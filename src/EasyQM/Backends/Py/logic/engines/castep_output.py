# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Reads the results of a CASTEP job (checked on CASTEP 26.11) from its output and run folder.

The output holds each run's log after a header line the runner writes (``==> job-dos: …``).
The log of ``job`` gives the energies, the optimisation trace and the convergence table; the
log of ``job-phonon`` the frequencies. The run folder gives what the log does not hold, or
not in the sample's order:

- ``job.cell``, written by the adapter: the input cell, and the atoms in the sample's order.
- ``job.geom``: one frame per accepted optimisation step, in atomic units. CASTEP lists the
  atoms by species, numbered within each species; the n-th atom of element X in ``job.cell``
  is CASTEP's ``X n``.
- ``job.bands``, ``job-bands.bands``, ``job-dos.bands``: the levels of the ground state, the
  path and the DOS grid, in Hartree, with the k-points in fractional coordinates.

Energies, one definition per case: the free energy E−TS with smearing, which the forces
belong to and which is pw.x's ``!`` energy; its dispersion-corrected form with dispersion;
and for an optimisation the LBFGS enthalpy, which includes the finite-basis correction and is
also each point of the trace. The other ``Final energy`` lines of an optimisation (trial
steps, the cut-offs of the finite-basis correction) are not read.

