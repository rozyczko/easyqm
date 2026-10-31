# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
import pytest

from Backends.Py.logic.sample import Sample


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
        ('', 'not an XYZ file'),
        ('two\n\nC 0 0 0\n', 'not an XYZ file'),
        ('3\n\nC 0 0 0\nC 1 0 0\n', 'declares 3 atoms'),
        ('1\n\nC 0 0\n', 'expected "element x y z"'),
        ('1\n\nC 0 0 z\n', 'not numbers'),
    ],
)
def test_bad_xyz_is_rejected(tmp_path, text, message):
    xyz = tmp_path / 'bad.xyz'
    xyz.write_text(text, encoding='utf-8')
    sample = Sample.benzene()

    with pytest.raises(ValueError, match=message):
        sample.load_xyz(xyz)
    assert sample.atom_count == 12
