# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
import sys

import gemmi
import pytest
from conftest import NACL_CIF

from Backends.Py.logic.elements import COVALENT_RADII
from Backends.Py.logic.elements import SYMBOLS
from Backends.Py.logic.sample import Cell
from Backends.Py.logic.sample import Sample
from Backends.Py.logic.sample import find_bonds
from Backends.Py.logic.sample import read_cif
from Backends.Py.logic.sample import read_xyz


def test_benzene_is_bundled():
    sample = Sample.benzene()

    assert sample.name == 'benzene'
    assert sample.source == 'benzene.xyz'
    assert sample.atom_count == 12
    assert sample.formula == 'C6H6'
    assert sample.summary == 'benzene.xyz · C6H6 · 12 atoms'
    assert [atom.label for atom in sample.atoms][:7] == ['C1', 'C2', 'C3', 'C4', 'C5', 'C6', 'H7']
    assert not sample.periodic and sample.charge == 0 and sample.multiplicity == 1


def test_benzene_bonds():
    bonds = find_bonds(Sample.benzene().atoms)

    assert len(bonds) == 12
    ring = [pair for pair in bonds if pair[0] < 6 and pair[1] < 6]
    assert sorted(ring) == [(0, 1), (0, 5), (1, 2), (2, 3), (3, 4), (4, 5)]
    assert all((i, i + 6) in bonds for i in range(6))


def test_formula_hill_order(tmp_path):
    xyz = tmp_path / 'x.xyz'
    xyz.write_text('4\n\nO 0 0 0\nH 1 0 0\nN 0 1 0\nh 0 0 1\n', encoding='utf-8')
    sample = Sample()
    sample.load(xyz)
    assert sample.formula == 'H2NO'
    assert sample.atoms[3].element == 'H'


def test_fixed_count():
    sample = Sample.benzene()
    assert sample.fixed_count == 0
    sample.atoms[0].fixed = True
    sample.atoms[7].fixed = True
    assert sample.fixed_count == 2


@pytest.mark.parametrize(
    'text, message',
    [
        ('', 'number of atoms'),
        ('two\n\nC 0 0 0\n', 'number of atoms'),
        ('0\n\n', 'no atoms'),
        ('3\n\nC 0 0 0\nC 1 0 0\n', 'declares 3 atoms but holds 2'),
        ('2\n\nC 0 0 0\n\nC 1 0 0\n', 'declares 2 atoms but holds 1'),
        ('1\n\nC 0 0\n', 'expected "element x y z"'),
        ('1\n\nC 0 0 z\n', 'expected "element x y z"'),
        ('1\n\nXx 0 0 0\n', '"Xx" is not an element'),
        ('1\n\n0 0 0 0\n', '"0" is not an element'),
    ],
)
def test_bad_xyz_is_rejected(tmp_path, text, message):
    xyz = tmp_path / 'bad.xyz'
    xyz.write_text(text, encoding='utf-8')
    sample = Sample.benzene()

    with pytest.raises(ValueError, match=message):
        sample.load(xyz)
    assert sample.atom_count == 12 and sample.source == 'benzene.xyz'


def test_binary_file_is_rejected(tmp_path):
    path = tmp_path / 'picture.xyz'
    path.write_bytes(b'\x89PNG\r\n\x1a\n\xff\xfe')

    with pytest.raises(ValueError, match='not a text file'):
        Sample().load(path)


@pytest.mark.parametrize(
    'field, element',
    [('C', 'C'), ('cl', 'Cl'), ('CL', 'Cl'), ('6', 'C'), ('17', 'Cl'), ('C12', 'C'), ('Cl_a', 'Cl'), ('Hb', 'H')],
)
def test_element_column_variants(field, element):
    assert read_xyz(f'1\n\n{field} 0 0 0\n')[0][0].element == element


def test_extended_xyz_and_further_frames_are_ignored():
    text = (
        '2\n'
        'Properties=species:S:1:pos:R:3:forces:R:3 energy=-1.0\n'
        'H 0.0 0.0 0.0 0.1 0.2 0.3\n'
        'H 0.0 0.0 0.74 -0.1 -0.2 -0.3\n'
        '2\n'
        'second frame\n'
        'H 0.0 0.0 0.0\n'
        'H 0.0 0.0 0.80\n'
    )
    atoms, cell = read_xyz(text)

    assert [(atom.label, atom.z) for atom in atoms] == [('H1', 0.0), ('H2', 0.74)]


