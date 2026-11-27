# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Quantum ESPRESSO adapter: plane-wave DFT of crystals with pw.x (checked on QE 7.5).

A single point is a pw.x `scf` run, an optimisation `relax` or `vc-relax`, whose first SCF
is the energy at the input geometry and whose last is the one at the optimised geometry.
Vibrational frequencies are the phonons at Γ: ph.x on the ground state pw.x left behind, then
dynmat.x, which imposes the acoustic sum rule so that the three acoustic modes are zero. All
three write to the one output file.

ph.x and dynmat.x are found next to pw.x, with its prefix swapped: pw.exe gives ph.exe and
dynmat.exe on Windows, pw.x gives ph.x and dynmat.x elsewhere.

Pseudopotentials come from one folder, found as pw.x looks for it (``ESPRESSO_PSEUDO``,
then ``~/espresso/pseudo``) or as ``pseudo`` next to the ``bin`` folder of pw.x. The UPF
files in that folder are one library, those in each of its subfolders another
(``pseudo/pbesol/``). A library holds one UPF file per element, named after the element
(``Si.us.pbe…upf``, ``si_pbe_v1.uspp.F.UPF``), and ``cutoffs.json`` with the recommended
cutoffs per element (``{"Si": {"cutoff_wfc": 30, "cutoff_rho": 240}, …}``, the SSSP
convention). A job uses the largest cutoffs among its elements.

The functionals offered are those the libraries were made with, read from the UPF headers:
pw.x takes the functional from the pseudopotentials, so choosing a functional chooses its
library. Where two libraries share a functional, the first (the folder's own files, then the
subfolders by name) is used.
"""

import json
import math
import os
import re
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Optional

from ..calculations import CalculationType
from ..calculations import info
from ..method import Method
from ..results import Results
from . import quantum_espresso_output
from .base import Capabilities
from .base import EngineAdapter
from .base import EngineInfo
from .base import banner

NOT_CONVERGED = 'convergence NOT achieved'
_VERSION_BANNER = re.compile(r'Program PWSCF v\.(\d+(?:\.\d+)*)')
CUTOFFS_FILE_NAME = 'cutoffs.json'

# Γ-point phonons: the dynamical matrix goes to job.dyn, dynmat.x reads it back.
PHONON_FILE_NAME = 'ph.in'
PHONON_INPUT = """phonons at Gamma
&inputph
  prefix = 'job'
  outdir = './tmp'
  fildyn = 'job.dyn'
/
0.0 0.0 0.0
"""
# With fixed occupations ph.x also computes the Born charges, from which dynmat.x gets IR intensities.
PHONON_INPUT_INSULATOR = PHONON_INPUT.replace("  fildyn = 'job.dyn'\n", "  fildyn = 'job.dyn'\n  epsil = .true.\n")
DYNMAT_FILE_NAME = 'dynmat.in'
DYNMAT_INPUT = """&input
  fildyn = 'job.dyn'
  asr = 'crystal'
