# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""High-symmetry paths: the lattice of a cell, the named points in its reciprocal vectors."""

import math

import pytest

from Backends.Py.logic.kpath import GAMMA
from Backends.Py.logic.kpath import band_path
from Backends.Py.logic.kpath import cartesian
from Backends.Py.logic.kpath import folded_reason
from Backends.Py.logic.kpath import path_kpoints
from Backends.Py.logic.sample import Cell


def _length(cell, point) -> float:
    """|k| in Å⁻¹ with the 2π factor."""
    return math.sqrt(sum(x * x for x in cartesian(cell.reciprocal, point)))


@pytest.mark.parametrize(
    'cell, lattice, path',
    [
        (Cell.from_parameters(5.43, 5.43, 5.43, 90, 90, 90), 'Simple cubic', 'Γ–X–M–Γ–R–X | M–R'),
        (Cell(((0, 2.7, 2.7), (2.7, 0, 2.7), (2.7, 2.7, 0))), 'Face-centred cubic (primitive cell)',
         'Γ–X–W–K–Γ–L–U–W–L–K | U–X'),
        (Cell(((-1.5, 1.5, 1.5), (1.5, -1.5, 1.5), (1.5, 1.5, -1.5))), 'Body-centred cubic (primitive cell)',
         'Γ–H–N–Γ–P–H | P–N'),
        (Cell.from_parameters(4, 4, 6, 90, 90, 90), 'Tetragonal', 'Γ–X–M–Γ–Z–R–A–Z | X–R | M–A'),
        (Cell.from_parameters(3, 4, 5, 90, 90, 90), 'Orthorhombic', 'Γ–X–S–Y–Γ–Z–U–R–T–Z | Y–T | U–X | S–R'),
        (Cell.from_parameters(2.46, 2.46, 6.7, 90, 90, 120), 'Hexagonal', 'Γ–M–K–Γ–A–L–H–A | L–M | K–H'),
        (Cell.from_parameters(5, 5, 5, 70, 70, 70), 'Rhombohedral', 'Γ–L–B₁ | B–Z–Γ–X | Q–F–P₁–Z | L–P'),
        (Cell.from_parameters(5, 5, 5, 100, 100, 100), 'Rhombohedral', 'Γ–P–Z–Q–Γ–F–P₁–Q₁–L–Z'),
        (Cell.from_parameters(5.1, 5.2, 5.3, 90, 99, 90), 'General (no symmetry recognised)',
         'X–Γ–Y | L–Γ–Z | N–Γ–M | R–Γ'),
    ],
)
def test_the_lattice_picks_the_path(cell, lattice, path):
    found = band_path(cell)
    assert (found.lattice, found.text) == (lattice, path)
    assert found.points[GAMMA] == (0, 0, 0)


def test_named_points_lie_where_their_lattice_puts_them():
    a = 5.43
    # Primitive fcc: X at 2π/a, L at √3·π/a, K at 3√2·π/(2a).
    fcc = Cell(((0, a / 2, a / 2), (a / 2, 0, a / 2), (a / 2, a / 2, 0)))
    points = band_path(fcc).points
    assert _length(fcc, points['X']) == pytest.approx(2 * math.pi / a)
    assert _length(fcc, points['L']) == pytest.approx(math.sqrt(3) * math.pi / a)
    assert _length(fcc, points['K']) == pytest.approx(3 * math.sqrt(2) * math.pi / (2 * a))


@pytest.mark.parametrize('gamma', [120, 60])
def test_hexagonal_points_in_either_setting(gamma):
    a, c = 2.46, 6.7
    cell = Cell.from_parameters(a, a, c, 90, 90, gamma)
    points = band_path(cell).points
    assert _length(cell, points['K']) == pytest.approx(4 * math.pi / (3 * a))
    assert _length(cell, points['M']) == pytest.approx(2 * math.pi / (math.sqrt(3) * a))
    assert _length(cell, points['A']) == pytest.approx(math.pi / c)
    # K and M are neighbours on the zone boundary: a third of the way round from M.
    k, m = cartesian(cell.reciprocal, points['K']), cartesian(cell.reciprocal, points['M'])
    assert math.dist(k, m) == pytest.approx(2 * math.pi / (3 * a))


