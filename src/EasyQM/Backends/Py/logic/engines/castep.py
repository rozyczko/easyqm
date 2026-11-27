# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""CASTEP adapter: plane-wave DFT of crystals (checked on CASTEP 26.11, serial build).

``castep <seed>`` reads ``<seed>.cell`` and ``<seed>.param`` and writes its log to
``<seed>.castep``; nothing goes to standard output. One run does one task, so a workflow is
the ground-state run ``job`` (a single point, or the geometry optimisation), then one run per
ticked Frequencies (``job-phonon``), Band structure (``job-bands``) and Density of states
(``job-dos``), each continuing from ``job.check``: it takes the ground state, the optimised
geometry and the ionic constraints from there. ``job`` always runs, so every checkpoint a
run reads has a run that wrote it. Every run is given the whole method all the same.

CASTEP exits with code 0 after a failure too. A run ended well when its log has the closing
``Total time`` line; an ``.err`` file alone does not mean failure, a completed phonon run can
leave one. The reason of a failure is the failed run's ``Error`` line.

Pseudopotentials are generated on the fly for the functional from a library named in the
input (C19 by default), so no files are needed. ``Automatic`` takes NCP19, which is
norm-conserving, when the frequencies can be analytical with it (`analytical_obstacle`),
and C19 otherwise. Folders of potential files are offered from ``PSPOT_DIR``; the files are
copied into the run folder.

