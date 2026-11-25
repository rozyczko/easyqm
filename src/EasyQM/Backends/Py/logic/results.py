# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Qt-free, engine-agnostic results of a job (GENERAL_DESIGN.md, section 4, rule 2).

An adapter's `parse()` fills a `Results` from the engine output. Every field is optional:
what the output does not contain stays None, and the Summary page shows only what is there.
"""

import math
from dataclasses import dataclass
from dataclasses import field
from typing import Optional

from .geometry import angle
from .geometry import distance
from .sample import Atom
from .sample import Cell
from .sample import find_bonds

HARTREE_TO_KCAL_PER_MOL = 627.509474
EV_NM = 1239.84198  # photon energy in eV times its wavelength in nm
# Below this an excitation gets no wavelength: such a root is mostly the partner of a
# degenerate ground state that an open-shell reference splits, and would stretch the spectrum.
WAVELENGTH_FROM_EV = 1.0


@dataclass(frozen=True)
class Criterion:
    """One row of the optimiser's convergence table, as the engine reports it."""

    name: str
    value: float
    tolerance: float
    met: bool


@dataclass
class Optimisation:
    converged: bool
    cycles: int
    energies: list[float]  # Eh, one per evaluated geometry, in order
    initial: list[Atom]
    final: list[Atom]
    criteria: list[Criterion] = field(default_factory=list)  # of the last cycle
    final_cell: Optional[Cell] = None  # when the optimiser also changed the cell

    @property
    def energy_change(self) -> Optional[float]:
        """Final minus initial energy, Eh."""
        return self.energies[-1] - self.energies[0] if len(self.energies) > 1 else None


@dataclass(frozen=True)
class Mode:
    number: int  # the engine's mode number
    frequency: float  # cm-1; negative for an imaginary mode
    ir_intensity: Optional[float] = None  # km/mol
    raman_activity: Optional[float] = None  # Å^4/amu


@dataclass
class Frequencies:
    modes: list[Mode]  # vibrations only, without translations and rotations
    zero_point_energy: Optional[float] = None  # Eh
    gibbs_free_energy: Optional[float] = None  # Eh
    temperature: Optional[float] = None  # K
    pressure: Optional[float] = None  # atm

    @property
    def imaginary_count(self) -> int:
        return sum(mode.frequency < 0 for mode in self.modes)

    @property
    def has_ir(self) -> bool:
        """Γ phonons of a crystal come without IR intensities."""
        return any(mode.ir_intensity is not None for mode in self.modes)

    @property
    def has_raman(self) -> bool:
        return any(mode.raman_activity is not None for mode in self.modes)


@dataclass(frozen=True)
class Excitation:
    state: int  # the engine's state number
    energy: float  # eV, above the ground state
    multiplicity: Optional[int] = None  # of the excited state, when the engine says
    oscillator_strength: Optional[float] = None  # missing where the engine has no transition moments

    @property
    def wavelength(self) -> Optional[float]:
        """nm; None below `WAVELENGTH_FROM_EV`."""
        return EV_NM / self.energy if self.energy >= WAVELENGTH_FROM_EV else None


@dataclass
class ExcitedStates:
    method: str  # as the engine names it: 'TD-DFT/TDA', 'CIS', 'EOM-CCSD'
    states: list[Excitation]


# Levels of a crystal: channel (one, or spin up and down) -> k-point -> band energies in eV.
Levels = list[list[list[float]]]


@dataclass(frozen=True)
class BandEdge:
    energy: float  # eV
    k: int  # index of the k-point where the edge is
    band: int  # zero-based


@dataclass
class BandStructure:
    """Bands along the path: distances in Å⁻¹, one per k-point, starting again where `starts`
    says (a jump between two branches keeps the distance)."""

    distances: list[float]
    levels: Levels
    ticks: list[tuple[float, str]]  # (distance, name) of the named points; 'X|U' at a jump
    starts: list[int]  # first k-point of each branch
    filled: Optional[list[int]] = None  # filled bands per channel; None when a band is partly filled
    lattice: str = ''
    kpoints: list[tuple[float, float, float]] = field(default_factory=list)  # as the engine prints them

    def edges(self) -> Optional[tuple[BandEdge, BandEdge]]:
        """Valence band maximum and conduction band minimum along the path; None for a metal."""
        return band_edges(self.levels, self.filled)

    def same_point(self, first: int, second: int) -> bool:
        """Whether two k-points of the path are one point (Γ is passed more than once)."""
        if first == second:
            return True
        if len(self.kpoints) != len(self.distances):
            return False
        return all(abs(a - b) < 1e-6 for a, b in zip(self.kpoints[first], self.kpoints[second]))

    def location(self, k: int) -> str:
        """Where a k-point is on the path: 'Γ', or 'Γ–X' between two named points."""
        distance = self.distances[k]
        names = [name for x, name in self.ticks if abs(x - distance) < 1e-6]
        if names:
            # At a jump 'X|U' the first k-point is X, the next U.
            parts = names[0].split('|')
            return parts[-1] if k in self.starts else parts[0]
        before = [name for x, name in self.ticks if x < distance]
        after = [name for x, name in self.ticks if x > distance]
        if not before or not after:
            return ''
        return f'{before[-1].split("|")[-1]}–{after[0].split("|")[0]}'