IR intensities are read only from a ``phonon+efield`` run: CASTEP prints the column for
finite displacement too, filled with zeros, blanks or noise. The first Γ table holds the TO
modes, which an IR spectrum shows; the LO modes of a polar crystal follow it and are not read.
"""

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..kpath import band_path
from ..kpath import path_axis
from ..results import BandStructure
from ..results import Criterion
from ..results import DensityOfStates
from ..results import Frequencies
from ..results import Levels
from ..results import Mode
from ..results import Optimisation
from ..results import Results
from ..results import sampled_band_edges
from ..sample import Atom
from ..sample import Cell
from .parsing import ANGSTROM_PER_BOHR
from .parsing import EV_PER_HARTREE
from .parsing import KM_PER_MOL_PER_IR_UNIT
from .parsing import NUMBER
from .parsing import block

_HEADER = re.compile(r'^==> (\S+): .*$', re.MULTILINE)
# In order of preference: the first that the log has is the final energy.
_ENERGIES = [re.compile(rf'^{text}\s*=\s*({NUMBER})', re.MULTILINE) for text in (
    r'Dispersion corrected final free energy\* \(Ecor-TS\)',
    r'Final free energy \(E-TS\)',
    r'Dispersion corrected final energy\*',
    r'Final energy',
)]
_ITERATION = re.compile(rf'LBFGS: finished iteration\s+\d+ with enthalpy=\s*({NUMBER})')
_FINAL_ENTHALPY = re.compile(rf'LBFGS: Final Enthalpy\s*=\s*({NUMBER})')
_OPTIMISATION = re.compile(r'type of calculation\s*:\s*geometry optimization')
_CONVERGED = 'Geometry optimization completed successfully'
_NOTHING_TO_OPTIMISE = 'there is nothing to optimise'
_CRITERIA_HEADER = r'\|\s*Parameter\s*\|\s*value'
_CRITERION = re.compile(rf'^\s*\|\s*(\S+)\s*\|\s*({NUMBER})\s*\|\s*({NUMBER})\s*\|\s*\S+\s*\|\s*(Yes|No)\s*\|')
_CRITERION_NAMES = {'dE/ion': 'Energy change (eV/atom)', '|F|max': 'Max. force (eV/Å)',
                    '|dR|max': 'Max. displacement (Å)', 'Smax': 'Max. stress (GPa)'}
_METALLIC = 'Treating system as metallic'
_EFIELD = 'Phonon followed by E-field'
_MODES_HEADER = r'^\s*\+\s+N\s+Frequency'
_MODE = re.compile(r'^\s*\+\s+(\d+)\s+(-?\d+\.\d+)\s+(?:[A-Za-z]\S*\s+)?(?:LO\s+)?(-?\d+\.\d+)?')
_SAME_FERMI = 1e-4  # Ha: two spin channels with one Fermi level


def read(folder: Optional[Path], output: str) -> Results:
    """The results of a job; without a run folder only what the logs hold."""
    parts = split_steps(output)
    job = parts.get('job', '' if parts else output)
    structure = _read_cell(folder / 'job.cell') if folder else None
    ground = _read_bands(folder / 'job.bands') if folder else None
    bands = _read_bands(folder / 'job-bands.bands') if folder and 'job-bands' in parts else None
    dos = _read_bands(folder / 'job-dos.bands') if folder and 'job-dos' in parts else None
    optimisation = _optimisation(job, structure, folder / 'job.geom' if folder else None)
    metallic = _METALLIC in job
    band_structure = _band_structure(bands, structure) if bands else None
    density_of_states = _density_of_states(dos, _fermi(dos) if metallic else None) if dos else None
    sources = [(part.levels, part.filled) for part in (ground, bands, dos) if part is not None]
    valence, conduction = sampled_band_edges(sources)
    return Results(
        final_energy=_final_energy(job, optimisation),
        homo=valence,
        lumo=conduction,
        fermi_energy=_fermi(dos or ground) if metallic else None,
        optimisation=optimisation,
        frequencies=_frequencies(parts.get('job-phonon', '')),
        crystal=True,
        band_structure=band_structure,
        density_of_states=density_of_states,
    )


def split_steps(output: str) -> dict[str, str]:
    """The text of each run by seed, from the header lines the runner writes; {} without any."""
    headers = list(_HEADER.finditer(output))
    ends = [match.start() for match in headers[1:]] + [len(output)]
    return {match.group(1): output[match.end():end] for match, end in zip(headers, ends)}


# Energies and the optimisation


def _final_energy(job: str, optimisation: Optional[Optimisation]) -> Optional[float]:
    if optimisation is not None and optimisation.energies:
        return optimisation.energies[-1]
    for pattern in _ENERGIES:
        values = pattern.findall(job)
        if values:
            return float(values[-1]) / EV_PER_HARTREE
    return None


def _optimisation(job: str, structure, geom: Optional[Path]) -> Optional[Optimisation]:
    if not _OPTIMISATION.search(job):
        return None
    initial = structure.atoms if structure else []
    if _NOTHING_TO_OPTIMISE in job:
        energy = _final_energy(job, None)
        return Optimisation(converged=True, cycles=0, energies=[energy] if energy is not None else [],
                            initial=initial, final=initial)
    energies = [float(value) / EV_PER_HARTREE for value in _ITERATION.findall(job)]
    final, final_cell = initial, None
    frame = _last_frame(geom) if structure and geom else None
    if frame is not None:
        final, final_cell = _final_geometry(structure, *frame)
    criteria = [Criterion(_CRITERION_NAMES.get(match.group(1), match.group(1)), float(match.group(2)),
                          float(match.group(3)), match.group(4) == 'Yes')
                for match in block(job.splitlines(), _CRITERIA_HEADER, _CRITERION)]
    return Optimisation(converged=_CONVERGED in job, cycles=len(energies), energies=energies, initial=initial,
                        final=final, criteria=criteria, final_cell=final_cell)


@dataclass
class _Structure:
    cell: Cell
    atoms: list[Atom]  # in the sample's order
    fractional: list[tuple[float, float, float]]


def _read_cell(path: Path) -> Optional[_Structure]:
    """The cell and atoms of a .cell file the adapter wrote (LATTICE_CART in Å, POSITIONS_FRAC)."""
    try:
        text = path.read_text(encoding='utf-8')
    except OSError:
        return None
    lattice, positions = _cell_block(text, 'LATTICE_CART'), _cell_block(text, 'POSITIONS_FRAC')
    vectors = [tuple(map(float, row)) for row in lattice if len(row) == 3]
    if len(vectors) != 3 or not positions:
        return None
    cell = Cell(tuple(vectors))
    fractional = [tuple(map(float, row[1:4])) for row in positions]
    atoms = [Atom(f'{row[0]}{i + 1}', row[0], *cell.cartesian(*k)) for i, (row, k) in enumerate(zip(positions, fractional))]
    return _Structure(cell, atoms, fractional)


def _cell_block(text: str, name: str) -> list[list[str]]:
    match = re.search(rf'^\s*%BLOCK\s+{name}\s*$(.*?)^\s*%ENDBLOCK\s+{name}', text, re.MULTILINE | re.DOTALL | re.IGNORECASE)
    if match is None:
        return []
    return [line.split('!')[0].split() for line in match.group(1).splitlines() if line.split('!')[0].strip()]


def _last_frame(path: Path) -> Optional[tuple[list[tuple[float, ...]], list[tuple[str, int, tuple[float, ...]]]]]:
    """(cell vectors, [(element, number within the element, position)]) of the last whole
    frame of a .geom file, in bohr; None without one."""
    try:
        lines = path.read_text(encoding='utf-8').splitlines()
    except OSError:
        return None
    frames, cell, atoms = [], [], []
    for line in lines:
        fields = line.split()
        if line.rstrip().endswith('<-- c'):
            cell, atoms = [], []
        elif line.rstrip().endswith('<-- h'):
            cell.append(tuple(map(float, fields[:3])))
        elif line.rstrip().endswith('<-- R'):
            atoms.append((fields[0], int(fields[1]), tuple(map(float, fields[2:5]))))
        elif not line.strip() and len(cell) == 3 and atoms:
            frames.append((cell, atoms))
            cell, atoms = [], []
    if len(cell) == 3 and atoms:
        frames.append((cell, atoms))
    return frames[-1] if frames else None


def _final_geometry(structure: _Structure, vectors, positions) -> tuple[list[Atom], Optional[Cell]]:
    """The frame's atoms in the sample's order, each moved by whole lattice vectors next to
    where it started; the frame's cell if it differs from the input one."""
    cell = Cell(tuple(tuple(value * ANGSTROM_PER_BOHR for value in vector) for vector in vectors))
    by_species = {(element, number): position for element, number, position in positions}
    counts, atoms = {}, []
    for atom, start in zip(structure.atoms, structure.fractional):
        counts[atom.element] = counts.get(atom.element, 0) + 1
        position = by_species.get((atom.element, counts[atom.element]))
        if position is None:
            return structure.atoms, None  # a frame of other atoms: leave the geometry alone
        k = cell.fractional(*(value * ANGSTROM_PER_BOHR for value in position))
        k = tuple(value - round(value - before) for value, before in zip(k, start))
        atoms.append(Atom(atom.label, atom.element, *cell.cartesian(*k)))
    changed = any(abs(a - b) > 1e-5 for new, old in zip(cell.vectors, structure.cell.vectors) for a, b in zip(new, old))
    return atoms, cell if changed else None


