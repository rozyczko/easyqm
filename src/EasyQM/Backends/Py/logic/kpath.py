# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Qt-free high-symmetry paths through the Brillouin zone of a cell, for band structures.

The lattice is recognised from the cell's own vectors, which are taken as the primitive
cell: the job runs on them, so the bands belong to them. The paths and point names are those
of Setyawan and Curtarolo (Comput. Mater. Sci. 49, 299 (2010)), written in the fractional
coordinates of the cell's reciprocal vectors. A conventional cell of a centred lattice (the
8-atom cubic cell of silicon) is therefore treated as simple cubic, and shows the bands of
the primitive cell folded into its smaller zone; `folded_reason` says when that happens.

Lattices recognised: simple, face-centred (primitive, 60°) and body-centred (primitive,
109.47°) cubic; tetragonal, orthorhombic and hexagonal with any axis unique; rhombohedral.
Every other cell gets a general path through the face and corner centres of its reciprocal
cell.
"""

import math
from dataclasses import dataclass
from functools import cached_property

from .geometry import norm

Frac = tuple[float, float, float]

_LENGTH_TOLERANCE = 1e-3  # relative
_ANGLE_TOLERANCE = 0.05  # degrees
_BCC_ANGLE = math.degrees(math.acos(-1 / 3))  # 109.47°, between the primitive vectors
GAMMA = 'Γ'


@dataclass(frozen=True)
class KPath:
    lattice: str  # 'Simple cubic', … for the user
    points: dict[str, Frac]  # every named point, fractional in the cell's reciprocal vectors
    branches: tuple[tuple[str, ...], ...]  # continuous runs of named points; a jump between runs

    @property
    def text(self) -> str:
        """'Γ–X–M–Γ–R–X | M–R'."""
        return ' | '.join('–'.join(branch) for branch in self.branches)

    def label(self, k: Frac, tolerance: float = 2e-3) -> str:
        """The name of the nearest point within `tolerance` of `k`, or ''. Where two points
        are closer than that (B and Z of a rhombohedral cell near 90°) the tolerance shrinks
        below half their distance, so the samples between them stay unnamed."""
        tolerance = min(tolerance, self._separation / 4)
        name, distance = min(((name, _apart(k, point)) for name, point in self.points.items()),
                             key=lambda item: item[1], default=('', math.inf))
        return name if distance < tolerance else ''

    @cached_property
    def _separation(self) -> float:
        """The smallest distance between two distinct named points, per fractional coordinate."""
        points = list(self.points.values())
        distances = [_apart(a, b) for i, a in enumerate(points) for b in points[i + 1 :]]
        return min((d for d in distances if d > 1e-9), default=math.inf)


def band_path(cell) -> KPath:
    """The path for the lattice of this cell."""
    lengths, angles = cell.lengths, cell.angles
    right = [_same_angle(angle, 90) for angle in angles]
    equal = [_same_length(lengths[i], lengths[j]) for i, j in ((1, 2), (0, 2), (0, 1))]  # pair opposite each angle
    if all(right):
        if all(equal):
            return _standard('Simple cubic', _CUBIC)
        if any(equal):
            unique = equal.index(True)  # the axis opposite the equal pair
            return _permuted('Tetragonal', _TETRAGONAL, unique)
        order = sorted(range(3), key=lambda axis: lengths[axis])
        return _transformed('Orthorhombic', _ORTHORHOMBIC, [_unit(order.index(axis)) for axis in range(3)])
    hexagonal = _hexagonal(lengths, angles, right, equal)
    if hexagonal is not None:
        return hexagonal
    if all(equal) and _same_angle(angles[0], angles[1]) and _same_angle(angles[0], angles[2]):
        alpha = angles[0]
        if _same_angle(alpha, 60):
            return _standard('Face-centred cubic (primitive cell)', _FCC)
        if _same_angle(alpha, _BCC_ANGLE):
            return _standard('Body-centred cubic (primitive cell)', _BCC)
        return _rhombohedral(alpha)
    return _standard('General (no symmetry recognised)', _GENERAL)


def folded_reason(cell, path: KPath) -> str:
    """Why the bands of this cell are folded, or '': a conventional cell of a centred lattice."""
    centring = cell.space_group[:1]
    if centring not in ('F', 'I', 'A', 'B', 'C', 'R') or 'primitive' in path.lattice or 'Rhombohedral' in path.lattice:
        return ''
    return (f'The cell is the conventional cell of a centred lattice ({cell.space_group}), so the bands of its '
            'primitive cell appear folded. A primitive cell gives the textbook band structure.')


def path_kpoints(cell, path: KPath, points: int) -> list[tuple[Frac, int, str]]:
    """The vertices of the path with the number of points from each to the next, as pw.x's
    ``K_POINTS crystal_b`` reads them: about `points` in all, spread by length, at least two per
    line so that two named points in a row mark a jump."""
    reciprocal = cell.reciprocal
    lines = [(branch[i], branch[i + 1]) for branch in path.branches for i in range(len(branch) - 1)]
    lengths = [_distance(reciprocal, path.points[start], path.points[end]) for start, end in lines]
    total = sum(lengths) or 1.0
    counts = iter([max(2, round(points * length / total)) for length in lengths])
    vertices = []
    for branch in path.branches:
        for name in branch[:-1]:
            vertices.append((path.points[name], next(counts), name))
        vertices.append((path.points[branch[-1]], 1, branch[-1]))  # a jump, or the end
    return vertices


def cartesian(reciprocal, k: Frac) -> tuple[float, float, float]:
    """Å⁻¹, with the 2π factor."""
    return tuple(2 * math.pi * sum(k[i] * reciprocal[i][axis] for i in range(3)) for axis in range(3))


# Recognising the lattice


def _same_length(a: float, b: float) -> bool:
    return abs(a - b) <= _LENGTH_TOLERANCE * max(a, b)


def _same_angle(a: float, b: float) -> bool:
    return abs(a - b) <= _ANGLE_TOLERANCE


def _unit(axis: int) -> tuple[int, int, int]:
    return tuple(int(i == axis) for i in range(3))


def _hexagonal(lengths, angles, right, equal):
    """Two equal axes at 120° or 60°, the third at right angles to both."""
    for unique in range(3):
        others = [axis for axis in range(3) if axis != unique]
        if not (equal[unique] and right[others[0]] and right[others[1]]):
            continue
        gamma = angles[unique]
        # Rows: the cell's vectors in the standard vectors a1, a2 (at 120°) and c.
        rows = [None, None, None]
        rows[unique] = (0, 0, 1)
        rows[others[0]] = (1, 0, 0)
        if _same_angle(gamma, 120):
            rows[others[1]] = (0, 1, 0)
        elif _same_angle(gamma, 60):
            rows[others[1]] = (1, 1, 0)  # a1 + a2 is at 60° to a1
        else:
            return None
        return _transformed('Hexagonal', _HEXAGONAL, rows)
    return None


def _rhombohedral(alpha: float) -> KPath:
    cos_alpha = math.cos(math.radians(alpha))
    if alpha < 90:
        eta = (1 + 4 * cos_alpha) / (2 + 4 * cos_alpha)
        nu = 3 / 4 - eta / 2
        points = {
            GAMMA: (0, 0, 0), 'B': (eta, 0.5, 1 - eta), 'B₁': (0.5, 1 - eta, eta - 1), 'F': (0.5, 0.5, 0),
            'L': (0.5, 0, 0), 'L₁': (0, 0, -0.5), 'P': (eta, nu, nu), 'P₁': (1 - nu, 1 - nu, 1 - eta),
            'P₂': (nu, nu, eta - 1), 'Q': (1 - nu, nu, 0), 'X': (nu, 0, -nu), 'Z': (0.5, 0.5, 0.5),
        }
        branches = ((GAMMA, 'L', 'B₁'), ('B', 'Z', GAMMA, 'X'), ('Q', 'F', 'P₁', 'Z'), ('L', 'P'))
    else:
        eta = 1 / (2 * math.tan(math.radians(alpha) / 2) ** 2)
        nu = 3 / 4 - eta / 2
        points = {
            GAMMA: (0, 0, 0), 'F': (0.5, -0.5, 0), 'L': (0.5, 0, 0), 'P': (1 - nu, -nu, 1 - nu),
            'P₁': (nu, nu - 1, nu - 1), 'Q': (eta, eta, eta), 'Q₁': (1 - eta, -eta, -eta), 'Z': (0.5, -0.5, 0.5),
        }
        branches = ((GAMMA, 'P', 'Z', 'Q', GAMMA, 'F', 'P₁', 'Q₁', 'L', 'Z'),)
    return KPath('Rhombohedral', points, branches)


def _standard(lattice: str, table) -> KPath:
    points, branches = table
    return KPath(lattice, dict(points), branches)


def _permuted(lattice: str, table, unique: int) -> KPath:
    """A tetragonal table (c unique) for a cell whose `unique` axis is the different one."""
    others = iter((0, 1))
    standard = [2 if axis == unique else next(others) for axis in range(3)]
    return _transformed(lattice, table, [_unit(axis) for axis in standard])


def _transformed(lattice: str, table, rows) -> KPath:
    """The table's points for a cell whose vector i is Σ_j rows[i][j] × standard vector j: the
    fractional coordinate k·a_i follows the same sums."""
    points, branches = table
    moved = {name: tuple(sum(row[j] * k[j] for j in range(3)) + 0.0 for row in rows) for name, k in points.items()}
    return KPath(lattice, moved, branches)


def _apart(a: Frac, b: Frac) -> float:
    """The largest difference of fractional coordinates."""
    return max(abs(x - y) for x, y in zip(a, b))


def _distance(reciprocal, a: Frac, b: Frac) -> float:
    return norm(tuple(x - y for x, y in zip(cartesian(reciprocal, a), cartesian(reciprocal, b))))


# Setyawan–Curtarolo tables: points, then the path

_CUBIC = (
    {GAMMA: (0, 0, 0), 'X': (0, 0.5, 0), 'M': (0.5, 0.5, 0), 'R': (0.5, 0.5, 0.5)},
    ((GAMMA, 'X', 'M', GAMMA, 'R', 'X'), ('M', 'R')),
)
_FCC = (
    {GAMMA: (0, 0, 0), 'X': (0.5, 0, 0.5), 'W': (0.5, 0.25, 0.75), 'K': (0.375, 0.375, 0.75),
     'L': (0.5, 0.5, 0.5), 'U': (0.625, 0.25, 0.625)},
    ((GAMMA, 'X', 'W', 'K', GAMMA, 'L', 'U', 'W', 'L', 'K'), ('U', 'X')),
)
_BCC = (
    {GAMMA: (0, 0, 0), 'H': (0.5, -0.5, 0.5), 'N': (0, 0, 0.5), 'P': (0.25, 0.25, 0.25)},
    ((GAMMA, 'H', 'N', GAMMA, 'P', 'H'), ('P', 'N')),
)
_TETRAGONAL = (
    {GAMMA: (0, 0, 0), 'X': (0, 0.5, 0), 'M': (0.5, 0.5, 0), 'Z': (0, 0, 0.5), 'R': (0, 0.5, 0.5),
     'A': (0.5, 0.5, 0.5)},
    ((GAMMA, 'X', 'M', GAMMA, 'Z', 'R', 'A', 'Z'), ('X', 'R'), ('M', 'A')),
)
_ORTHORHOMBIC = (  # a < b < c
    {GAMMA: (0, 0, 0), 'X': (0.5, 0, 0), 'Y': (0, 0.5, 0), 'Z': (0, 0, 0.5), 'S': (0.5, 0.5, 0),
     'T': (0, 0.5, 0.5), 'U': (0.5, 0, 0.5), 'R': (0.5, 0.5, 0.5)},
    ((GAMMA, 'X', 'S', 'Y', GAMMA, 'Z', 'U', 'R', 'T', 'Z'), ('Y', 'T'), ('U', 'X'), ('S', 'R')),
)
_HEXAGONAL = (  # a1, a2 at 120°
    {GAMMA: (0, 0, 0), 'M': (0.5, 0, 0), 'K': (1 / 3, 1 / 3, 0), 'A': (0, 0, 0.5), 'L': (0.5, 0, 0.5),
     'H': (1 / 3, 1 / 3, 0.5)},
    ((GAMMA, 'M', 'K', GAMMA, 'A', 'L', 'H', 'A'), ('L', 'M'), ('K', 'H')),
)
_GENERAL = (  # the triclinic path: through Γ to the centres of the faces, edges and corners
    {GAMMA: (0, 0, 0), 'X': (0.5, 0, 0), 'Y': (0, 0.5, 0), 'Z': (0, 0, 0.5), 'L': (0.5, 0.5, 0),
     'M': (0, 0.5, 0.5), 'N': (0.5, 0, 0.5), 'R': (0.5, 0.5, 0.5)},
    (('X', GAMMA, 'Y'), ('L', GAMMA, 'Z'), ('N', GAMMA, 'M'), ('R', GAMMA)),
)
