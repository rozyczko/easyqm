# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Qt-free point group of a molecule, as a Schoenflies symbol ('C2v', 'D6h', 'D∞h').

The `pointgroup` package finds it from the principal axes of inertia and the symmetry
operations that map every atom onto an atom of its element, within 4°. Its time grows with
the square of the atom count, and a cubic or icosahedral molecule (CH4, SF6, C60) takes
about a second, so the caller should not ask more often than the structure changes.
"""

from pointgroup import PointGroup

from .sample import Atom

ATOM_LIMIT = 300  # about a second; larger structures are left undetermined
_SYMBOLS = {'Dinfh': 'D∞h', 'Cinfv': 'C∞v'}


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