# Levels, bands and DOS


@dataclass
class _Bands:
    """A .bands file: k-points sorted by index, in fractional coordinates."""

    kpoints: list[tuple[float, float, float]]
    weights: list[float]  # summing to 1
    levels: Levels  # eV
    electrons: list[float]  # per spin channel; one value without spin
    fermi: list[float]  # eV, per spin channel
    cell: Cell

    @property
    def filled(self) -> Optional[list[int]]:
        """Filled bands per channel; None when a count is not whole (a partly filled band)."""
        counts = [self.electrons[0] / 2] if len(self.electrons) == 1 else self.electrons
        if any(abs(count - round(count)) > 1e-6 for count in counts):
            return None
        return [round(count) for count in counts]


def _read_bands(path: Path) -> Optional[_Bands]:
    """A whole .bands file; None if it is missing, cut short or holds a value that is not finite."""
    try:
        lines = path.read_text(encoding='utf-8').splitlines()
        kcount = int(_value(lines, 'Number of k-points')[0])
        spins = int(_value(lines, 'Number of spin components')[0])
        electrons = [float(value) for value in _value(lines, 'Number of electrons')]
        counts = [int(value) for value in _value(lines, 'Number of eigenvalues')]
        fermi = [float(value) * EV_PER_HARTREE for value in _value(lines, 'Fermi energ')]
        start = next(i for i, line in enumerate(lines) if line.startswith('Unit cell vectors'))
        cell = Cell(tuple(tuple(float(value) * ANGSTROM_PER_BOHR for value in lines[start + i].split()) for i in (1, 2, 3)))
    except (OSError, ValueError, StopIteration, IndexError):
        return None
    counts = counts * spins if len(counts) == 1 else counts
    kpoints = {}
    i = start + 4
    try:
        while i < len(lines):
            fields = lines[i].split()
            if not fields:
                i += 1
                continue
            index, k, weight = int(fields[1]), tuple(map(float, fields[2:5])), float(fields[5])
            i += 1
            channels = []
            for spin in range(spins):
                i += 1  # 'Spin component n'
                values = [float(line) * EV_PER_HARTREE for line in lines[i:i + counts[spin]]]
                if len(values) != counts[spin] or not all(map(math.isfinite, values)):
                    return None
                channels.append(values)
                i += counts[spin]
            kpoints[index] = (k, weight, channels)
    except (ValueError, IndexError):
        return None
    if len(kpoints) != kcount or len(electrons) != spins:
        return None
    ordered = [kpoints[index] for index in sorted(kpoints)]
    levels = [[channels[spin] for _, _, channels in ordered] for spin in range(spins)]
    return _Bands([k for k, _, _ in ordered], [w for _, w, _ in ordered], levels, electrons, fermi, cell)


