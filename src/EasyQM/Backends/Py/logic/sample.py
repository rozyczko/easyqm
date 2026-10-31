# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Qt-free sample state: the molecule the calculations are run on (GENERAL_DESIGN.md, 3.2).

Structures are read from XYZ files by `read_xyz`. Other formats (through ASE) can be added
next to it; `Sample` itself does not change.
"""

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Union

from .elements import COVALENT_RADII
from .elements import DEFAULT_COVALENT_RADIUS
from .elements import SYMBOLS
from .elements import atomic_number
from .geometry import distance

STRUCTURES_DIR = Path(__file__).resolve().parents[3] / 'Resources' / 'structures'

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
        return find_bonds(self.atoms)

    # Input

    def load_xyz(self, path: Union[str, Path]) -> None:
        """Replace the structure with the one in an XYZ file. On an error the sample is unchanged.

        XYZ holds no charge or spin, so the charge goes back to 0 and the multiplicity to the
        lowest one the electron count allows (singlet or doublet).
        """
        path = Path(path)
        try:
            atoms = read_xyz(path.read_text(encoding='utf-8'))
        except UnicodeDecodeError:
            raise ValueError('The file is not a text file.')
        self.atoms = atoms
        self.source = path.name
        self.name = path.stem
        self.periodic = False
        self.charge = 0
        electrons = sum(atomic_number(atom.element) for atom in atoms)
        self.multiplicity = 1 + electrons % 2


def read_xyz(text: str) -> list[Atom]:
    """Atoms of the first frame of an XYZ file, Cartesian coordinates in Å.

    The format: the atom count, a comment line, then one `element x y z` line per atom.
    The element may also be an atomic number or a label starting with the symbol ('C12',
    'Cl_a'); columns after z (extended XYZ: forces, charges, ...) are ignored, and so are
    any further frames. Labels are numbered in file order: C1, H2, ...
    """
    lines = text.splitlines()
    try:
        count = int(lines[0].split()[0])
    except (IndexError, ValueError):
        raise ValueError('The first line must be the number of atoms.')
    if count < 1:
        raise ValueError('The file declares no atoms.')
    body = lines[2 : 2 + count]
    if len(body) < count or not all(line.strip() for line in body):
        found = sum(1 for line in body if line.strip())
        raise ValueError(f'The file declares {count} atoms but holds {found}.')
    atoms = []
    for number, line in enumerate(body, start=1):
        fields = line.split()
        element = _element(fields[0])
        if element is None:
            raise ValueError(f'Atom {number}: "{fields[0]}" is not an element.')
        try:
            x, y, z = (float(field) for field in fields[1:4])
        except ValueError:
            raise ValueError(f'Atom {number}: expected "element x y z", got "{line.strip()}".')
        atoms.append(Atom(f'{element}{number}', element, x, y, z))
    return atoms


def _element(field: str) -> Union[str, None]:
    """'C', 'cl', 'CL', '6', 'C12', 'Cl_a' -> the element symbol, or None."""
    if field.isdigit():
        number = int(field)
        return SYMBOLS[number - 1] if 1 <= number <= len(SYMBOLS) else None
    letters = re.match(r'[A-Za-z]{1,2}', field)
    if letters is None:
        return None
    # Two letters first ('Cl' before 'C'), then one; a symbol is a capital and a small letter.
    for candidate in (letters.group(), letters.group()[0]):
        symbol = candidate.capitalize()
        if symbol in SYMBOLS:
            return symbol
    return None


def find_bonds(atoms: list[Atom]) -> list[tuple[int, int]]:
    """Atom index pairs closer than the scaled sum of their covalent radii."""
    pairs = []
    for i, first in enumerate(atoms):
        for j in range(i + 1, len(atoms)):
            second = atoms[j]
            cutoff = _BOND_TOLERANCE * (_radius(first.element) + _radius(second.element))
            if distance(first, second) < cutoff:
                pairs.append((i, j))
    return pairs


def _radius(element: str) -> float:
    return COVALENT_RADII.get(element, DEFAULT_COVALENT_RADIUS)
