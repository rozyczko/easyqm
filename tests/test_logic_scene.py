# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
import itertools
import math
from collections import Counter

import pytest

from Backends.Py.logic.sample import Sample
from Backends.Py.logic.sample import find_bonds
from Backends.Py.logic.scene import build_scene
from Backends.Py.logic.scene import place


@pytest.fixture
def nacl(nacl_cif) -> Sample:
    sample = Sample()
    sample.load(nacl_cif)
    return sample


def _closest(scene) -> float:
    positions = [(atom.x, atom.y, atom.z) for atom in scene.atoms]
    return min(math.dist(p, q) for p, q in itertools.combinations(positions, 2))


def test_molecule_scene_is_the_molecule():
    benzene = Sample.benzene()
    scene = build_scene(benzene)

    assert [(atom.atom, atom.image) for atom in scene.atoms] == [(i, (0, 0, 0)) for i in range(12)]
    assert scene.bonds == find_bonds(benzene.atoms)
    assert scene.cell_edges == []
    assert scene.centre == pytest.approx((0, 0, 0), abs=1e-6)
    assert scene.extent == pytest.approx(2.474, abs=1e-3)  # the H atoms


def test_crystal_with_boundary_atoms(nacl):
    scene = build_scene(nacl)

    # Na on corners and faces: 8 + 3 × 2; Cl at the centre and on edges: 1 + 3 × 4.
    elements = Counter(atom.element for atom in scene.atoms)
    assert len(scene.atoms) == 27 and elements == {'Na': 14, 'Cl': 13}
    assert _closest(scene) == pytest.approx(2.8201)
    assert len(scene.bonds) == 54  # every Na-Cl contact inside the cube


def test_boundary_atoms_are_added_on_the_block_faces_only(nacl):
    assert len(build_scene(nacl, (2, 1, 1), boundary_atoms=False).atoms) == 16
    scene = build_scene(nacl, (2, 1, 1))

    assert len(scene.atoms) == 45  # 3 × 3 × 5 sites of the 2 × 1 × 1 block
    assert _closest(scene) == pytest.approx(2.8201)  # no atom on top of another
    assert all(math.dist(*(_position(scene.atoms[i]) for i in pair)) > 1 for pair in scene.bonds)


def test_cell_edges_centre_and_extent(nacl):
    scene = build_scene(nacl, (2, 1, 1))
    a = 5.6402

    assert len(scene.cell_edges) == 12
    # Edges 0, 4 and 8 run from the origin along a, b and c.
    assert [scene.cell_edges[i] for i in (0, 4, 8)] == [
        ((0, 0, 0), pytest.approx((2 * a, 0, 0))),
        ((0, 0, 0), pytest.approx((0, a, 0))),
        ((0, 0, 0), pytest.approx((0, 0, a))),
    ]
    assert scene.centre == pytest.approx((a, a / 2, a / 2))
    assert scene.extent == pytest.approx(math.sqrt(6) / 2 * a)


def test_place_moves_by_cells(nacl):
    atom = place(nacl, 5, (1, 0, -1))  # Cl6 at (0.5, 0, 0)
    assert (atom.x, atom.y, atom.z) == pytest.approx((1.5 * 5.6402, 0, -5.6402))
    assert atom.atom == 5 and atom.element == 'Cl'


def _position(atom):
    return atom.x, atom.y, atom.z