def _value(lines: list[str], name: str) -> list[str]:
    """The numbers after a header line's name, 'Number of electrons  5.000  3.000'."""
    line = next(line for line in lines if line.startswith(name))
    return re.findall(r'-?\d+(?:\.\d+)?', line.split(')')[-1] if '(' in line else line[len(name):])


def _fermi(bands: Optional[_Bands]) -> Optional[float]:
    """The Fermi energy (eV); None when the two spin channels have their own, with the spin held."""
    if bands is None or not bands.fermi:
        return None
    if max(bands.fermi) - min(bands.fermi) > _SAME_FERMI * EV_PER_HARTREE:
        return None
    return bands.fermi[0]


def _band_structure(bands: _Bands, structure: Optional[_Structure]) -> BandStructure:
    """The levels along the path, named from the path of the input cell, which the k-point
    list was written for."""
    path = band_path(structure.cell if structure else bands.cell)
    distances, ticks, starts = path_axis(bands.kpoints, path, bands.cell.reciprocal)
    return BandStructure(distances, bands.levels, ticks, starts, bands.filled, path.lattice, bands.kpoints)


def _density_of_states(bands: _Bands, fermi: Optional[float]) -> DensityOfStates:
    # DensityOfStates weights sum to 2 without spin, as pw.x prints them, and to 1 per channel.
    scale = 2 if len(bands.levels) == 1 else 1
    return DensityOfStates(bands.levels, [weight * scale for weight in bands.weights], fermi, bands.filled)


# Frequencies


def _frequencies(text: str) -> Optional[Frequencies]:
    rows = block(text.splitlines(), _MODES_HEADER, _MODE, last=False)
    if not rows:
        return None
    efield = _EFIELD in text
    modes = [Mode(int(match.group(1)), float(match.group(2)),
                  float(match.group(3)) * KM_PER_MOL_PER_IR_UNIT if efield and match.group(3) else None)
             for match in rows]
    # CASTEP applies the acoustic sum rule at Γ, so the three modes nearest zero are the translations.
    acoustic = sorted(modes, key=lambda mode: abs(mode.frequency))[:3]
    return Frequencies(modes=[mode for mode in modes if mode not in acoustic])
