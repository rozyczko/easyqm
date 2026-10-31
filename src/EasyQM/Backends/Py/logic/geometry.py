# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Distances, angles and dihedrals between atoms (anything with x, y, z in Å)."""

import math
from typing import Optional

_TINY = 1e-8  # a vector shorter than this has no direction


def distance(first, second) -> float:
    return math.dist(_position(first), _position(second))


def angle(first, vertex, second) -> Optional[float]:
    """Angle first–vertex–second in degrees; None when an atom sits on the vertex."""
    u, v = _vector(vertex, first), _vector(vertex, second)
    lengths = _norm(u) * _norm(v)
    if lengths < _TINY:
        return None
    return math.degrees(math.acos(max(-1.0, min(1.0, _dot(u, v) / lengths))))


def dihedral(first, second, third, fourth) -> Optional[float]:
    """Torsion angle about second–third in degrees, -180 to 180, positive clockwise (IUPAC).

    None when three of the atoms are on a line, so a plane is not defined.
    """
    b1, b2, b3 = _vector(first, second), _vector(second, third), _vector(third, fourth)
    n1, n2 = _cross(b1, b2), _cross(b2, b3)
    if _norm(n1) < _TINY or _norm(n2) < _TINY:
        return None
    return math.degrees(math.atan2(_norm(b2) * _dot(b1, n2), _dot(n1, n2)))


def measure(atoms: list) -> Optional[tuple[str, Optional[float]]]:
    """('distance', Å), ('angle', °) at the middle atom or ('dihedral', °) for 2, 3 or 4 atoms
    in the given order; None for any other count."""
    if len(atoms) == 2:
        return 'distance', distance(*atoms)
    if len(atoms) == 3:
        return 'angle', angle(*atoms)
    if len(atoms) == 4:
        return 'dihedral', dihedral(*atoms)
    return None


def _position(atom) -> tuple[float, float, float]:
    return atom.x, atom.y, atom.z


def _vector(start, end) -> tuple[float, float, float]:
    return tuple(b - a for a, b in zip(_position(start), _position(end)))


def _dot(u, v) -> float:
    return sum(a * b for a, b in zip(u, v))


def _cross(u, v) -> tuple[float, float, float]:
    return (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])


def _norm(u) -> float:
    return math.hypot(*u)
