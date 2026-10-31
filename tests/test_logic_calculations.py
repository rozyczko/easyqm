# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
from Backends.Py.logic.calculations import CATALOGUE
from Backends.Py.logic.calculations import Calculations
from Backends.Py.logic.calculations import CalculationType
from Backends.Py.logic.calculations import info


def test_catalogue_covers_every_type_once():
    assert [entry.type for entry in CATALOGUE] == list(CalculationType)
    assert info(CalculationType.VIBRATIONAL_FREQUENCIES).notes == 'Runs after optimisation'


def test_nothing_selected_by_default():
    calculations = Calculations()
    assert calculations.workflow() == []
    assert calculations.selected_names() == []
    assert calculations.geometry_optimisation.max_steps == 100
    assert calculations.vibrational_frequencies.temperature == 298.15


def test_workflow_order_is_independent_of_tick_order():
    calculations = Calculations()
    calculations.set_selected(CalculationType.VIBRATIONAL_FREQUENCIES, True)
    calculations.set_selected(CalculationType.SINGLE_POINT, True)
    calculations.set_selected(CalculationType.GEOMETRY_OPTIMISATION, True)

    assert calculations.workflow() == [
        CalculationType.GEOMETRY_OPTIMISATION,
        CalculationType.SINGLE_POINT,
        CalculationType.VIBRATIONAL_FREQUENCIES,
    ]
    assert calculations.selected_names() == ['Single point energy', 'Geometry optimisation', 'Vibrational frequencies']

    calculations.set_selected(CalculationType.SINGLE_POINT, False)
    calculations.set_selected(CalculationType.SINGLE_POINT, False)
    assert calculations.workflow() == [CalculationType.GEOMETRY_OPTIMISATION, CalculationType.VIBRATIONAL_FREQUENCIES]


def test_single_point_at_input_geometry_runs_first():
    calculations = Calculations()
    for calculation in CalculationType:
        calculations.set_selected(calculation, True)
    calculations.single_point.geometry = 'input'

    assert calculations.workflow() == [
        CalculationType.SINGLE_POINT,
        CalculationType.GEOMETRY_OPTIMISATION,
        CalculationType.VIBRATIONAL_FREQUENCIES,
    ]
