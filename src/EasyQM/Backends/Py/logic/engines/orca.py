# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""ORCA adapter: detection, the choices ORCA offers, input generation, success check and results.

The whole workflow goes into one input file, so one ORCA process writes one output file:
optimisation and frequencies are keywords of the same job (ORCA runs the frequencies at the
optimised geometry), and the single point is the energy every job prints. Only a single
point at the *input* geometry before an optimisation needs a second job, joined with
``$new_job``.

Excited states run last, in a second ORCA process on ``excited.inp`` when there are
ground-state steps, on the optimised geometry (``job.xyz``) after an optimisation. A job
after ``$new_job`` would inherit settings such as the dispersion correction, which ORCA
refuses with EOM-CCSD; and on its own ORCA neither optimises nor differentiates an excited
state. The energies before stay ground-state ones; the excited-state job reports the
excited state's energy as its final energy.
"""

import re
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Optional

from ..calculations import CalculationType
from ..calculations import info
from ..elements import atomic_number
from ..results import Results
from . import orca_output
from .base import Capabilities
from .base import EngineAdapter
from .base import EngineInfo
from .base import banner
from .orca_output import EXCITED_STATES_START

_VERSION_FOLDER = re.compile(r'^\d+(\.\d+)+$')
_VERSION_BANNER = re.compile(r'Program Version\s+(\d+(?:\.\d+)+)')
NORMAL_TERMINATION = 'ORCA TERMINATED NORMALLY'
EXCITED_FILE_NAME = 'excited.inp'  # run by a second ORCA process after the ground-state steps

CAPABILITIES = Capabilities(
    families=(('HF', 'HF'), ('DFT', 'DFT')),
    functionals=(
        ('B3LYP', 'B3LYP'),
        ('PBE', 'PBE'),
        ('PBE0', 'PBE0'),
        ('TPSS', 'TPSS'),
        ('wB97X-D3', 'ωB97X-D3'),
        ('M062X', 'M06-2X'),
    ),
    dispersions=(('none', 'None'), ('D3BJ', 'D3(BJ)'), ('D3', 'D3'), ('D4', 'D4')),
    basis_sets=(
        ('def2-SVP', 'def2-SVP'),
        ('def2-TZVP', 'def2-TZVP'),
        ('def2-TZVPP', 'def2-TZVPP'),
        ('def2-QZVP', 'def2-QZVP'),
        ('cc-pVDZ', 'cc-pVDZ'),
        ('cc-pVTZ', 'cc-pVTZ'),
    ),
    auxiliary_bases=(('def2/J', 'def2/J (RIJCOSX)'), ('def2/JK', 'def2/JK'), ('none', 'None')),
    references=(('RKS', 'RKS (closed shell)'), ('UKS', 'UKS (unrestricted)'), ('ROKS', 'ROKS')),
    solvations=(('none', 'None'), ('CPCM(water)', 'CPCM (water)'), ('SMD(water)', 'SMD (water)')),
    scf_convergences=(
        ('loose', 'Loose (1e-5 Eh)'),
        ('normal', 'Normal (1e-6 Eh)'),
        ('tight', 'Tight (1e-8 Eh)'),
        ('verytight', 'Very tight (1e-9 Eh)'),
    ),
    integration_grids=(('DefGrid1', 'DefGrid1'), ('DefGrid2', 'DefGrid2'), ('DefGrid3', 'DefGrid3')),
)

# Method and calculation values to ORCA keywords. Every keyword was checked against ORCA 6.1.
_AUXILIARY_KEYWORDS = {'def2/J': 'def2/J RIJCOSX', 'def2/JK': 'def2/JK RIJK', 'none': 'NoRI'}
_HF_REFERENCES = {'RKS': 'RHF', 'UKS': 'UHF', 'ROKS': 'ROHF'}
_SCF_KEYWORDS = {'loose': 'LooseSCF', 'normal': 'NormalSCF', 'tight': 'TightSCF', 'verytight': 'VeryTightSCF'}
_OPT_KEYWORDS = {'loose': 'LooseOpt', 'normal': 'Opt', 'tight': 'TightOpt', 'verytight': 'VeryTightOpt'}

# %maxcore is per process and ORCA may exceed it, so it gets a share of the memory setting.
_MAXCORE_SHARE = 0.75
# From Rb on, def2 basis sets replace the core with an effective core potential, so ORCA's
# orbital numbers no longer count every electron.
_ECP_FROM = 37


class OrcaAdapter(EngineAdapter):
    name = 'ORCA'
    programs = ('orca',)
    uses_memory = True  # %maxcore
    # The single point after an optimisation is its final energy evaluation; frequencies start
    # with the analytical Hessian's response calculation or the numerical displacements.
    step_markers = {
        CalculationType.GEOMETRY_OPTIMISATION: re.compile('GEOMETRY OPTIMIZATION CYCLE'),
        CalculationType.SINGLE_POINT: re.compile('FINAL ENERGY EVALUATION AT THE STATIONARY POINT'),
        CalculationType.VIBRATIONAL_FREQUENCIES: re.compile(
            r'Nuclear geometric perturbations\s+\.\.\.\s+YES|ORCA NUMERICAL FREQUENCIES'
        ),
        CalculationType.EXCITED_STATES: EXCITED_STATES_START,
    }

    def __init__(self, executable: Optional[str] = None):
        # A user-configured path takes precedence over PATH.
        self.executable = executable

    # Detection

    def detect(self) -> EngineInfo:
        path = self.executable or shutil.which(self.programs[0])
        if path is None or not Path(path).is_file():
            return EngineInfo(found=False)
        path = str(Path(path))
        version = _version_from_path(path) or _version_from_banner(path)
        return EngineInfo(found=True, version=version, path=path)

    def capabilities(self) -> Capabilities:
        return CAPABILITIES

    # Input and output

    def input_text(self, sample, calculations, method, settings) -> str:
        return self.input_files(sample, calculations, method, settings)[self.input_file_name]

    def input_files(self, sample, calculations, method, settings) -> dict[str, str]:
        problem = self.system_problem(sample.periodic)
        if problem:
            raise ValueError(problem)
        steps = calculations.workflow()
        if not steps:
            raise ValueError('No calculation is selected.')
        excited = CalculationType.EXCITED_STATES in steps
        problem = excited and excited_states_problem(calculations.excited_states, sample, method)
        if problem:
            raise ValueError(problem)
        single_point = CalculationType.SINGLE_POINT in steps
        optimisation = CalculationType.GEOMETRY_OPTIMISATION in steps
        frequencies = CalculationType.VIBRATIONAL_FREQUENCIES in steps
        # A single point at the input geometry cannot share a job with the optimisation.
        separate_single_point = single_point and optimisation and calculations.single_point.geometry == 'input'
        print_orbitals = single_point and calculations.single_point.print_orbitals

        jobs = []
        if separate_single_point:
            jobs.append(_job(sample, method, settings, ['PrintMOs'] if print_orbitals else [], []))

        keywords, blocks = [], []
        ground_state = single_point or optimisation or frequencies
        if print_orbitals and not separate_single_point:
            keywords.append('PrintMOs')
        if optimisation:
            options = calculations.geometry_optimisation
            keywords.append(_OPT_KEYWORDS[options.convergence])
            blocks.append(_geom_block(options.max_steps, [i for i, atom in enumerate(sample.atoms) if atom.fixed]))
        if frequencies:
            options = calculations.vibrational_frequencies
            # Raman needs polarisability derivatives; ORCA's analytical route lacks them for
            # most functionals (B3LYP stops with an input error), the numerical one has them.
            numerical = options.type == 'numerical' or options.raman
            keywords.append('NumFreq' if numerical else 'Freq')
            blocks.append(f'%freq\n  Temp {options.temperature:g}\n  Pressure {options.pressure:g}\nend')
            if options.raman:
                blocks.append('%elprop\n  Polar 1\nend')
        if ground_state:
            jobs.append(_job(sample, method, settings, keywords, blocks))

        title = f'# EasyQM: {sample.name or "sample"} ({sample.formula}) - '
        ground = ', '.join(info(step).name for step in steps if step is not CalculationType.EXCITED_STATES)
        files = {self.input_file_name: title + ground + '\n' + '\n$new_job\n'.join(jobs)} if jobs else {}
        if excited:
            geometry = Path(self.input_file_name).with_suffix('.xyz').name if optimisation else ''
            text = _excited_job(sample, method, settings, calculations.excited_states, geometry)
            name = EXCITED_FILE_NAME if files else self.input_file_name
            files[name] = title + info(CalculationType.EXCITED_STATES).name + '\n' + text
        return files

    def commands(self, executable: str, input_names: list[str]) -> list[list[str]]:
        return [self.command(executable, Path(name)) for name in input_names]

    def succeeded(self, output: str) -> bool:
        return NORMAL_TERMINATION in output

    def parse(self, output: str) -> Results:
        return orca_output.parse(output)


def _method_keywords(method) -> list[str]:
    if method.family == 'HF':
        keywords = ['HF', _HF_REFERENCES[method.reference]]
    else:
        keywords = [method.functional]
        if method.dispersion != 'none':
            keywords.append(method.dispersion)
        keywords.append(method.reference)
    keywords += [method.basis_set, _AUXILIARY_KEYWORDS[method.auxiliary_basis]]
    if method.solvation != 'none':
        keywords.append(method.solvation)
    keywords += [_SCF_KEYWORDS[method.scf_convergence], method.integration_grid]
    return keywords


def excited_states_problem(options, sample, method) -> str:
    """Why ORCA cannot compute these excited states of the sample with the method, or ''."""
    if options.method == 'eom_ccsd':
        if method.reference == 'ROKS':
            return 'EOM-CCSD needs an RHF or UHF reference: choose RKS or UKS as the reference.'
        return ''
    if options.triplets and (method.reference != 'RKS' or sample.multiplicity > 1):
        return 'Triplet states need a closed-shell singlet with the RKS reference; untick triplets.'
    windowed = options.occupied_orbitals or options.virtual_orbitals
    if windowed and any(atomic_number(atom.element) >= _ECP_FROM for atom in sample.atoms):
        return ('Orbital counts need elements up to Kr: heavier ones have an effective core potential. '
                'Set both counts to 0.')
    return ''


def _excited_job(sample, method, settings, options, geometry_file: str) -> str:
    if options.method == 'eom_ccsd':
        # On the Hartree-Fock reference; RIJCOSX would need a correlation fitting basis.
        reference = replace(method, family='HF', auxiliary_basis='none')
        keywords = ['EOM-CCSD', 'FrozenCore' if options.frozen_core else 'NoFrozenCore']
        return _job(sample, reference, settings, keywords, [f'%mdci\n  NRoots {options.states}\nend'], geometry_file)
    return _job(sample, method, settings, [], [_tddft_block(sample, options)], geometry_file)


def _tddft_block(sample, options) -> str:
    lines = ['%tddft', f'  NRoots {options.states}', f'  TDA {"true" if options.tda else "false"}']
    if options.triplets:
        lines.append('  Triplets true')
    if options.occupied_orbitals or options.virtual_orbitals:
        # ORCA numbers orbitals from 0, per spin (OrbWin[1] is ignored for a closed shell);
        # -1 keeps its own first occupied or last virtual orbital.
        unpaired = sample.multiplicity - 1
        for spin, occupied in enumerate(((sample.electrons + unpaired) // 2, (sample.electrons - unpaired) // 2)):
            homo = occupied - 1
            first = max(homo - options.occupied_orbitals + 1, 0) if options.occupied_orbitals else -1
            last = homo + options.virtual_orbitals if options.virtual_orbitals else -1
            lines.append(f'  OrbWin[{spin}] = {first},-1,-1,{last}')
    return '\n'.join(lines + ['end'])


def _job(sample, method, settings, keywords: list[str], blocks: list[str], geometry_file: str = '') -> str:
    """One ORCA job: keyword line, memory and SCF blocks, the given blocks, coordinates (or the
    file an earlier job of the input writes them to)."""
    scf = [f'  MaxIter {method.scf_max_iterations}']
    if method.stability_check:
        scf.append('  STABPerform true')
    lines = [
        '! ' + ' '.join(_method_keywords(method) + keywords),
        f'%maxcore {int(settings.memory_gb * 1024 * _MAXCORE_SHARE)}',
        '%scf\n' + '\n'.join(scf) + '\nend',
        *blocks,
    ]
    if geometry_file:
        lines.append(f'* xyzfile {sample.charge} {sample.multiplicity} {geometry_file}')
    else:
        lines.append(f'* xyz {sample.charge} {sample.multiplicity}')
        lines += [f'  {atom.element:<2} {atom.x:14.8f} {atom.y:14.8f} {atom.z:14.8f}' for atom in sample.atoms]
        lines.append('*')
    return '\n'.join(lines) + '\n'


def _geom_block(max_steps: int, fixed: list[int]) -> str:
    lines = ['%geom', f'  MaxIter {max_steps}']
    if fixed:
        # Cartesian constraints on whole atoms; ORCA counts atoms from 0.
        lines += ['  Constraints', *(f'    {{C {index} C}}' for index in fixed), '  end']
    return '\n'.join(lines + ['end'])


def _version_from_path(path: str) -> str:
    """ORCA is usually unpacked into a folder named after its version (/opt/orca/6.0.1/orca)."""
    for part in reversed(Path(path).parent.parts):
        if _VERSION_FOLDER.match(part):
            return part
        match = re.search(r'orca[_-]?(\d+(?:[._]\d+)+)', part, re.IGNORECASE)
        if match:
            return match.group(1).replace('_', '.')
    return ''


def _version_from_banner(path: str) -> str:
    """ORCA prints its banner, with the version, before it complains about a missing input."""
    match = _VERSION_BANNER.search(banner([path, 'missing.inp']))
    return match.group(1) if match else ''
