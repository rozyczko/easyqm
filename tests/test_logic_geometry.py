# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
import pytest

from Backends.Py.logic.geometry import angle
from Backends.Py.logic.geometry import dihedral
from Backends.Py.logic.geometry import distance
from Backends.Py.logic.geometry import measure
from Backends.Py.logic.sample import Atom


def _atom(x, y, z) -> Atom:
    return Atom('X', 'C', x, y, z)


ORIGIN, X, Y, Z = _atom(0, 0, 0), _atom(1, 0, 0), _atom(0, 1, 0), _atom(0, 0, 1)


def test_distance_and_angle():
    assert distance(X, _atom(1, 3, 4)) == 5.0
    assert angle(X, ORIGIN, Y) == pytest.approx(90.0)
    assert angle(X, ORIGIN, _atom(-1, 0, 0)) == pytest.approx(180.0)
    assert angle(X, ORIGIN, ORIGIN) is None  # an atom on the vertex


@pytest.mark.parametrize(
    'fourth, expected',
    [
        (_atom(1, 0, 1), 0.0),  # cis
        (_atom(-1, 0, 1), 180.0),  # trans
        (_atom(0, 1, 1), 90.0),  # clockwise looking along second -> third: positive (IUPAC)
        (_atom(0, -1, 1), -90.0),
    ],
)
def test_dihedral_sign_and_range(fourth, expected):
    assert dihedral(X, ORIGIN, Z, fourth) == pytest.approx(expected)


def test_dihedral_on_a_line_is_undefined():
    assert dihedral(_atom(0, 0, -1), ORIGIN, Z, Y) is None
    assert dihedral(X, ORIGIN, ORIGIN, Y) is None


def test_measure_by_count():
    assert measure([X]) is None
    assert measure([X, Y]) == ('distance', pytest.approx(2**0.5))
    assert measure([X, ORIGIN, Y]) == ('angle', pytest.approx(90.0))
    assert measure([X, ORIGIN, Z, _atom(0, 1, 1)]) == ('dihedral', pytest.approx(90.0))
    assert measure([X, Y, Z, ORIGIN, X]) is None
