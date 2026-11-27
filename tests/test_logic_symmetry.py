# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
import pytest

from Backends.Py.logic import symmetry
from Backends.Py.logic.sample import Sample
from Backends.Py.logic.sample import read_xyz
from Backends.Py.logic.symmetry import point_group


def _atoms(text: str):
    return read_xyz(text)[0]


@pytest.mark.parametrize(
    'xyz, symbol',
    [
        ('O 0 0 0.117\nH 0 0.757 -0.468\nH 0 -0.757 -0.468', 'C2v'),  # water
        ('N 0 0 0.1\nH 0.94 0 -0.27\nH -0.47 0.814 -0.27\nH -0.47 -0.814 -0.27', 'C3v'),  # ammonia
        ('N 0 0.62 0\nN 0 -0.62 0\nH 0.95 0.95 0\nH -0.95 -0.95 0', 'C2h'),  # trans-diazene
        ('C 0 0 0\nH 0.63 0.63 0.63\nF -0.8 -0.8 0.8\nCl -1 1 -1\nBr 1.1 -1.1 -1.1', 'C1'),
        ('C 0 0 0\nO 0 0 1.16\nO 0 0 -1.16', 'D∞h'),  # carbon dioxide
        ('H 0 0 -1.06\nC 0 0 0\nN 0 0 1.15', 'C∞v'),  # hydrogen cyanide
        ('Ar 0 0 0', 'Kh'),
    ],
)
def test_point_groups(xyz, symbol):
    assert point_group(_atoms(f'{xyz.count(chr(10)) + 1}\n\n{xyz}\n')) == symbol


def test_point_group_of_a_spherical_top():
    methane = 'C 0 0 0\nH 0.629 0.629 0.629\nH -0.629 -0.629 0.629\nH -0.629 0.629 -0.629\nH 0.629 -0.629 -0.629'
    assert point_group(_atoms(f'5\n\n{methane}\n')) == 'Td'


def test_point_group_follows_the_geometry():
    sample = Sample.benzene()
    assert point_group(sample.atoms) == 'D6h'

    sample.set_position(0, (sample.atoms[0].x, sample.atoms[0].y, 0.3))  # C1 out of the ring plane
    assert point_group(sample.atoms) == 'Cs'


def test_point_group_is_not_determined_for_large_or_odd_structures(monkeypatch):
    water = _atoms('3\n\nO 0 0 0.117\nH 0 0.757 -0.468\nH 0 -0.757 -0.468\n')
    assert point_group([]) == ''

    monkeypatch.setattr(symmetry, 'ATOM_LIMIT', 2)
    assert point_group(water) == ''

    monkeypatch.undo()

    def fail(*args):
        raise Exception('Group type error')

    monkeypatch.setattr(symmetry, 'PointGroup', fail)
    assert point_group(water) == ''


def _crystal(text: str):
    atoms, cell = read_xyz(text)
    return atoms, cell


def test_space_group_of_rock_salt_and_its_supercell(nacl_cif):
    sample = Sample()
    sample.load(nacl_cif)

    assert symmetry.space_group(sample.atoms, sample.cell) == symmetry.SpaceGroup('Fm-3m', 225)
    assert sample.space_group().text == 'Fm-3m (225)'
    assert sample.space_group_warning(sample.space_group()) == ''

    sample.make_supercell(2, 1, 1)  # a tetragonal block of a cubic crystal: still Fm-3m
    assert sample.space_group().number == 225 and sample.cell.space_group == ''


def test_space_group_follows_the_atoms(nacl_cif):
    sample = Sample()
    sample.load(nacl_cif)

    sample.set_position(0, (0.02, 0.0, 0.0), fractional=True)  # one Na off its site

    assert sample.space_group().symbol == 'P4mm'
    # Off by 0.0056 Å: its mirror image is 0.011 Å away, more than the tolerance.
    sample.set_position(0, (0.001, 0.0, 0.0), fractional=True)
    assert sample.space_group().symbol == 'P4mm'
    sample.set_position(0, (0.0005, 0.0, 0.0), fractional=True)  # image 0.0056 Å away: within it
    assert sample.space_group().symbol == 'Fm-3m'


def test_space_group_of_a_hexagonal_cell_and_of_no_atoms():
    # Graphite-like boron nitride layer stacking, a = 2.5 Å, coordinates to three decimals.
    atoms, cell = _crystal('2\nLattice="2.5 0 0 -1.25 2.165 0 0 0 6.7"\nB 0 0 0\nN 0 1.443 0\n')
    assert symmetry.space_group(atoms, cell).symbol == 'P-6m2'
    assert symmetry.space_group([], cell) is None


def test_space_group_is_none_for_atoms_on_top_of_each_other():
    atoms, cell = _crystal('2\nLattice="3 0 0 0 3 0 0 0 3"\nNa 0 0 0\nNa 0 0 0.001\n')
    assert symmetry.space_group(atoms, cell) is None
    assert Sample().space_group() is None  # no structure, no cell


def test_space_group_warning_when_the_file_gives_another_group(tmp_path):
    from conftest import NACL_CIF

    # The two sites without the F centring that would make rock salt of them: CsCl's structure.
    path = tmp_path / 'wrong.cif'
    path.write_text(NACL_CIF.replace("'F m -3 m'", "'P 1'"), encoding='utf-8')
    sample = Sample()
    sample.load(path)

    assert (sample.cell.space_group, sample.cell.space_group_number) == ('P1', 1)
    assert sample.space_group().text == 'Pm-3m (221)'
    assert sample.space_group_warning(sample.space_group()) == 'The file gives P1 (1), but the atoms have Pm-3m (221).'
    assert sample.space_group_warning(None) == 'The file gives P1 (1), but no space group was found for the atoms.'

    sample.set_position(0, (0.0, 0.0, 0.0), fractional=True)  # an edit drops the file's group
    assert sample.space_group_warning(sample.space_group()) == ''


def test_space_group_warning_compares_numbers_not_settings(nacl_cif):
    sample = Sample()
    sample.load(nacl_cif)
    sample.cell.space_group, sample.cell.space_group_number = 'P21/n', 14  # as a file may give it

    assert sample.space_group_warning(symmetry.SpaceGroup('P2_1/c', 14)) == ''
    assert Sample.benzene().space_group_warning(None) == ''
