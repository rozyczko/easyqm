# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Quantum ESPRESSO adapter: plane-wave DFT of crystals with pw.x (checked on QE 7.5).

A single point is a pw.x `scf` run, an optimisation `relax` or `vc-relax`, whose first SCF
is the energy at the input geometry and whose last is the one at the optimised geometry.
Vibrational frequencies are the phonons at Γ: ph.x on the ground state pw.x left behind, then
dynmat.x, which imposes the acoustic sum rule so that the three acoustic modes are zero.

A band structure and a density of states are two more pw.x runs on the ground state the
first left behind, both with ``verbosity = 'high'`` so that every level is printed: a
``bands`` run along the high-symmetry path of `logic.kpath`, and an ``nscf`` run with
tetrahedra on a denser grid, whose levels the DOS is drawn from. They take the geometry from
the saved ground state, so they follow an optimisation, and they run last because they
overwrite that state, which ph.x reads. Every program writes to the one output file.

ph.x and dynmat.x are found next to pw.x, with its prefix swapped: pw.exe gives ph.exe and
dynmat.exe on Windows, pw.x gives ph.x and dynmat.x elsewhere.

Pseudopotentials come from one folder, found as pw.x looks for it (``ESPRESSO_PSEUDO``,
then ``~/espresso/pseudo``) or as ``pseudo`` next to the ``bin`` folder of pw.x. It holds
one UPF file per element, named after the element (``Si.us.pbe…upf``,
``si_pbe_v1.uspp.F.UPF``), and ``cutoffs.json`` with the recommended cutoffs per element
(``{"Si": {"cutoff_wfc": 30, "cutoff_rho": 240}, …}``, the SSSP convention). A job uses
the largest cutoffs among its elements.
"""

import json
import math
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..calculations import CalculationType
from ..calculations import info
from ..kpath import band_path
from ..kpath import path_kpoints
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
# Band structure and density of states: two more pw.x runs on the ground state.
BANDS_FILE_NAME = 'bands.in'
DOS_FILE_NAME = 'dos.in'
# The program of each input after the first; 'pw' is pw.x itself.
_PROGRAMS = {PHONON_FILE_NAME: 'ph', DYNMAT_FILE_NAME: 'dynmat', BANDS_FILE_NAME: 'pw', DOS_FILE_NAME: 'pw'}

CAPABILITIES = Capabilities(
    families=(('DFT', 'DFT'),),
    # The functional is the one the pseudopotentials were made with; pw.x reads it from them.
    functionals=(('PBE', 'PBE'),),
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
_SMEARING = ["occupations = 'smearing'", "smearing = 'cold'", f'degauss = {_DEGAUSS:g}']
_Z_VALENCE = re.compile(r'z_valence\s*=\s*"\s*([-+.\deE]+)"|([-+.\deE]+)\s+Z valence')


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
        # Printed by the DOS run too, after the DOS marker, which then wins.
        CalculationType.BAND_STRUCTURE: re.compile('Band Structure Calculation'),
        CalculationType.DENSITY_OF_STATES: quantum_espresso_output.TETRAHEDRA,
    }
    # pw.x ends normally after an SCF that did not converge, so ph.x starts and fails.
    failure_marker = re.compile(NOT_CONVERGED)
    raman = False

    def __init__(self, executable: Optional[str] = None):
        self.executable = executable
        # Set by `detect`, next to the executable it finds.
        self.pseudo_folder: Optional[Path] = None

    # Detection

    def detect(self) -> EngineInfo:
        path = self.executable or next(filter(None, map(shutil.which, self.programs)), None)
        if path is None or not Path(path).is_file():
            self.pseudo_folder = None
            return EngineInfo(found=False)
        path = str(Path(path))
        self.pseudo_folder = _pseudo_folder(Path(path))
        match = _VERSION_BANNER.search(banner([path, '-i', 'missing.in']))
        detail = f'pseudopotentials in {self.pseudo_folder}' if self.pseudo_folder else 'no pseudopotential folder'
        return EngineInfo(found=True, version=match.group(1) if match else '', path=path, detail=detail)

    def capabilities(self) -> Capabilities:
        return CAPABILITIES

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

    # Input and output

    def input_text(self, sample, calculations, method, settings) -> str:
        steps = self._check(sample, calculations)
        optimisation = calculations.geometry_optimisation if CalculationType.GEOMETRY_OPTIMISATION in steps else None
        calculation, control, namelists = 'scf', [], []
        if optimisation is not None:
            calculation = 'vc-relax' if optimisation.optimise == 'positions_and_cell' else 'relax'
            energy, force = _RELAX_THRESHOLDS[optimisation.convergence]
            control = [f'etot_conv_thr = {energy:g}', f'forc_conv_thr = {force:g}', f'nstep = {optimisation.max_steps}']
            namelists = _namelist('ions', [])
            if calculation == 'vc-relax':
                namelists += _namelist('cell', ["cell_dofree = 'all'"])
        if method.occupations == 'fixed':
            occupations = ["occupations = 'fixed'", f'nbnd = {self._filled_bands(sample, method) + _EMPTY_BANDS}']
        else:
            occupations = _SMEARING
        grid = method.kpoints.for_cell(sample.cell)
        return self._pw_input(
            sample,
            method,
            ', '.join(info(step).name for step in steps),
            _Run(calculation, control, occupations, namelists, ['K_POINTS automatic', _grid_line(grid)]),
            # Fixed atoms break symmetries pw.x finds at the start, and it stops when they go.
            nosym=optimisation is not None and any(atom.fixed for atom in sample.atoms),
        )

    def input_files(self, sample, calculations, method, settings) -> dict[str, str]:
        files = {self.input_file_name: self.input_text(sample, calculations, method, settings)}
        steps = calculations.workflow()
        if CalculationType.VIBRATIONAL_FREQUENCIES in steps:
            files[PHONON_FILE_NAME] = PHONON_INPUT_INSULATOR if method.occupations == 'fixed' else PHONON_INPUT
            files[DYNMAT_FILE_NAME] = DYNMAT_INPUT
        if CalculationType.BAND_STRUCTURE in steps:
            files[BANDS_FILE_NAME] = self._bands_input(sample, calculations.band_structure, method)
        if CalculationType.DENSITY_OF_STATES in steps:
            files[DOS_FILE_NAME] = self._dos_input(sample, calculations.density_of_states, method)
        return files

    def _check(self, sample, calculations) -> list[CalculationType]:
        """The workflow, or why there is no input for it."""
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
        return steps

    def _bands_input(self, sample, options, method) -> str:
        """The levels along the path; the named points are comments, for the reader."""
        path = band_path(sample.cell)
        vertices = path_kpoints(sample.cell, path, options.points)
        kpoints = ['K_POINTS crystal_b', f'  {len(vertices)}']
        kpoints += [f'  {k[0]:12.8f} {k[1]:12.8f} {k[2]:12.8f}  {count:4d}  ! {name}' for k, count, name in vertices]
        bands = self._filled_bands(sample, method, majority=True) + options.empty_bands
        run = _Run('bands', ["verbosity = 'high'"], [*_SMEARING, f'nbnd = {bands}'], [], kpoints)
        return self._pw_input(sample, method, f'Band structure ({path.text})', run, diagonalise_fully=True)

    def _dos_input(self, sample, options, method) -> str:
        """The levels on a denser grid; tetrahedra give the Fermi energy of that grid."""
        grid = [n * options.grid_factor for n in method.kpoints.for_cell(sample.cell)]
        bands = self._filled_bands(sample, method, majority=True) + options.empty_bands
        run = _Run('nscf', ["verbosity = 'high'"], ["occupations = 'tetrahedra'", f'nbnd = {bands}'], [],
                   ['K_POINTS automatic', _grid_line(grid)])
        return self._pw_input(sample, method, 'Density of states', run, diagonalise_fully=True)

    def _filled_bands(self, sample, method, majority: bool = False) -> int:
        """Bands the valence electrons fill; with `majority` and spin, those of the spin-up channel."""
        elements = sorted({atom.element for atom in sample.atoms})
        pseudopotentials = find_pseudopotentials(self.pseudo_folder, elements)
        electrons = sum(_valence(self.pseudo_folder / pseudopotentials[atom.element]) for atom in sample.atoms)
        electrons -= sample.charge
        if majority and method.reference == 'UKS':
            electrons += sample.multiplicity - 1
        return math.ceil(electrons / 2)

    def _pw_input(self, sample, method, steps_text: str, run: '_Run', nosym=False, diagonalise_fully=False) -> str:
        """One pw.x input: what every run of the workflow shares, around what `run` changes."""
        elements = sorted({atom.element for atom in sample.atoms})
        pseudopotentials = find_pseudopotentials(self.pseudo_folder, elements)
        cutoff_wfc, cutoff_rho = cutoffs(self.pseudo_folder, elements)
        control = [
            f"calculation = '{run.calculation}'",
            "prefix = 'job'",
            "outdir = './tmp'",
            f"pseudo_dir = '{self.pseudo_folder.as_posix()}'",
            *run.control,
        ]
        system = [
            'ibrav = 0',
            f'nat = {sample.atom_count}',
            f'ntyp = {len(elements)}',
            f'ecutwfc = {cutoff_wfc:g}',
            f'ecutrho = {cutoff_rho:g}',
            *run.occupations,
        ]
        if nosym:
            system.append('nosym = .true.')
        if sample.charge:
            system.append(f'tot_charge = {sample.charge}')
        if method.reference == 'UKS':
            system += ['nspin = 2', f'tot_magnetization = {sample.multiplicity - 1}']
        if method.dispersion != 'none':
            system += ["vdw_corr = 'dft-d3'", f'dftd3_version = {_DFTD3_VERSIONS[method.dispersion]}']
        scf = [f'conv_thr = {_CONV_THR[method.scf_convergence]:g}', f'electron_maxstep = {method.scf_max_iterations}']
        if diagonalise_fully:
            scf.append('diago_full_acc = .true.')  # empty bands as accurate as the filled ones

        lines = [f'! EasyQM: {sample.name or "sample"} ({sample.formula}) - {steps_text}']
        lines += _namelist('control', control) + _namelist('system', system) + _namelist('electrons', scf)
        lines += run.namelists
        lines.append('ATOMIC_SPECIES')
        lines += [f'  {element:<2} {_mass(element):10.4f}  {pseudopotentials[element]}' for element in elements]
        lines.append('CELL_PARAMETERS angstrom')
        lines += [f'  {x:14.8f} {y:14.8f} {z:14.8f}' for x, y, z in sample.cell.vectors]
        lines.append('ATOMIC_POSITIONS angstrom')
        lines += [
            f'  {atom.element:<2} {atom.x:14.8f} {atom.y:14.8f} {atom.z:14.8f}' + ('  0 0 0' if atom.fixed else '')
            for atom in sample.atoms
        ]
        return '\n'.join(lines + run.kpoints) + '\n'

    def command(self, executable: str, input_path: Path) -> list[str]:
        return [executable, '-i', input_path.name]

    def commands(self, executable: str, input_names: list[str]) -> list[list[str]]:
        commands = [self.command(executable, Path(input_names[0]))]
        for name in input_names[1:]:
            if _PROGRAMS[name] == 'pw':
                commands.append(self.command(executable, Path(name)))
                continue
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


@dataclass(frozen=True)
class _Run:
    """What one pw.x run of the workflow sets differently from the others."""

    calculation: str  # 'scf', 'relax', 'vc-relax', 'bands', 'nscf'
    control: list[str]  # &control entries after the shared ones
    occupations: list[str]  # &system entries
    namelists: list[str]  # &ions, &cell
    kpoints: list[str]  # the K_POINTS card


def _grid_line(grid) -> str:
    return f'  {grid[0]} {grid[1]} {grid[2]}  0 0 0'


def _namelist(name: str, entries: list[str]) -> list[str]:
    return [f'&{name}', *(f'  {entry}' for entry in entries), '/']


def _mass(element: str) -> float:
    """Atomic mass in u; pw.x needs one per species, though only dynamics and phonons use it."""
    try:
        import gemmi
    except ImportError:
        raise ValueError('Writing a Quantum ESPRESSO input needs the gemmi package.') from None
    return gemmi.Element(element).weight