@dataclass
class DensityOfStates:
    """The levels on the DOS k-point grid with their weights; the broadened curve is drawn
    from them, so the broadening can change without a new job."""

    levels: Levels
    weights: list[float]  # per k-point, as pw.x prints them: summing to 2 without spin, 1 per spin channel
    fermi_energy: Optional[float] = None  # eV
    filled: Optional[list[int]] = None

    def curve(self, energies: list[float], broadening: float) -> list[float]:
        """States per eV per cell at `energies`, each level a Gaussian of standard deviation
        `broadening` (eV)."""
        norm = 1 / (broadening * math.sqrt(2 * math.pi))
        reach = 5 * broadening
        values = [0.0] * len(energies)
        if not energies:
            return values
        start, step = energies[0], (energies[-1] - energies[0]) / max(len(energies) - 1, 1)
        for channel in self.levels:
            for k, levels in enumerate(channel):
                weight = self.weights[k % len(self.weights)] * norm
                for level in levels:
                    first = max(0, math.ceil((level - reach - start) / step)) if step else 0
                    last = min(len(energies) - 1, math.floor((level + reach - start) / step)) if step else 0
                    for i in range(first, last + 1):
                        x = (energies[i] - level) / broadening
                        values[i] += weight * math.exp(-0.5 * x * x)
        return values


def band_edges(levels: Levels, filled: Optional[list[int]]) -> Optional[tuple[BandEdge, BandEdge]]:
    """The highest filled and the lowest empty level over every channel and k-point; None when
    a band is partly filled, an empty band is missing or the two overlap (a metal)."""
    if filled is None or len(filled) != len(levels):
        return None
    valence = conduction = None
    for channel, count in zip(levels, filled):
        for k, energies in enumerate(channel):
            if count < 1 or len(energies) <= count:
                return None
            top, bottom = BandEdge(energies[count - 1], k, count - 1), BandEdge(energies[count], k, count)
            valence = top if valence is None or top.energy > valence.energy else valence
            conduction = bottom if conduction is None or bottom.energy < conduction.energy else conduction
    if valence is None or conduction.energy <= valence.energy:
        return None
    return valence, conduction


@dataclass
class Results:
    final_energy: Optional[float] = None  # Eh, the last energy of the job
    # eV; for a crystal the valence band maximum and the conduction band minimum
    homo: Optional[float] = None
    lumo: Optional[float] = None
    fermi_energy: Optional[float] = None  # eV, crystals with smearing only
    crystal: bool = False  # homo and lumo are band edges
    dipole: Optional[float] = None  # Debye
    optimisation: Optional[Optimisation] = None
    frequencies: Optional[Frequencies] = None
    excited_states: Optional[ExcitedStates] = None
    band_structure: Optional[BandStructure] = None
    density_of_states: Optional[DensityOfStates] = None

    @property
    def gap(self) -> Optional[float]:
        return self.lumo - self.homo if self.homo is not None and self.lumo is not None else None

    @property
    def empty(self) -> bool:
        return self == Results(crystal=self.crystal)


# Geometry comparison for the optimisation card


@dataclass(frozen=True)
class Bond:
    label: str  # 'C1–C2'
    initial: float  # Å
    final: float


@dataclass(frozen=True)
class Angle:
    label: str  # 'C1–C2–C3', the middle atom at the vertex
    initial: float  # degrees
    final: float


def atom_label(atoms: list[Atom], index: int) -> str:
    return f'{atoms[index].element}{index + 1}'


def bonds_and_angles(initial: list[Atom], final: list[Atom]) -> tuple[list[Bond], list[Angle]]:
    """Bond lengths and bond angles of the initial connectivity, in both geometries."""
    pairs = find_bonds(initial)
    bonds = [
        Bond(
            f'{atom_label(initial, i)}–{atom_label(initial, j)}',
            distance(initial[i], initial[j]),
            distance(final[i], final[j]),
        )
        for i, j in pairs
    ]
    neighbours: dict[int, list[int]] = {}
    for i, j in pairs:
        neighbours.setdefault(i, []).append(j)
        neighbours.setdefault(j, []).append(i)
    angles = []
    for vertex in sorted(neighbours):
        around = sorted(neighbours[vertex])
        for a, first in enumerate(around):
            for second in around[a + 1 :]:
                label = '–'.join(atom_label(initial, index) for index in (first, vertex, second))
                angles.append(Angle(label, _angle(initial, first, vertex, second), _angle(final, first, vertex, second)))
    return bonds, angles


def _angle(atoms: list[Atom], first: int, vertex: int, second: int) -> float:
    return angle(atoms[first], atoms[vertex], atoms[second])  # bonded atoms never coincide