Atoms are written in the sample's order. CASTEP lists them by species and numbers them
within each species, and so do its constraints; `castep_output` maps them back.
"""

import os
import re
import shutil
import sys
from dataclasses import replace
from pathlib import Path
from typing import Optional

from ..calculations import CalculationType
from ..calculations import info
from ..kpath import band_path
from ..kpath import path_points
from ..method import Method
from ..method import RunSettings
from ..results import Results
from ..runner import Step
from . import castep_output
from .base import Capabilities
from .base import EngineAdapter
from .base import EngineInfo
from .base import EngineOption
from .base import probe

SEED = 'job'
# The run of each calculation after the ground state, in the order they run.
CHILD_SEEDS = {
    CalculationType.VIBRATIONAL_FREQUENCIES: 'job-phonon',
    CalculationType.BAND_STRUCTURE: 'job-bands',
    CalculationType.DENSITY_OF_STATES: 'job-dos',
}
_TITLES = {SEED: 'Ground state', **{seed: info(calculation).name for calculation, seed in CHILD_SEEDS.items()}}

AUTOMATIC = 'automatic'
LIBRARIES = (
    ('C19', 'C19 (ultrasoft)'),
    ('NCP19', 'NCP19 (norm-conserving)'),
    ('QC5', 'QC5 (ultrasoft, low cut-off)'),
    ('HARD', 'HARD (ultrasoft, high cut-off)'),
    ('C19MK2', 'C19MK2 (ultrasoft)'),
)
_DEFAULT_LIBRARY, _ANALYTICAL_LIBRARY = 'C19', 'NCP19'
_NORM_CONSERVING = ('NCP19',)
POTENTIAL_SUFFIXES = ('.usp', '.uspcc', '.recpot', '.upf')
PRECISIONS = (('COARSE', 'Coarse'), ('MEDIUM', 'Medium'), ('FINE', 'Fine'), ('PRECISE', 'Precise'), ('EXTREME', 'Extreme'))

# Curated: the executable lists 32 functionals, among them ZERO and LDA-X. Hybrids are later work.
FUNCTIONALS = (('LDA', 'LDA'), ('PBE', 'PBE'), ('PBESOL', 'PBEsol'), ('RPBE', 'RPBE'), ('WC', 'WC'),
               ('PW91', 'PW91'), ('BLYP', 'BLYP'), ('RSCAN', 'rSCAN'))
CAPABILITIES = Capabilities(
    families=(('DFT', 'DFT'),),
    functionals=FUNCTIONALS,
    dispersions=(('none', 'None'), ('D3', 'D3'), ('D3BJ', 'D3(BJ)'), ('TS', 'TS'), ('MBD*', 'MBD*'), ('G06', 'G06 (D2)')),
    basis_sets=(('pw', 'Plane waves'),),
    auxiliary_bases=(),
    references=(('RKS', 'Spin-restricted'), ('UKS', 'Spin-polarised')),
    solvations=(),
    scf_convergences=(
        ('loose', 'Loose (1e-5 eV/atom)'),
        ('normal', 'Normal (1e-6 eV/atom)'),
        ('tight', 'Tight (1e-8 eV/atom)'),
        ('verytight', 'Very tight (1e-10 eV/atom)'),
    ),
    integration_grids=(),
    stability_check=False,
    occupations=(('smearing', 'Smearing (metals)'), ('fixed', 'Fixed (insulators)')),
)
_SEDC_SCHEMES = {'D3': 'D3', 'D3BJ': 'D3-BJ', 'TS': 'TS', 'MBD*': 'MBD*', 'G06': 'G06'}
# Analytical (DFPT) second derivatives exist for these only; D3 and the rest abort the run.
_DFPT_DISPERSIONS = ('none', 'TS', 'G06')

_ELEC_ENERGY_TOL = {'loose': 1e-5, 'normal': 1e-6, 'tight': 1e-8, 'verytight': 1e-10}  # eV/atom
# geom_energy_tol (eV/atom), geom_force_tol (eV/Å), geom_disp_tol (Å), geom_stress_tol (GPa);
# 'normal' is CASTEP's default.
_GEOM_TOLERANCES = {
    'loose': (1e-4, 0.1, 5e-3, 0.5),
    'normal': (2e-5, 0.05, 1e-3, 0.1),
    'tight': (5e-6, 0.01, 5e-4, 0.05),
    'verytight': (1e-6, 0.005, 1e-4, 0.01),
}
_EMPTY_BANDS = 4  # with fixed occupations, so that the levels of the ground state show the gap
# CASTEP refuses limits below its convergence windows (elec_convergence_win, geom_convergence_win).
MIN_SCF_CYCLES, MIN_GEOM_STEPS = 3, 2

_VERSION = re.compile(r'CASTEP version:\s*(\S+)')
_SERIAL = re.compile(r'Comms\s*:\s*serial')
_ALLOWED = re.compile(r'Allowed values:\s*(.+?)\.\s*$', re.MULTILINE)
_TOTAL_TIME = re.compile(r'^Total time\s*=', re.MULTILINE)
_ERROR = re.compile(r'^\s*(?:ERROR|Error)\b(:?)\s*(.+?)\s*$', re.MULTILINE)
_MAX_FORCE = re.compile(r'Maximum force \|F\|max\s*=\s*(-?\d+\.\d+)')
_DLL_NOT_FOUND = 0xC0000135


class CastepAdapter(EngineAdapter):
    name = 'CASTEP'
    systems = ('crystal',)
    programs = ('castep.serial', 'castep.mpi', 'castep')
    input_file_name = f'{SEED}.cell'
    raman = False
    step_markers = {
        # The single point at the input geometry is the optimiser's iteration 0, the one at the
        # optimised geometry its final configuration.
        CalculationType.GEOMETRY_OPTIMISATION: re.compile(r'LBFGS: finished iteration\s+0 '),
        CalculationType.SINGLE_POINT: re.compile(r'LBFGS: Final Configuration|there is nothing to optimise'),
        **{calculation: re.compile(rf'^==> {seed}:', re.MULTILINE) for calculation, seed in CHILD_SEEDS.items()},
    }

    def __init__(self, executable: Optional[str] = None):
        self.executable = executable
        self._functionals: frozenset[str] = frozenset()  # what the executable accepts; empty when unknown

    # Detection

    def detect(self) -> EngineInfo:
        self._functionals = frozenset()
        path = self.executable or next(filter(None, map(shutil.which, self.programs)), None)
        if path is None or not Path(path).is_file():
            return EngineInfo(found=False)
        path = str(Path(path))
        environment = self.environment(RunSettings())
        version = probe([path, '--version'], environment)
        match = _VERSION.search(version.text)
        if match is None and version.code != 0:
            return EngineInfo(found=False, path=path, detail=start_problem(Path(path).name, version.code))
        allowed = _ALLOWED.search(probe([path, '--help', 'xc_functional'], environment).text)
        if allowed:
            self._functionals = frozenset(value.strip().upper() for value in allowed.group(1).split(','))
        comms = 'serial' if _SERIAL.search(version.text) else 'MPI'
        return EngineInfo(found=True, version=match.group(1) if match else '', path=path, detail=comms)

    def capabilities(self) -> Capabilities:
        if not self._functionals:
            return CAPABILITIES
        offered = tuple(choice for choice in FUNCTIONALS if choice[0] in self._functionals)
        return replace(CAPABILITIES, functionals=offered or FUNCTIONALS)

    def default_method(self) -> Method:
        return Method(
            functional='PBE',
            dispersion='none',
            basis_set='pw',
            auxiliary_basis='',
            solvation='',
            integration_grid='',
            scf_max_iterations=100,
        )

    def engine_options(self, elements: list[str]) -> tuple[EngineOption, ...]:
        folders = tuple((str(folder), folder.name) for folder in potential_folders(elements))
        return (
            EngineOption(
                'pseudopotentials',
                'Pseudopotentials',
                ((AUTOMATIC, 'Automatic'), *LIBRARIES, *folders),
                AUTOMATIC,
                'Automatic: C19, or NCP19 when the frequencies can be analytical with it. Libraries are generated '
                'for the functional; the functional of files from a folder in PSPOT_DIR is not checked.',
            ),
            EngineOption('basis_precision', 'Basis precision', PRECISIONS, 'FINE',
                         'The plane-wave cut-off energy, set from the pseudopotentials.'),
        )

    def option_warning(self, name: str, value: str, calculations, method) -> str:
        options = calculations.vibrational_frequencies
        if (name != 'pseudopotentials' or value == AUTOMATIC or value in _NORM_CONSERVING
                or CalculationType.VIBRATIONAL_FREQUENCIES not in calculations.workflow() or options.type != 'analytical'):
            return ''
        text = (f'With {library_label(value)} the frequencies are computed by finite displacement and have no IR '
                'intensities.')
        return text if method_obstacle(method, options) else text + ' NCP19 or Automatic gives both.'

    def frequencies_note(self, calculations, method) -> str:
        if CalculationType.VIBRATIONAL_FREQUENCIES not in calculations.workflow():
            return ''
        library = resolve_library(calculations, method)
        reason = analytical_obstacle(library, method, calculations.vibrational_frequencies)
        if reason:
            return f'Finite displacement, no IR intensities: {reason}.'
        return f'Analytical (DFPT) with IR intensities; pseudopotentials {library_label(library)}.'

    # Input

    def input_files(self, sample, calculations, method, settings) -> dict[str, str]:
        steps = self._check(sample, calculations, method)
        library = resolve_library(calculations, method)
        potentials = _library_files(library, sample)
        # One word sets a library for every species; files from a folder are named per species.
        species = [f'{element:<2} {path.name}' for element, path in sorted(potentials.items())] if potentials else [library]
        files = {}
        for seed in [SEED, *(CHILD_SEEDS[step] for step in steps if step in CHILD_SEEDS)]:
            files[f'{seed}.cell'] = _cell(sample, calculations, method, seed, species, steps)
            files[f'{seed}.param'] = _param(sample, calculations, method, seed, library, steps)
        for path in (potentials or {}).values():
            files[path.name] = path.read_text(encoding='utf-8')
        return files

    def _check(self, sample, calculations, method) -> list[CalculationType]:
        """The workflow, or why there is no input for it."""
        problem = self.system_problem(sample.periodic)
        if problem:
            raise ValueError(problem)
        steps = calculations.workflow()
        if not steps:
            raise ValueError('No calculation is selected.')
        if CalculationType.VIBRATIONAL_FREQUENCIES in steps and calculations.vibrational_frequencies.raman:
            raise ValueError(f'{self.name} does not compute Raman activities here; untick Raman.')
        if method.scf_max_iterations < MIN_SCF_CYCLES:
            raise ValueError(f'{self.name} needs at least {MIN_SCF_CYCLES} SCF iterations.')
        if CalculationType.GEOMETRY_OPTIMISATION in steps:
            options = calculations.geometry_optimisation
            if options.max_steps < MIN_GEOM_STEPS:
                raise ValueError(f'{self.name} needs at least {MIN_GEOM_STEPS} optimisation steps.')
            if options.optimise == 'positions' and all(atom.fixed for atom in sample.atoms):
                raise ValueError('Nothing to optimise: every atom is fixed.')
        return steps

    # Running

    def steps(self, executable: str, input_names: list[str]) -> list[Step]:
        seeds = [name.removesuffix('.param') for name in input_names if name.endswith('.param')]
        return [Step([executable, seed], _TITLES[seed], f'{seed}.castep', f'{seed}.*.err') for seed in seeds]

    def environment(self, settings: RunSettings) -> dict[str, str]:
        # An OpenMP build takes every core otherwise, and OpenBLAS keeps its own threads.
        return {'OMP_NUM_THREADS': str(settings.cores), 'OPENBLAS_NUM_THREADS': str(settings.cores)}

    def step_succeeded(self, text: str) -> bool:
        return _TOTAL_TIME.search(text) is not None

    def succeeded(self, output: str) -> bool:
        parts = castep_output.split_steps(output)
        return bool(parts) and all(self.step_succeeded(text) for text in parts.values())

    def failure_reason(self, output: str) -> str:
        parts = castep_output.split_steps(output)
        text = list(parts.values())[-1] if parts else output
        if self.step_succeeded(text):
            return ''
        if 'unoptimised geometry' in text:
            force = _MAX_FORCE.search(text)
            largest = f': the largest force is {float(force.group(1)):.3g} eV/Å' if force else ''
            return f'Frequencies need an optimised geometry{largest}. Tick Optimisation.'
        error = _ERROR.search(text)  # 'ERROR: Phonon run aborted…', 'Error in parameters_restore: …'
        if error:
            return error.group(2) if error.group(1) else error.group(0).strip()
        started = re.search(r'^Could not start .*$', text, re.MULTILINE)
        return started.group(0) if started else 'the run ended before its closing Total time line'

    # Results

    def parse(self, output: str) -> Results:
        return castep_output.read(None, output)

    def read_results(self, folder: Optional[Path], output: str) -> Results:
        return castep_output.read(folder, output)


# Frequencies and pseudopotentials


def resolve_library(calculations, method) -> str:
    """The library or folder a job uses: the one chosen, or for Automatic NCP19 when it makes
    the frequencies analytical and C19 otherwise."""
    chosen = method.engine_options.get('pseudopotentials', AUTOMATIC)
    if chosen != AUTOMATIC:
        return chosen
    analytical = (CalculationType.VIBRATIONAL_FREQUENCIES in calculations.workflow()
                  and not method_obstacle(method, calculations.vibrational_frequencies))
    return _ANALYTICAL_LIBRARY if analytical else _DEFAULT_LIBRARY


def method_obstacle(method, options) -> str:
    """Why the method rules out analytical frequencies whatever the library, or ''."""
    if options.type != 'analytical':
        return 'the type is Numerical'
    if method.occupations != 'fixed':
        return 'smearing is on'  # the electric-field response needs an insulator
    if method.dispersion not in _DFPT_DISPERSIONS:
        label = dict(CAPABILITIES.dispersions).get(method.dispersion, method.dispersion)
        return f'{label} has no analytical second derivatives in CASTEP'
    if method.functional == 'RSCAN':  # it runs, and gives wrong frequencies
        return 'rSCAN has no analytical second derivatives in CASTEP'
    if method.reference == 'UKS':
        return 'the reference is spin-polarised'
    return ''


def analytical_obstacle(library: str, method, options) -> str:
    """Why the frequencies are computed by finite displacement, or '' for analytical (DFPT).
    A folder of files counts as not norm-conserving: its type is not known."""
    obstacle = method_obstacle(method, options)
    if obstacle:
        return obstacle
    return '' if library in _NORM_CONSERVING else f'{library_label(library)} is not norm-conserving'


def library_label(library: str) -> str:
    """'C19', or the name of a folder of potential files."""
    return library if library in dict(LIBRARIES) else Path(library).name


def potential_folders(elements: list[str]) -> list[Path]:
    """The folders named in PSPOT_DIR, and the folders directly inside them, that have exactly
    one potential file for every element."""
    if not elements:
        return []
    roots = [Path(root) for root in os.environ.get('PSPOT_DIR', '').split(os.pathsep) if root]
    candidates = []
    for root in roots:
        if root.is_dir():
            candidates += [root, *sorted(path for path in root.iterdir() if path.is_dir())]
    return [folder for folder in dict.fromkeys(candidates) if potential_files(folder, elements) is not None]


def potential_files(folder: Path, elements: list[str]) -> Optional[dict[str, Path]]:
    """The one potential file of each element in `folder`, named after it (Si_C19.usp,
    si.pbe.recpot: the symbol, then _, -, . or the end); None if one is missing or ambiguous."""
    try:
        files = [path for path in folder.iterdir() if path.is_file() and path.suffix.lower() in POTENTIAL_SUFFIXES]
    except OSError:
        return None
    found = {}
    for element in elements:
        named = [path for path in files if re.fullmatch(rf'{element}(?:[._-].*)?', path.stem, re.IGNORECASE)]
        if len(named) != 1:
            return None
        found[element] = named[0]
    return found


def _library_files(library: str, sample) -> Optional[dict[str, Path]]:
    """The potential file of each element for a folder, None for an on-the-fly library."""
    if library in dict(LIBRARIES):
        return None
    elements = sorted({atom.element for atom in sample.atoms})
    files = potential_files(Path(library), elements)
    if files is None:
        raise ValueError(f'{library} does not hold exactly one pseudopotential for each of {", ".join(elements)}.')
    return files


def start_problem(name: str, code: Optional[int]) -> str:
    """The card text for an executable that is there but did not report its version."""
    if code is None:
        return f'{name} could not be run'
    code &= 0xFFFFFFFF
    if code == _DLL_NOT_FOUND and sys.platform == 'win32':
        return f'{name} does not start (0xC0000135: a DLL it needs was not found)'
    return f'{name} does not start (exit code {f"0x{code:08X}" if sys.platform == "win32" else code})'


# Writing the files


def _cell(sample, calculations, method, seed: str, species: list[str], steps) -> str:
    """One .cell file: the structure, the k-points, the rows of the SPECIES_POT block and what
    the run of `seed` adds."""
    optimisation = calculations.geometry_optimisation if CalculationType.GEOMETRY_OPTIMISATION in steps else None
    fixed = optimisation is not None and any(atom.fixed for atom in sample.atoms)
    grid = method.kpoints.for_cell(sample.cell)
    lines = [f'! EasyQM: {sample.name or "sample"} ({sample.formula}) - {_TITLES[seed]}', '']
    lines += _block('LATTICE_CART', ['ang', *(_vector(vector) for vector in sample.cell.vectors)])
    lines += _block('POSITIONS_FRAC', [f'{atom.element:<2} {_vector(sample.cell.fractional(atom.x, atom.y, atom.z))}'
                                       for atom in sample.atoms])
    lines.append(f'kpoint_mp_grid : {grid[0]} {grid[1]} {grid[2]}')
    if not fixed:
        lines.append('symmetry_generate')  # fixed atoms break symmetries, as with pw.x's nosym
    lines += _block('SPECIES_POT', species)
    if seed == SEED and optimisation is not None:
        if optimisation.optimise == 'positions':
            lines.append('fix_all_cell : true')
        if fixed:
            lines += _block('IONIC_CONSTRAINTS', _constraints(sample.atoms))
    elif seed == CHILD_SEEDS[CalculationType.VIBRATIONAL_FREQUENCIES]:
        lines += _block('PHONON_KPOINT_LIST', ['0.0 0.0 0.0 1.0'])
    elif seed == CHILD_SEEDS[CalculationType.BAND_STRUCTURE]:
        points = path_points(sample.cell, band_path(sample.cell), calculations.band_structure.points)
        # CASTEP wants the weights to sum to 1 within about 1e-8.
        lines += _block('SPECTRAL_KPOINT_LIST', [f'{_vector(k)} {1 / len(points):.15f}' + (f'  ! {name}' if name else '')
                                                  for k, name in points])
    elif seed == CHILD_SEEDS[CalculationType.DENSITY_OF_STATES]:
        factor = calculations.density_of_states.grid_factor
        lines.append('spectral_kpoint_mp_grid : ' + ' '.join(str(n * factor) for n in grid))
    return '\n'.join(lines).rstrip() + '\n'


def _constraints(atoms) -> list[str]:
    """Three lines per fixed atom, which CASTEP names by species and number within the species."""
    lines, counts = [], {}
    for atom in atoms:
        counts[atom.element] = counts.get(atom.element, 0) + 1
        if atom.fixed:
            for axis in ('1 0 0', '0 1 0', '0 0 1'):
                lines.append(f'{len(lines) + 1:4d} {atom.element:<2} {counts[atom.element]:4d}  {axis}')
    return lines


def _param(sample, calculations, method, seed: str, library: str, steps) -> str:
    """One .param file: the whole method, then the task of the run of `seed`."""
    lines = [f'! EasyQM: {_TITLES[seed]}', *_task(calculations, method, seed, library, steps), '']
    lines += [
        f'xc_functional : {method.functional}',
        f'basis_precision : {method.engine_options.get("basis_precision", "FINE")}',
        f'elec_energy_tol : {_ELEC_ENERGY_TOL[method.scf_convergence]:g}',
        f'max_scf_cycles : {method.scf_max_iterations}',
    ]
    if method.occupations == 'fixed':
        lines += ['fix_occupancy : true', f'nextra_bands : {_EMPTY_BANDS}']
    else:
        lines.append('fix_occupancy : false')
    if method.reference == 'UKS':
        lines += ['spin_polarized : true', f'spin : {sample.multiplicity - 1}']
        if method.occupations != 'fixed':
            lines.append('spin_fix : -1')  # hold the spin, as pw.x's tot_magnetization does
    else:
        lines.append('spin_polarized : false')  # CASTEP polarises an odd electron count on its own
    if sample.charge:
        lines.append(f'charge : {sample.charge}')
    if method.dispersion != 'none':
        lines += ['sedc_apply : true', f'sedc_scheme : {_SEDC_SCHEMES[method.dispersion]}']
    if seed != SEED:
        lines.append(f'continuation : {SEED}.check')
    return '\n'.join(lines) + '\n'


def _task(calculations, method, seed: str, library: str, steps) -> list[str]:
    optimisation = calculations.geometry_optimisation if CalculationType.GEOMETRY_OPTIMISATION in steps else None
    tolerances = _GEOM_TOLERANCES[optimisation.convergence if optimisation else 'normal']
    if seed == SEED:
        if optimisation is None:
            return ['task : singlepoint']
        energy, force, displacement, stress = tolerances
        return ['task : geometryoptimization', 'geom_method : LBFGS', f'geom_max_iter : {optimisation.max_steps}',
                f'geom_energy_tol : {energy:g}', f'geom_force_tol : {force:g}', f'geom_disp_tol : {displacement:g}',
                f'geom_stress_tol : {stress:g}']
    if seed == CHILD_SEEDS[CalculationType.VIBRATIONAL_FREQUENCIES]:
        # CASTEP refuses a phonon run whose forces exceed geom_force_tol.
        tolerance = f'geom_force_tol : {tolerances[1]:g}'
        if analytical_obstacle(library, method, calculations.vibrational_frequencies):
            return ['task : phonon', 'phonon_method : finitedisplacement', tolerance]
        return ['task : phonon+efield', 'phonon_method : dfpt', tolerance]
    spectral = 'bandstructure' if seed == CHILD_SEEDS[CalculationType.BAND_STRUCTURE] else 'dos'
    options = calculations.band_structure if spectral == 'bandstructure' else calculations.density_of_states
    # Nothing reads a spectral run's checkpoint or orbitals, which take megabytes.
    return ['task : spectral', f'spectral_task : {spectral}', f'spectral_nextra_bands : {options.empty_bands}',
            'write_checkpoint : none', 'write_orbitals : false']


def _block(name: str, rows: list[str]) -> list[str]:
    return [f'%BLOCK {name}', *(f'  {row}' for row in rows), f'%ENDBLOCK {name}', '']


def _vector(values) -> str:
    return ' '.join(f'{value:14.8f}' for value in values)
