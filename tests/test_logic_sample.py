# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
import pytest

from Backends.Py.logic.elements import COVALENT_RADII
from Backends.Py.logic.elements import SYMBOLS
from Backends.Py.logic.sample import Sample
from Backends.Py.logic.sample import find_bonds
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
    bonds = Sample.benzene().bonds()

    assert len(bonds) == 12
    ring = [pair for pair in bonds if pair[0] < 6 and pair[1] < 6]
    assert sorted(ring) == [(0, 1), (0, 5), (1, 2), (2, 3), (3, 4), (4, 5)]
    assert all((i, i + 6) in bonds for i in range(6))


def test_formula_hill_order(tmp_path):
    xyz = tmp_path / 'x.xyz'
    xyz.write_text('4\n\nO 0 0 0\nH 1 0 0\nN 0 1 0\nh 0 0 1\n', encoding='utf-8')
    sample = Sample()
    sample.load_xyz(xyz)
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
        sample.load_xyz(xyz)
    assert sample.atom_count == 12 and sample.source == 'benzene.xyz'


def test_binary_file_is_rejected(tmp_path):
    path = tmp_path / 'picture.xyz'
    path.write_bytes(b'\x89PNG\r\n\x1a\n\xff\xfe')

    with pytest.raises(ValueError, match='not a text file'):
        Sample().load_xyz(path)


@pytest.mark.parametrize(
    'field, element',
    [('C', 'C'), ('cl', 'Cl'), ('CL', 'Cl'), ('6', 'C'), ('17', 'Cl'), ('C12', 'C'), ('Cl_a', 'Cl'), ('Hb', 'H')],
)
def test_element_column_variants(field, element):
    assert read_xyz(f'1\n\n{field} 0 0 0\n')[0].element == element


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
    atoms = read_xyz(text)

    assert [(atom.label, atom.z) for atom in atoms] == [('H1', 0.0), ('H2', 0.74)]


def test_loading_resets_the_electronic_state(tmp_path):
    methyl = tmp_path / 'methyl.xyz'
    methyl.write_text('4\nmethyl radical\nC 0 0 0\nH 1.08 0 0\nH -0.54 0.935 0\nH -0.54 -0.935 0\n', encoding='utf-8')
    sample = Sample.benzene()
    sample.charge = 1
    sample.atoms[0].fixed = True

    sample.load_xyz(methyl)

    assert sample.name == 'methyl' and sample.summary == 'methyl.xyz · CH3 · 4 atoms'
    assert sample.charge == 0 and sample.multiplicity == 2  # 9 electrons
    assert sample.fixed_count == 0


def test_bonds_use_radii_of_all_elements(tmp_path):
    # CH3Br: C-Br 1.94 Å bonds; Br-H 2.5 Å does not.
    atoms = read_xyz('5\n\nC 0 0 0\nBr 0 0 1.94\nH 1.03 0 -0.36\nH -0.51 0.89 -0.36\nH -0.51 -0.89 -0.36\n')
    assert sorted(find_bonds(atoms)) == [(0, 1), (0, 2), (0, 3), (0, 4)]


def test_element_table_is_complete():
    assert len(SYMBOLS) == 118 and SYMBOLS[5] == 'C' and SYMBOLS[-1] == 'Og'
    assert len(COVALENT_RADII) == 96 and COVALENT_RADII['Cm'] == 1.69
