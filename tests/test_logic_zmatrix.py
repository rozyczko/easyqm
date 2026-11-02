# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
import pytest
from Backends.Py.logic.geometry import angle
from Backends.Py.logic.geometry import dihedral
from Backends.Py.logic.geometry import distance
from Backends.Py.logic.sample import Atom
from Backends.Py.logic.sample import Sample
from Backends.Py.logic.zmatrix import ZMatrix


def _atoms(spec: str) -> list[Atom]:
    rows = [line.split() for line in spec.strip().splitlines()]
    return [Atom(f'{row[0]}{i + 1}', row[0], *map(float, row[1:4])) for i, row in enumerate(rows)]


def _moved(atoms: list[Atom], positions) -> list[Atom]:
    return [Atom(atom.label, atom.element, *position) for atom, position in zip(atoms, positions)]


def test_benzene_rows_have_the_textbook_shape():
    atoms = Sample.benzene().atoms
    zmatrix = ZMatrix(atoms)

    assert sorted(row.atom for row in zmatrix.rows) == list(range(12))
    first, second, third, *rest = zmatrix.rows
    assert first.references == (None, None, None)
    assert second.references[0] == first.atom and second.references[1:] == (None, None)
    assert third.references[:2] == (first.atom, second.atom) and third.references[2] is None
    assert all(None not in row.references for row in rest)
    assert second.value('bond') == pytest.approx(1.3915, abs=1e-3)


def test_values_are_distances_angles_and_iupac_dihedrals():
    atoms = Sample.benzene().atoms
    atoms[6].z = 0.5  # H7 out of the plane, so its dihedral is not 0 or 180
    zmatrix = ZMatrix(atoms)

    for row in zmatrix.rows[3:]:
        bond_to, angle_to, dihedral_to = (atoms[i] for i in row.references)
        here = atoms[row.atom]
        assert row.value('bond') == pytest.approx(distance(here, bond_to))
        assert row.value('angle') == pytest.approx(angle(here, bond_to, angle_to))
        assert row.value('dihedral') == pytest.approx(dihedral(here, bond_to, angle_to, dihedral_to), abs=1e-9)
    assert any(abs(row.value('dihedral')) not in (0.0, 180.0) for row in zmatrix.rows[3:])


def test_editing_a_value_moves_the_atom_and_those_placed_from_it():
    atoms = Sample.benzene().atoms
    zmatrix = ZMatrix(atoms)
    row = next(row for row in zmatrix.rows if atoms[row.atom].element == 'H')

    moved = _moved(atoms, zmatrix.positions_with(row.atom, 'bond', 1.2))

    assert distance(moved[row.atom], moved[row.reference('bond')]) == pytest.approx(1.2)
    dependants = {other.atom for other in zmatrix.rows if row.atom in other.references}
    for index, (before, after) in enumerate(zip(atoms, moved)):
        if index != row.atom and index not in dependants:
            assert distance(before, after) < 1e-9


def test_editing_a_dihedral_keeps_the_iupac_sign():
    atoms = Sample.benzene().atoms
    zmatrix = ZMatrix(atoms)
    row = zmatrix.rows[5]

    moved = _moved(atoms, zmatrix.positions_with(row.atom, 'dihedral', 30.0))

    assert dihedral(*(moved[i] for i in (row.atom, *row.references))) == pytest.approx(30.0)


def test_the_construction_is_kept_while_atoms_move():
    atoms = Sample.benzene().atoms
    zmatrix = ZMatrix(atoms)
    atoms[4].x += 0.1

    again = ZMatrix(atoms, zmatrix.construction)

    assert [(row.atom, row.references) for row in again.rows] == [(row.atom, row.references) for row in zmatrix.rows]


@pytest.mark.parametrize(
    'field, value, message',
    [
        ('bond', 0.0, 'positive'),
        ('angle', 0.0, 'above 0'),
        ('angle', 181.0, 'up to 180'),
        ('bond', float('nan'), 'number'),
    ],
)
def test_values_out_of_range_are_refused(field, value, message):
    zmatrix = ZMatrix(Sample.benzene().atoms)

    with pytest.raises(ValueError, match=message):
        zmatrix.positions_with(zmatrix.rows[5].atom, field, value)


def test_absolute_values_are_not_edited():
    zmatrix = ZMatrix(Sample.benzene().atoms)

    with pytest.raises(ValueError, match='not defined by other atoms'):
        zmatrix.positions_with(zmatrix.rows[1].atom, 'angle', 100.0)


@pytest.mark.parametrize(
    'spec, rows',
    [
        ('Ar 0 0 0', 1),
        ('H 0 0 0\nH 0 0 0.74', 2),
        ('O 0 0 -1.16\nC 0 0 0\nO 0 0 1.16', 3),  # linear, but no dihedral needed
    ],
)
def test_small_molecules(spec, rows):
    assert len(ZMatrix(_atoms(spec)).rows) == rows


def test_a_linear_molecule_of_four_atoms_has_no_zmatrix():
    with pytest.raises(ValueError, match='linear'):
        ZMatrix(_atoms('H 0 0 -1.66\nC 0 0 -0.6\nC 0 0 0.6\nH 0 0 1.66'))
