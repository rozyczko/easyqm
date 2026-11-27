# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Qt-free symmetry of a structure: the point group of a molecule, as a Schoenflies symbol
('C2v', 'D6h', 'D∞h'), and the space group of a crystal, as a short Hermann-Mauguin symbol
and its number ('Fm-3m', 225).

The `pointgroup` package finds a molecule's group from the principal axes of inertia and the
symmetry operations that map every atom onto an atom of its element, within 4°. Its time
grows with the square of the atom count, and a cubic or icosahedral molecule (CH4, SF6, C60)
takes about a second, so the caller should not ask more often than the structure changes.

spglib finds a crystal's group in the same way, with the lattice translations included,
within SPACE_GROUP_TOLERANCE. It is fast: milliseconds for the largest structures shown. It
reports the group of the atoms as they are, so it also finds the symmetry of a supercell's
parent cell, and the lower symmetry of a cell whose atoms were moved.
"""

from dataclasses import dataclass
from typing import Optional

import spglib
from pointgroup import PointGroup

from .elements import atomic_number
from .sample import Atom
from .sample import Cell

ATOM_LIMIT = 300  # about a second; larger structures are left undetermined
SPACE_GROUP_TOLERANCE = 1e-2  # Å; CIF files give coordinates to a few decimals
_SYMBOLS = {'Dinfh': 'D∞h', 'Cinfv': 'C∞v'}

# spglib 2.7 reports errors as exceptions only when asked to; from 3.0 it always will.
try:
    spglib.error.OLD_ERROR_HANDLING = False
except AttributeError:
    pass


@dataclass(frozen=True)
class SpaceGroup:
    symbol: str  # short Hermann-Mauguin symbol, 'Fm-3m'
    number: int  # 1 to 230

    @property
    def text(self) -> str:
        """'Fm-3m (225)'."""
        return f'{self.symbol} ({self.number})'


def point_group(atoms: list[Atom]) -> str:
    """The Schoenflies symbol; 'Kh' for a single atom, '' when not determined."""
    if len(atoms) == 1:
        return 'Kh'  # the package takes a lone atom for a linear molecule
    if not atoms or len(atoms) > ATOM_LIMIT:
        return ''
    try:
        group = PointGroup([(atom.x, atom.y, atom.z) for atom in atoms], [atom.element for atom in atoms])
        symbol = group.get_point_group()
    except Exception:  # the package raises nothing more specific
        return ''
    return _SYMBOLS.get(symbol, symbol)


def space_group(atoms: list[Atom], cell: Cell) -> Optional[SpaceGroup]:
    """The space group of the atoms in this cell; None when spglib finds none (atoms closer
    than the tolerance, for one)."""
    if not atoms:
        return None
    structure = _structure(atoms, cell)
    try:
        dataset = spglib.get_symmetry_dataset(structure, symprec=SPACE_GROUP_TOLERANCE)
    except spglib.error.SpglibError:
        return None
    if dataset is None:  # spglib before 2.7
        return None
    return SpaceGroup(dataset.international, dataset.number)


def primitive_count(atoms: list[Atom], cell: Cell) -> int:
    """How many primitive cells of the atoms this cell holds: 1 for a primitive cell, 4 for
    the conventional cell of an fcc lattice, 8 for a 2 × 2 × 2 supercell of a primitive cell;
    0 when spglib finds no primitive cell."""
    if not atoms:
        return 0
    try:
        primitive = spglib.find_primitive(_structure(atoms, cell), symprec=SPACE_GROUP_TOLERANCE)
    except spglib.error.SpglibError:
        return 0
    if primitive is None or not len(primitive[2]):
        return 0
    return round(len(atoms) / len(primitive[2]))


def _structure(atoms: list[Atom], cell: Cell) -> tuple:
    return (
        [list(vector) for vector in cell.vectors],
        [list(cell.fractional(atom.x, atom.y, atom.z)) for atom in atoms],
        [atomic_number(atom.element) for atom in atoms],
    )