def test_close_named_points_keep_their_names_and_the_samples_between_stay_unnamed():
    # Near 90°, B (η, ½, 1 − η) lies within the default tolerance of Z (½, ½, ½).
    path = band_path(Cell.from_parameters(5, 5, 5, 89.9, 89.9, 89.9))
    b, z = path.points['B'], path.points['Z']
    assert path.lattice == 'Rhombohedral' and max(abs(x - y) for x, y in zip(b, z)) < 2e-3
    assert path.label(z) == 'Z' and path.label(b) == 'B'
    assert path.label(tuple((x + y) / 2 for x, y in zip(b, z))) == ''
    # Well-separated points keep the full tolerance.
    cubic = band_path(Cell.from_parameters(5.43, 5.43, 5.43, 90, 90, 90))
    assert cubic.label((0.0015, 0.5, 0)) == 'X' and cubic.label((0.003, 0.5, 0)) == ''


def test_the_unique_or_shortest_axis_is_found_in_any_position():
    tetragonal = Cell.from_parameters(6, 4, 4, 90, 90, 90)  # a unique
    assert band_path(tetragonal).points['Z'] == (0.5, 0, 0)
    orthorhombic = Cell.from_parameters(5, 3, 4, 90, 90, 90)  # b shortest, then c, then a
    points = band_path(orthorhombic).points
    assert (points['X'], points['Y'], points['Z']) == ((0, 0.5, 0), (0, 0, 0.5), (0.5, 0, 0))


def test_path_kpoints_spread_by_length_with_jumps_between_branches():
    cell = Cell.from_parameters(5.43, 5.43, 5.43, 90, 90, 90)
    path = band_path(cell)
    vertices = path_kpoints(cell, path, 100)

    assert [name for _, _, name in vertices] == ['Γ', 'X', 'M', 'Γ', 'R', 'X', 'M', 'R']
    counts = [count for _, count, _ in vertices]
    assert counts[5] == 1 and counts[-1] == 1  # X | M is a jump, R ends the path
    assert all(count >= 2 for i, count in enumerate(counts) if i not in (5, 7))
    assert sum(counts) == pytest.approx(100, abs=5)
    # On a cube |ΓX| = |XM| and |ΓR| = √3 |ΓX|.
    assert counts[0] == counts[1] and counts[3] == pytest.approx(math.sqrt(3) * counts[0], abs=1)


def test_a_conventional_cell_of_a_centred_lattice_folds_its_bands():
    conventional = Cell.from_parameters(5.43, 5.43, 5.43, 90, 90, 90, 'Fd-3m')
    assert 'conventional cell of a centred lattice (Fd-3m)' in folded_reason(conventional, band_path(conventional))
    primitive = Cell(((0, 2.7, 2.7), (2.7, 0, 2.7), (2.7, 2.7, 0)), 'Fd-3m')
    assert folded_reason(primitive, band_path(primitive)) == ''
    unknown = Cell.from_parameters(5.43, 5.43, 5.43, 90, 90, 90)  # edited: no space group
    assert folded_reason(unknown, band_path(unknown)) == ''
    assert folded_reason(Cell.from_parameters(3, 3, 5, 90, 90, 120, 'P63/mmc'), band_path(unknown)) == ''


def test_the_atoms_tell_a_conventional_cell_from_a_supercell():
    cubic = Cell.from_parameters(5.43, 5.43, 5.43, 90, 90, 90)  # no group from a file
    path = band_path(cubic)
    assert 'conventional cell of a centred lattice (Fd-3m)' in folded_reason(cubic, path, 4, 'Fd-3m')
    assert 'holds 2 primitive cells' in folded_reason(Cell.from_parameters(5.43, 5.43, 10.86, 90, 90, 90),
                                                      path, 2, 'P4/mmm')  # 2 × 1 × 1 of a simple cell
    assert 'holds 32 primitive cells' in folded_reason(cubic, path, 32, 'Fd-3m')  # 2 × 2 × 2 of the conventional
    assert folded_reason(cubic, path, 1, 'Pm-3m') == ''
    primitive = Cell(((0, 2.7, 2.7), (2.7, 0, 2.7), (2.7, 2.7, 0)))
    assert folded_reason(primitive, band_path(primitive), 1, 'Fd-3m') == ''
    assert 'holds 8 primitive cells' in folded_reason(primitive, band_path(primitive), 8, 'Fd-3m')
