# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Qt-free Z-matrix of a molecule: every atom placed by a bond length to an earlier atom, a bond
angle with a second one and a dihedral with a third. chemcoord converts between the Z-matrix
and Cartesian coordinates, and picks the reference atoms from the bonds.

chemcoord places the first atoms relative to the origin and the axes (references 'origin',
'e_x', 'e_y', 'e_z') where a textbook Z-matrix leaves the values out; that keeps the molecule
in place when a value changes. These absolute references are reported as no reference (None).

Dihedrals follow IUPAC, positive clockwise, as `geometry.dihedral` and the engines do;
chemcoord's have the opposite sign.

chemcoord, with pandas and numba, is imported on first use: that takes a few seconds.
"""

import math
from dataclasses import dataclass
from typing import Optional

from .geometry import Vec

FIELDS = ('bond', 'angle', 'dihedral')
_REFERENCE_COLUMNS = {'bond': 'b', 'angle': 'a', 'dihedral': 'd'}
_LINEAR_MESSAGE = 'No Z-matrix: the molecule is linear, so its dihedrals are undefined.'


@dataclass
class ZRow:
    atom: int  # index into the sample's atoms
    references: tuple[Optional[int], Optional[int], Optional[int]]  # of bond, angle, dihedral; None: absolute
    values: tuple[float, float, float]  # bond in Å, angle and dihedral in degrees

    def value(self, field: str) -> float:
        return self.values[FIELDS.index(field)]

    def reference(self, field: str) -> Optional[int]:
        return self.references[FIELDS.index(field)]


class ZMatrix:
    """The Z-matrix of `atoms` (with element, x, y, z), in construction order.

    `construction` is the `construction` of an earlier Z-matrix of the same atoms: kept, the
    rows keep their order and references while the atoms move. It is replaced when it no
    longer defines the atoms, e.g. when three of its reference atoms came onto a line.

    :raises ValueError: when no Z-matrix can be built (a linear molecule of four atoms or more).
    """

    def __init__(self, atoms: list, construction=None):
        self._count = len(atoms)
        self._zmat = _build(atoms, construction)
        table = self._zmat.loc[:, ['b', 'bond', 'a', 'angle', 'd', 'dihedral']]
        self.rows = [_row(atom, table.loc[atom]) for atom in table.index]
        self._by_atom = {row.atom: row for row in self.rows}

    @property
    def construction(self):
        """chemcoord's construction table: the reference atoms of every atom, in order."""
        return self._zmat.loc[:, ['b', 'a', 'd']].copy()

    def row(self, atom: int) -> ZRow:
        return self._by_atom[atom]

    def positions_with(self, atom: int, field: str, value: float) -> list[Vec]:
        """Cartesian positions of all atoms, in atom order, after setting one value: `atom`
        moves, and with it every atom placed from it. The others stay where they are.

        :raises ValueError: for a value out of range, a value with an absolute reference, or
            one that leaves later atoms undefined (an angle of 180° that one of them hangs on).
        """
        if field not in FIELDS or atom not in self._by_atom:
            raise ValueError(f'No {field} for atom {atom}.')
        if self._by_atom[atom].reference(field) is None:
            raise ValueError(f'The {field} of this atom is not defined by other atoms.')
        if not math.isfinite(value):
            raise ValueError('The value must be a number.')
        if field == 'bond' and value <= 0:
            raise ValueError('A bond length must be positive.')
        if field == 'angle' and not 0 < value <= 180:
            raise ValueError('A bond angle must lie above 0° and up to 180°.')
        zmat = self._zmat.copy()
        # unsafe_loc: chemcoord's safe_loc would add dummy atoms for a linear angle.
        zmat.unsafe_loc[atom, field] = -value if field == 'dihedral' else value
        try:
            cartesian = zmat.get_cartesian()
            positions = cartesian.loc[list(range(self._count)), ['x', 'y', 'z']].to_numpy(dtype=float)
        except Exception as error:  # chemcoord raises several kinds for undefined positions
            raise ValueError(f'This value leaves the other atoms undefined ({error}).')
        if len(cartesian) != self._count or not all(math.isfinite(value) for value in positions.flat):
            raise ValueError('This value leaves the other atoms undefined.')
        return [tuple(float(value) for value in position) for position in positions]


def _build(atoms: list, construction):
    chemcoord, pandas = _chemcoord()
    cartesian = chemcoord.Cartesian(
        pandas.DataFrame(
            {
                'atom': [atom.element for atom in atoms],
                'x': [float(atom.x) for atom in atoms],
                'y': [float(atom.y) for atom in atoms],
                'z': [float(atom.z) for atom in atoms],
            }
        )
    )
    zmat = _with_construction(cartesian, construction, len(atoms))
    if zmat is not None:
        return zmat
    try:
        zmat = cartesian.get_zmat()
    except chemcoord.exceptions.UndefinedCoordinateSystem:
        raise ValueError(_LINEAR_MESSAGE)
    except Exception as error:
        raise ValueError(f'No Z-matrix: {error}')
    if not _defined(zmat):
        raise ValueError(_LINEAR_MESSAGE)
    return zmat


def _with_construction(cartesian, construction, count: int):
    """The Z-matrix on the kept references; None without them, or when they no longer work
    (chemcoord then picks new ones)."""
    if construction is None or len(construction) != count:
        return None
    try:
        zmat = cartesian.get_zmat(construction_table=construction)
    except Exception:  # chemcoord raises several kinds for references that no longer work
        return None
    return zmat if _defined(zmat) else None


def _defined(zmat) -> bool:
    return all(math.isfinite(value) for value in zmat.loc[:, ['bond', 'angle', 'dihedral']].to_numpy(dtype=float).flat)


def _row(atom, values) -> ZRow:
    references = tuple(_reference(values[_REFERENCE_COLUMNS[field]]) for field in FIELDS)
    bond, angle, dihedral = (float(values[field]) for field in FIELDS)
    # IUPAC sign; + 0.0 turns chemcoord's -0.0 into 0.0.
    return ZRow(int(atom), references, (bond + 0.0, angle + 0.0, -dihedral + 0.0))


def _reference(value) -> Optional[int]:
    """An atom index, or None for chemcoord's 'origin', 'e_x', 'e_y', 'e_z'."""
    return None if isinstance(value, str) else int(value)


def _chemcoord():
    try:
        import chemcoord
        import pandas
    except ImportError:
        raise ValueError('The Z-matrix needs the chemcoord package.')
    return chemcoord, pandas