/
"""
_PROGRAMS = {PHONON_FILE_NAME: 'ph', DYNMAT_FILE_NAME: 'dynmat'}  # after pw.x

DEFAULT_FUNCTIONAL = 'PBE'
CAPABILITIES = Capabilities(
    families=(('DFT', 'DFT'),),
    # Without pseudopotentials; `capabilities` offers the functionals of the libraries found.
    functionals=((DEFAULT_FUNCTIONAL, DEFAULT_FUNCTIONAL),),
    dispersions=(('none', 'None'), ('D3BJ', 'D3(BJ)'), ('D3', 'D3')),
    basis_sets=(('pw', 'Plane waves'),),
    auxiliary_bases=(),
    references=(('RKS', 'Spin-restricted'), ('UKS', 'Spin-polarised')),
    solvations=(),
    scf_convergences=(
        ('loose', 'Loose (1e-6 Ry)'),
        ('normal', 'Normal (1e-8 Ry)'),
        ('tight', 'Tight (1e-10 Ry)'),
        ('verytight', 'Very tight (1e-12 Ry)'),
    ),
    integration_grids=(),
    stability_check=False,
    occupations=(('smearing', 'Smearing (metals)'), ('fixed', 'Fixed (insulators)')),
)

# Method and calculation values to pw.x input values.
_CONV_THR = {'loose': 1e-6, 'normal': 1e-8, 'tight': 1e-10, 'verytight': 1e-12}  # Ry
# (etot_conv_thr in Ry, forc_conv_thr in Ry/bohr); 'normal' is pw.x's default.
_RELAX_THRESHOLDS = {'loose': (1e-3, 1e-2), 'normal': (1e-4, 1e-3), 'tight': (1e-5, 1e-4), 'verytight': (1e-6, 1e-5)}
_DFTD3_VERSIONS = {'D3': 3, 'D3BJ': 4}
# Cold smearing gives the ground state of metals and insulators alike. Phonons of an insulator
# need fixed occupations: with smearing the density of states at the Fermi level is about
# zero and ph.x diverges.
_DEGAUSS = 0.01  # Ry
_EMPTY_BANDS = 4  # beyond the filled ones, so that fixed occupations still show the gap
_Z_VALENCE = re.compile(r'z_valence\s*=\s*"\s*([-+.\deE]+)"|([-+.\deE]+)\s+Z valence')
# UPF v2 header attribute, or the UPF v1 header line ('SLA PW PBX PBC  PBE  Exchange-Correlation functional').
_FUNCTIONAL = re.compile(r'functional\s*=\s*"([^"]*)"|^[ \t]*(\S.*?)\s+Exchange-Correlation functional', re.MULTILINE)
_HEADER_SIZE = 100_000  # characters of a UPF file read for its header; PP_INFO comes first
# pw.x's names of functionals (Modules/funct.f90), short or as their exchange, correlation
# and gradient-correction parts, to the names shown.
_FUNCTIONAL_NAMES = {
    'PBE': 'PBE',
    'SLA PW PBX PBC': 'PBE',
    'PBESOL': 'PBEsol',
    'SLA PW PSX PSC': 'PBEsol',
    'PZ': 'LDA',
    'LDA': 'LDA',
    'PW': 'LDA',
    'SLA PZ': 'LDA',
    'SLA PZ NOGX NOGC': 'LDA',
    'SLA PW NOGX NOGC': 'LDA',
    'PW91': 'PW91',
    'SLA PW GGX GGC': 'PW91',
    'REVPBE': 'revPBE',
    'SLA PW REVX PBC': 'revPBE',
    'BLYP': 'BLYP',
    'SLA LYP B88 BLYP': 'BLYP',
}


class QuantumEspressoAdapter(EngineAdapter):
    name = 'Quantum ESPRESSO'
    systems = ('crystal',)
    programs = ('pw.x', 'pw')
    input_file_name = 'job.in'
    # The single point at the input geometry is the first SCF of the optimisation, the one at
    # the optimised geometry its last.
    step_markers = {
        CalculationType.GEOMETRY_OPTIMISATION: re.compile('BFGS Geometry Optimization'),
        CalculationType.SINGLE_POINT: re.compile('End of BFGS Geometry Optimization'),
        CalculationType.VIBRATIONAL_FREQUENCIES: re.compile('Program PHONON'),
    }
    # pw.x ends normally after an SCF that did not converge, so ph.x starts and fails.
    failure_marker = re.compile(NOT_CONVERGED)

    def __init__(self, executable: Optional[str] = None):
        self.executable = executable
        # Set by `detect`, next to the executable it finds.
        self.pseudo_folder: Optional[Path] = None
        self._libraries: dict[str, Path] = {}
        self._libraries_of: Optional[Path] = None  # the pseudo folder `_libraries` was read from

    # Detection

    def detect(self) -> EngineInfo:
        path = self.executable or next(filter(None, map(shutil.which, self.programs)), None)
        if path is None or not Path(path).is_file():
            self.pseudo_folder = None
            return EngineInfo(found=False)
        path = str(Path(path))
        self.pseudo_folder = _pseudo_folder(Path(path))
        match = _VERSION_BANNER.search(banner([path, '-i', 'missing.in']))
        if self.pseudo_folder is None:
            detail = 'no pseudopotential folder'
        else:
            self._libraries_of = None  # read the folder again: files may have been added
            detail = f'pseudopotentials in {self.pseudo_folder} ({", ".join(self.libraries) or "no UPF files"})'
        return EngineInfo(found=True, version=match.group(1) if match else '', path=path, detail=detail)

    @property
    def libraries(self) -> dict[str, Path]:
        """The pseudopotential library of each functional, in the order offered."""
        if self._libraries_of != self.pseudo_folder:
            self._libraries = pseudo_libraries(self.pseudo_folder) if self.pseudo_folder else {}
            self._libraries_of = self.pseudo_folder
        return self._libraries

    def capabilities(self) -> Capabilities:
        if not self.libraries:
            return CAPABILITIES
        return replace(CAPABILITIES, functionals=tuple((name, name) for name in self.libraries))

    def default_method(self) -> Method:
        libraries = self.libraries
        return Method(
            functional=DEFAULT_FUNCTIONAL if DEFAULT_FUNCTIONAL in libraries or not libraries else next(iter(libraries)),
            dispersion='none',
            basis_set='pw',
            auxiliary_basis='',
            solvation='',
            integration_grid='',
            scf_max_iterations=100,
        )

    # Input and output

    def input_text(self, sample, calculations, method, settings) -> str:
        problem = self.system_problem(sample.periodic)
        if problem:
            raise ValueError(problem)
        steps = calculations.workflow()
        if not steps:
            raise ValueError('No calculation is selected.')
        if CalculationType.VIBRATIONAL_FREQUENCIES in steps and calculations.vibrational_frequencies.raman:
            raise ValueError(f'{self.name} does not compute Raman activities here; untick Raman.')
        if self.pseudo_folder is None:
            raise ValueError(f'No pseudopotential folder was found for {self.name}; set ESPRESSO_PSEUDO.')
        library = self.libraries.get(method.functional)
        if library is None:
            found = ', '.join(self.libraries) or 'none'
            raise ValueError(f'No {method.functional} pseudopotentials in {self.pseudo_folder} (found: {found}).')
        elements = sorted({atom.element for atom in sample.atoms})
        pseudopotentials = find_pseudopotentials(library, elements)
        for name in pseudopotentials.values():
            made_with = functional(library / name)
            if made_with and made_with != method.functional:
                raise ValueError(f'{name} in {library} was made with {made_with}, not {method.functional}.')
        cutoff_wfc, cutoff_rho = cutoffs(library, elements)

        optimisation = calculations.geometry_optimisation if CalculationType.GEOMETRY_OPTIMISATION in steps else None
        calculation = 'scf'
        if optimisation is not None:
            calculation = 'vc-relax' if optimisation.optimise == 'positions_and_cell' else 'relax'

        control = [
            f"calculation = '{calculation}'",
            "prefix = 'job'",
            "outdir = './tmp'",
            f"pseudo_dir = '{library.as_posix()}'",
        ]
        if optimisation is not None:
            energy, force = _RELAX_THRESHOLDS[optimisation.convergence]
            control += [f'etot_conv_thr = {energy:g}', f'forc_conv_thr = {force:g}', f'nstep = {optimisation.max_steps}']
        system = [
            'ibrav = 0',
            f'nat = {sample.atom_count}',
            f'ntyp = {len(elements)}',
            f'ecutwfc = {cutoff_wfc:g}',
            f'ecutrho = {cutoff_rho:g}',
        ]
        if method.occupations == 'fixed':
            electrons = sum(_valence(library / pseudopotentials[atom.element]) for atom in sample.atoms)
            system += ["occupations = 'fixed'", f'nbnd = {math.ceil((electrons - sample.charge) / 2) + _EMPTY_BANDS}']
        else:
            system += ["occupations = 'smearing'", "smearing = 'cold'", f'degauss = {_DEGAUSS:g}']
        if optimisation is not None and any(atom.fixed for atom in sample.atoms):
            # Fixed atoms break symmetries pw.x finds at the start, and it stops when they go.
            system.append('nosym = .true.')
        if sample.charge:
            system.append(f'tot_charge = {sample.charge}')
        if method.reference == 'UKS':
            system += ['nspin = 2', f'tot_magnetization = {sample.multiplicity - 1}']
        if method.dispersion != 'none':
            system += ["vdw_corr = 'dft-d3'", f'dftd3_version = {_DFTD3_VERSIONS[method.dispersion]}']
        scf = [f'conv_thr = {_CONV_THR[method.scf_convergence]:g}', f'electron_maxstep = {method.scf_max_iterations}']

        steps_text = ', '.join(info(step).name for step in steps)
        lines = [f'! EasyQM: {sample.name or "sample"} ({sample.formula}) - {steps_text}']
        lines += _namelist('control', control) + _namelist('system', system) + _namelist('electrons', scf)
        if optimisation is not None:
            lines += _namelist('ions', [])
            if calculation == 'vc-relax':
                lines += _namelist('cell', ["cell_dofree = 'all'"])
        lines.append('ATOMIC_SPECIES')
        lines += [f'  {element:<2} {_mass(element):10.4f}  {pseudopotentials[element]}' for element in elements]
        lines.append('CELL_PARAMETERS angstrom')
        lines += [f'  {x:14.8f} {y:14.8f} {z:14.8f}' for x, y, z in sample.cell.vectors]
        lines.append('ATOMIC_POSITIONS angstrom')
        lines += [
            f'  {atom.element:<2} {atom.x:14.8f} {atom.y:14.8f} {atom.z:14.8f}' + ('  0 0 0' if atom.fixed else '')
            for atom in sample.atoms
        ]
        grid = method.kpoints.for_cell(sample.cell)
        lines += ['K_POINTS automatic', f'  {grid[0]} {grid[1]} {grid[2]}  0 0 0']
        return '\n'.join(lines) + '\n'

    def input_files(self, sample, calculations, method, settings) -> dict[str, str]:
        files = {self.input_file_name: self.input_text(sample, calculations, method, settings)}
        if CalculationType.VIBRATIONAL_FREQUENCIES in calculations.workflow():
            files[PHONON_FILE_NAME] = PHONON_INPUT_INSULATOR if method.occupations == 'fixed' else PHONON_INPUT
            files[DYNMAT_FILE_NAME] = DYNMAT_INPUT
        return files

    def command(self, executable: str, input_path: Path) -> list[str]:
        return [executable, '-i', input_path.name]

    def commands(self, executable: str, input_names: list[str]) -> list[list[str]]:
        commands = [self.command(executable, Path(input_names[0]))]
        for name in input_names[1:]:
            program = Path(sibling(executable, _PROGRAMS[name]))
            if not program.is_file():
                raise ValueError(f'{program.name} was not found next to {Path(executable).name} in {program.parent}.')
            commands.append(self.command(str(program), Path(name)))
        return commands

    def succeeded(self, output: str) -> bool:
        return 'JOB DONE.' in output and NOT_CONVERGED not in output

    def parse(self, output: str) -> Results:
        return quantum_espresso_output.parse(output)


def sibling(executable: str, program: str) -> str:
    """Another Quantum ESPRESSO program beside pw.x: F:/QE/bin/pw.exe, 'ph' -> F:/QE/bin/ph.exe."""
    path = Path(executable)
    rest = path.name[2:] if path.name.lower().startswith('pw') else path.suffix
    return str(path.with_name(program + rest))


def pseudo_libraries(folder: Path) -> dict[str, Path]:
    """The library of each functional: the folder's own UPF files, then each subfolder's.

    A library is named after the functional most of its files state, or after its folder if
    they state none. The first library of a functional wins.
    """
    libraries: dict[str, Path] = {}
    try:
        subfolders = sorted((path for path in folder.iterdir() if path.is_dir()), key=lambda path: path.name.lower())
    except OSError:
        return libraries
    for library in (folder, *subfolders):
        files = _upf_files(library)
        if not files:
            continue
        stated = [name for name in map(functional, files) if name]
        name = max(dict.fromkeys(stated), key=stated.count) if stated else library.name
        libraries.setdefault(name, library)
    return libraries


def functional(path: Path) -> str:
    """The functional a pseudopotential was made with, from its UPF header: 'PBE', 'PBEsol',
    …, pw.x's own name for one not known here, or '' if the header states none."""
    try:
        with open(path, encoding='utf-8', errors='replace') as file:
            match = _FUNCTIONAL.search(file.read(_HEADER_SIZE))
    except OSError:
        return ''
    if match is None:
        return ''
    parts = (match.group(1) or match.group(2)).upper().split()
    if not parts:
        return ''
    # UPF v1 lines give the parts and then the short name: 'SLA PW PBX PBC PBE'.
    for key in (' '.join(parts), ' '.join(parts[:4]), ' '.join(parts[:2]), parts[-1]):
        if key in _FUNCTIONAL_NAMES:
            return _FUNCTIONAL_NAMES[key]
    return ' '.join(parts)


