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
