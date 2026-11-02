# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Qt-free, engine-agnostic results of a job (GENERAL_DESIGN.md, section 4, rule 2).

An adapter's `parse()` fills a `Results` from the engine output. Every field is optional:
what the output does not contain stays None, and the Summary page shows only what is there.
"""

from dataclasses import dataclass
from dataclasses import field
from typing import Optional

from .geometry import angle
from .geometry import distance
from .sample import Atom
from .sample import Cell
from .sample import find_bonds

HARTREE_TO_KCAL_PER_MOL = 627.509474


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