def _upf_files(folder: Path) -> list[Path]:
    try:
        return sorted(path for path in folder.iterdir() if path.suffix.lower() == '.upf' and path.is_file())
    except OSError:
        return []


def find_pseudopotentials(folder: Path, elements: list[str]) -> dict[str, str]:
    """The UPF file name of each element; exactly one file per element is expected."""
    files = sorted(path.name for path in folder.iterdir() if path.suffix.lower() == '.upf')
    found = {}
    for element in elements:
        named = [name for name in files if re.match(rf'{element}[._-]', name, re.IGNORECASE)]
        if not named:
            raise ValueError(f'No pseudopotential for {element} in {folder}.')
        if len(named) > 1:
            raise ValueError(f'Several pseudopotentials for {element} in {folder}: {", ".join(named)}. Keep one.')
        found[element] = named[0]
    return found


def cutoffs(folder: Path, elements: list[str]) -> tuple[float, float]:
    """(ecutwfc, ecutrho) in Ry: the largest recommended values among the elements."""
    path = folder / CUTOFFS_FILE_NAME
    try:
        table = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        raise ValueError(f'The recommended cutoffs could not be read from {path}: {error}') from None
    missing = [element for element in elements if element not in table]
    if missing:
        raise ValueError(f'{path} has no cutoffs for {", ".join(missing)}.')
    return (
        max(float(table[element]['cutoff_wfc']) for element in elements),
        max(float(table[element]['cutoff_rho']) for element in elements),
    )


def _pseudo_folder(executable: Path) -> Optional[Path]:
    candidates = [
        os.environ.get('ESPRESSO_PSEUDO', ''),
        executable.parent.parent / 'pseudo',  # F:/QE/bin/pw.exe -> F:/QE/pseudo
        Path.home() / 'espresso' / 'pseudo',
    ]
    return next((Path(candidate) for candidate in candidates if candidate and Path(candidate).is_dir()), None)


def _valence(path: Path) -> float:
    """Valence electrons of a pseudopotential, from its UPF header."""
    with open(path, encoding='utf-8', errors='replace') as file:
        match = _Z_VALENCE.search(file.read(100_000))
    if match is None:
        raise ValueError(f'{path.name} states no valence charge.')
    return float(match.group(1) or match.group(2))


def _namelist(name: str, entries: list[str]) -> list[str]:
    return [f'&{name}', *(f'  {entry}' for entry in entries), '/']


def _mass(element: str) -> float:
    """Atomic mass in u; pw.x needs one per species, though only dynamics and phonons use it."""
    try:
        import gemmi
    except ImportError:
        raise ValueError('Writing a Quantum ESPRESSO input needs the gemmi package.') from None
    return gemmi.Element(element).weight