def test_loading_resets_the_electronic_state(tmp_path):
    methyl = tmp_path / 'methyl.xyz'
    methyl.write_text('4\nmethyl radical\nC 0 0 0\nH 1.08 0 0\nH -0.54 0.935 0\nH -0.54 -0.935 0\n', encoding='utf-8')
    sample = Sample.benzene()
    sample.charge = 1
    sample.atoms[0].fixed = True

    sample.load(methyl)

    assert sample.name == 'methyl' and sample.summary == 'methyl.xyz · CH3 · 4 atoms'
    assert sample.charge == 0 and sample.multiplicity == 2  # 9 electrons
    assert sample.fixed_count == 0


def test_bonds_use_radii_of_all_elements(tmp_path):
    # CH3Br: C-Br 1.94 Å bonds; Br-H 2.5 Å does not.
    atoms, _ = read_xyz('5\n\nC 0 0 0\nBr 0 0 1.94\nH 1.03 0 -0.36\nH -0.51 0.89 -0.36\nH -0.51 -0.89 -0.36\n')
    assert sorted(find_bonds(atoms)) == [(0, 1), (0, 2), (0, 3), (0, 4)]


def test_element_table_is_complete():
    assert len(SYMBOLS) == 118 and SYMBOLS[5] == 'C' and SYMBOLS[-1] == 'Og'
    assert len(COVALENT_RADII) == 96 and COVALENT_RADII['Cm'] == 1.69


# Unit cell


@pytest.mark.parametrize(
    'parameters',
    [(5.64, 5.64, 5.64, 90, 90, 90), (2.464, 2.464, 6.711, 90, 90, 120), (5, 6, 7, 80, 85, 95)],
)
def test_cell_from_parameters_is_gemmis_setting(parameters):
    cell = Cell.from_parameters(*parameters)
    reference = gemmi.UnitCell(*parameters)

    columns = [[reference.orth.mat.tolist()[row][column] for row in range(3)] for column in range(3)]
    assert [list(vector) for vector in cell.vectors] == [pytest.approx(column, abs=1e-9) for column in columns]
    assert cell.volume == pytest.approx(reference.volume)
    assert (*cell.lengths, *cell.angles) == pytest.approx(parameters)


def test_cell_coordinates_and_reciprocal():
    cell = Cell.from_parameters(5, 6, 7, 80, 85, 95)
    point = cell.cartesian(0.1, 0.2, 0.3)

    assert cell.fractional(*point) == pytest.approx((0.1, 0.2, 0.3))
    # Without 2π: a*·a = 1, a*·b = 0
    for i, star in enumerate(cell.reciprocal):
        for j, vector in enumerate(cell.vectors):
            assert sum(s * v for s, v in zip(star, vector)) == pytest.approx(1.0 if i == j else 0.0, abs=1e-12)


def test_extended_xyz_keeps_its_lattice_vectors():
    # A cell rotated 45° about z: rebuilding it from a, b, c, α, β, γ would turn it back.
    text = '1\nLattice="2 2 0 -2 2 0 0 0 3" pbc="T T T"\nH 1 1 0\n'
    atoms, cell = read_xyz(text)

    assert cell.vectors == ((2.0, 2.0, 0.0), (-2.0, 2.0, 0.0), (0.0, 0.0, 3.0))
    assert cell.fractional(1, 1, 0) == pytest.approx((0.5, 0.0, 0.0))  # (1, 1, 0) is a / 2


@pytest.mark.parametrize(
    'comment, periodic',
    [
        ('plain comment', False),
        ('Lattice="5 0 0 0 5 0 0 0 5"', True),
        ('Lattice="5 0 0 0 5 0 0 0 5" pbc="T T T"', True),
        ('lattice="5 0 0 0 5 0 0 0 5" PBC="t t t"', True),
        ('Lattice="10 0 0 0 10 0 0 0 10" pbc="F F F"', False),  # a molecule in a box
    ],
)
def test_extended_xyz_cell(comment, periodic):
    _, cell = read_xyz(f'1\n{comment}\nH 0 0 0\n')
    assert (cell is not None) == periodic


