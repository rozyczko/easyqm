# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""What the structure viewer draws: atoms, bonds and cell edges (PERIODIC-DESIGN.md, 3.3).

One scene for molecules and crystals, so the viewer does not tell them apart. A molecule is
a scene without a cell. A crystal is a block of na × nb × nc cells; with boundary atoms,
an atom on a face of the block is also drawn on the opposite face, as crystal viewers do.
"""

import itertools
import math
from dataclasses import dataclass

from .geometry import Vec
from .sample import Sample
from .sample import find_bonds

Image = tuple[int, int, int]  # lattice translation in cells

HOME: Image = (0, 0, 0)  # the atom in the cell itself

_ON_FACE = 1e-3  # fractional distance from a face that counts as on it


@dataclass(frozen=True)
class SceneAtom:
    atom: int  # index into sample.atoms: selection, tables, labels
    element: str
    x: float  # Å, where it is drawn
    y: float
    z: float
    image: Image = HOME


@dataclass
class Scene:
    atoms: list[SceneAtom]
    bonds: list[tuple[int, int]]  # indices into atoms
    # 12 segments for a crystal, [] for a molecule. Edges 0, 4 and 8 start at the origin and
    # run along a, b and c.
    cell_edges: list[tuple[Vec, Vec]]
    centre: Vec  # what the view turns about
    extent: float  # Å from the centre to the farthest atom or cell corner


def place(sample: Sample, index: int, image: Image = HOME) -> SceneAtom:
    """Atom `index` of the sample, moved by `image` cells."""
    atom = sample.atoms[index]
    position = (atom.x, atom.y, atom.z)
    if image != HOME:
        position = _add(position, sample.cell.cartesian(*image))
    return SceneAtom(index, atom.element, *position, image)


def build_scene(sample: Sample, repeat: Image = (1, 1, 1), boundary_atoms: bool = True) -> Scene:
    if not sample.periodic:
        atoms = [place(sample, index) for index in range(sample.atom_count)]
        positions = [_position(atom) for atom in atoms]
        centre = tuple(sum(axis) / len(positions) for axis in zip(*positions)) if positions else (0.0, 0.0, 0.0)
        extent = max((math.dist(position, centre) for position in positions), default=0.0)
        return Scene(atoms, find_bonds(atoms), [], centre, extent)

    cell = sample.cell
    atoms = []
    for index, atom in enumerate(sample.atoms):
        # Atoms are wrapped into the cell (`Sample.load`), so a face atom is at 0, never at 1.
        fractional = cell.fractional(atom.x, atom.y, atom.z)
        cells = [
            list(range(count)) + ([count] if boundary_atoms and abs(value) < _ON_FACE else [])
            for value, count in zip(fractional, repeat)
        ]
        atoms += [place(sample, index, image) for image in itertools.product(*cells)]

    spans = [tuple(count * x for x in vector) for vector, count in zip(cell.vectors, repeat)]
    corners = [
        _add(_add(_scale(spans[0], i), _scale(spans[1], j)), _scale(spans[2], k))
        for i, j, k in itertools.product((0, 1), repeat=3)
    ]
    centre = _scale(_add(_add(spans[0], spans[1]), spans[2]), 0.5)
    extent = max(math.dist(corner, centre) for corner in corners)
    return Scene(atoms, find_bonds(atoms), _edges(spans), centre, extent)


def _edges(spans: list[Vec]) -> list[tuple[Vec, Vec]]:
    """The 12 edges of the block spanned by three vectors; 0, 4 and 8 start at the origin."""
    edges = []
    for axis in range(3):
        u, v = (spans[other] for other in range(3) if other != axis)
        for s, t in ((0, 0), (1, 0), (0, 1), (1, 1)):
            start = _add(_scale(u, s), _scale(v, t))
            edges.append((start, _add(start, spans[axis])))
    return edges


def _position(atom: SceneAtom) -> Vec:
    return atom.x, atom.y, atom.z


def _add(u: Vec, v: Vec) -> Vec:
    return tuple(a + b for a, b in zip(u, v))


def _scale(u: Vec, factor: float) -> Vec:
    return tuple(a * factor for a in u)
