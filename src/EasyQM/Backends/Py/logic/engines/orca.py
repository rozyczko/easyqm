# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""ORCA adapter: detection, the choices ORCA offers, input generation and the success check.

The whole workflow goes into one input file, so one ORCA process writes one output file:
optimisation and frequencies are keywords of the same job (ORCA runs the frequencies at the
optimised geometry), and the single point is the energy every job prints. Only a single
point at the *input* geometry before an optimisation needs a second job, joined with
``$new_job``.
"""

import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from ..calculations import CalculationType
from ..calculations import info
from ..runner import NO_WINDOW
from .base import Capabilities
from .base import EngineAdapter
from .base import EngineInfo

_VERSION_FOLDER = re.compile(r'^\d+(\.\d+)+$')
_VERSION_BANNER = re.compile(r'Program Version\s+(\d+(?:\.\d+)+)')
_VERSION_PROBE_TIMEOUT = 20  # s
NORMAL_TERMINATION = 'ORCA TERMINATED NORMALLY'

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


class OrcaAdapter(EngineAdapter):
    name = 'ORCA'

    def __init__(self, executable: Optional[str] = None):
        # A user-configured path takes precedence over PATH.
        self.executable = executable

    # Detection

    def detect(self) -> EngineInfo:
        path = self.executable or shutil.which('orca')
        if path is None or not Path(path).is_file():
            return EngineInfo(found=False)
        path = str(Path(path))
        version = _version_from_path(path) or _version_from_banner(path)
        return EngineInfo(found=True, version=version, path=path)

    def capabilities(self) -> Capabilities:
        return CAPABILITIES

    # Input and output

    def input_text(self, sample, calculations, method, settings) -> str:
        steps = calculations.workflow()
        if not steps:
            raise ValueError('No calculation is selected.')
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
        jobs.append(_job(sample, method, settings, keywords, blocks))

        title = f'# EasyQM: {sample.name or "sample"} ({sample.formula}) - ' + ', '.join(info(step).name for step in steps)
        return title + '\n' + '\n$new_job\n'.join(jobs)

    def succeeded(self, output: str) -> bool:
        return NORMAL_TERMINATION in output


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


def _job(sample, method, settings, keywords: list[str], blocks: list[str]) -> str:
    """One ORCA job: keyword line, memory and SCF blocks, the given blocks, coordinates."""
    scf = [f'  MaxIter {method.scf_max_iterations}']
    if method.stability_check:
        scf.append('  STABPerform true')
    lines = [
        '! ' + ' '.join(_method_keywords(method) + keywords),
        f'%maxcore {int(settings.memory_gb * 1024 * _MAXCORE_SHARE)}',
        '%scf\n' + '\n'.join(scf) + '\nend',
        *blocks,
        f'* xyz {sample.charge} {sample.multiplicity}',
        *(f'  {atom.element:<2} {atom.x:14.8f} {atom.y:14.8f} {atom.z:14.8f}' for atom in sample.atoms),
        '*',
    ]
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
    with tempfile.TemporaryDirectory(prefix='easyqm-') as folder:
        try:
            result = subprocess.run(
                [path, 'missing.inp'],
                cwd=folder,
                capture_output=True,
                text=True,
                errors='replace',
                timeout=_VERSION_PROBE_TIMEOUT,
                creationflags=NO_WINDOW,
            )
        except (OSError, subprocess.SubprocessError):
            return ''
    match = _VERSION_BANNER.search(result.stdout or '')
    return match.group(1) if match else ''