@pytest.mark.parametrize(
    'comment, message',
    [
        ('Lattice="5 0 0 0 5 0 0 0 5" pbc="T T F"', 'Partially periodic'),
        ('Lattice="5 0 0 0 5 0"', 'nine numbers'),
        ('Lattice="5 0 0 0 5 0 0 0 x"', 'nine numbers'),
        ('Lattice="5 0 0 10 0 0 0 0 5"', 'span no volume'),
    ],
)
def test_bad_extended_xyz_cell_is_rejected(comment, message):
    with pytest.raises(ValueError, match=message):
        read_xyz(f'1\n{comment}\nH 0 0 0\n')


def test_cif_is_expanded_and_wrapped(nacl_cif):
    sample = Sample()
    sample.load(nacl_cif)

    assert sample.periodic and sample.cell.space_group == 'Fm-3m'
    assert [atom.label for atom in sample.atoms] == ['Na1', 'Na2', 'Na3', 'Na4', 'Cl5', 'Cl6', 'Cl7', 'Cl8']
    # gemmi gives Cl at (0.5, 1, 1) and the like; they are wrapped into the cell.
    fractional = [sample.cell.fractional(atom.x, atom.y, atom.z) for atom in sample.atoms]
    assert all(-1e-12 < value < 1 for position in fractional for value in position)
    assert fractional[5] == pytest.approx((0.5, 0.0, 0.0))
    assert sample.charge == 0 and sample.multiplicity == 1


def test_crystal_formula_and_summary(nacl_cif):
    sample = Sample()
    sample.load(nacl_cif)

    assert sample.formula == 'ClNa' and sample.formula_units == 4
    assert sample.summary == 'NaCl.cif · ClNa · Z = 4 · 8 atoms · Fm-3m'
    assert Sample.benzene().formula_units == 1


def test_cif_space_group_from_symmetry_operations():
    text = NACL_CIF.replace(
        "_symmetry_space_group_name_H-M 'F m -3 m'",
        "loop_\n_space_group_symop_operation_xyz\n'x,y,z'\n'-x,-y,-z'",
    )
    atoms, cell = read_cif(text)

    assert len(atoms) == 2 and cell.space_group == 'P-1'


def test_cif_without_symmetry_has_no_space_group():
    atoms, cell = read_cif(NACL_CIF.replace("_symmetry_space_group_name_H-M 'F m -3 m'\n", ''))
    assert len(atoms) == 2 and cell.space_group == ''


@pytest.mark.parametrize(
    'old, new, message',
    [
        ('_cell_length_a 5.6402\n', '', 'no unit cell'),
        ('Na1 Na+ 0 0 0\nCl1 Cl- 0.5 0.5 0.5\n', '', 'no atoms'),
        ('Cl1 Cl- 0.5 0.5 0.5', 'Q1 Qq 0.5 0.5 0.5', 'Site Q1: "Qq" is not an element'),
        ('data_NaCl', 'not a CIF', 'not a CIF file'),
    ],
)
def test_bad_cif_is_rejected(old, new, message):
    with pytest.raises(ValueError, match=message):
        read_cif(NACL_CIF.replace(old, new))


def test_partially_occupied_cif_is_rejected():
    text = NACL_CIF.replace('_atom_site_fract_z\n', '_atom_site_fract_z\n_atom_site_occupancy\n')
    text = text.replace('Na1 Na+ 0 0 0', 'Na1 Na+ 0 0 0 0.5\nK1 K+ 0 0 0 0.5').replace('Cl- 0.5 0.5 0.5', 'Cl- 0.5 0.5 0.5 1')
    with pytest.raises(ValueError, match='partially occupied'):
        read_cif(text)


def test_cif_without_gemmi(monkeypatch, nacl_cif):
    monkeypatch.setitem(sys.modules, 'gemmi', None)  # import gemmi raises ImportError
    sample = Sample.benzene()

    with pytest.raises(ValueError, match='needs the gemmi package'):
        sample.load(nacl_cif)
    assert sample.formula == 'C6H6'
