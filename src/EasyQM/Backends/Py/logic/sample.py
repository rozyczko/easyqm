# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Qt-free sample state: the molecule the calculations are run on (GENERAL_DESIGN.md, 3.2).

PoC1 reads one bundled XYZ file with a minimal reader. ASE replaces the reader when
"Load structure from file" is wired up; `Sample` itself does not change.
"""

import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Union

STRUCTURES_DIR = Path(__file__).resolve().parents[3] / 'Resources' / 'structures'

# Covalent radii in Å (Cordero et al. 2008), for the elements the bundled structures use.
_COVALENT_RADII = {
    'H': 0.31,
    'C': 0.76,
    'N': 0.71,
    'O': 0.66,
    'F': 0.57,
    'Si': 1.11,
    'P': 1.07,
    'S': 1.05,
    'Cl': 1.02,
}
_DEFAULT_COVALENT_RADIUS = 1.0
_BOND_TOLERANCE = 1.2


@dataclass
class Atom:
    label: str
    element: str
    x: float
    y: float
    z: float
    fixed: bool = False  # kept in place by the optimiser


class Sample:
    def __init__(self):
        self.reset()

    def reset(self) -> None:
        self.name = ''
        self.source = ''  # file the atoms came from, e.g. 'benzene.xyz'
        self.atoms: list[Atom] = []
        self.periodic = False
        self.charge = 0
        self.multiplicity = 1

    @classmethod
    def benzene(cls) -> 'Sample':
        sample = cls()
        sample.load_xyz(STRUCTURES_DIR / 'benzene.xyz')
        return sample

    # Derived

    @property
    def atom_count(self) -> int:
        return len(self.atoms)

    @property
    def formula(self) -> str:
        """Hill order: C, then H, then the rest alphabetically; count omitted when 1."""
        counts = Counter(atom.element for atom in self.atoms)
        ordered = [element for element in ('C', 'H') if element in counts]
        ordered += sorted(element for element in counts if element not in ('C', 'H'))
        return ''.join(f'{element}{counts[element] if counts[element] > 1 else ""}' for element in ordered)

    @property
    def summary(self) -> str:
        return ' · '.join(part for part in (self.source, self.formula, f'{self.atom_count} atoms') if part)

    @property
    def fixed_count(self) -> int:
        return sum(atom.fixed for atom in self.atoms)

    def bonds(self) -> list[tuple[int, int]]:
        """Atom index pairs closer than the scaled sum of their covalent radii."""
        pairs = []
        for i, first in enumerate(self.atoms):
            for j in range(i + 1, len(self.atoms)):
                second = self.atoms[j]
                cutoff = _BOND_TOLERANCE * (_radius(first.element) + _radius(second.element))
                if _distance(first, second) < cutoff:
                    pairs.append((i, j))
        return pairs

    # Input

    def load_xyz(self, path: Union[str, Path]) -> None:
        """Read a plain XYZ file: atom count, comment line, then `element x y z` per line."""
        path = Path(path)
        lines = path.read_text(encoding='utf-8').splitlines()
        try:
            count = int(lines[0].strip())
        except (IndexError, ValueError):
            raise ValueError(f'"{path}" is not an XYZ file: the first line is not an atom count.')
        body = lines[2 : 2 + count]
        if len(body) < count:
            raise ValueError(f'"{path}" declares {count} atoms but holds {len(body)}.')
        atoms = []
        for number, line in enumerate(body, start=1):
            fields = line.split()
            if len(fields) < 4:
                raise ValueError(f'"{path}", atom {number}: expected "element x y z", got "{line.strip()}".')
            element = fields[0].capitalize()
            try:
                x, y, z = (float(field) for field in fields[1:4])
            except ValueError:
                raise ValueError(f'"{path}", atom {number}: coordinates are not numbers.')
            atoms.append(Atom(f'{element}{number}', element, x, y, z))
        self.atoms = atoms
        self.source = path.name
        self.name = path.stem


def _radius(element: str) -> float:
    return _COVALENT_RADII.get(element, _DEFAULT_COVALENT_RADIUS)


def _distance(first: Atom, second: Atom) -> float:
    return math.dist((first.x, first.y, first.z), (second.x, second.y, second.z))
