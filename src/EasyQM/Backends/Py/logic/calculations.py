# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Qt-free calculations state: which calculations to run and their options (GENERAL_DESIGN.md, 3.3).

PoC1 offers the three calculations every engine supports. Rows for the other calculation
types arrive with the second engine, together with the per-engine enabling of rows.
"""

from dataclasses import dataclass
from enum import Enum


class CalculationType(Enum):
    SINGLE_POINT = 'single_point'
    GEOMETRY_OPTIMISATION = 'geometry_optimisation'
    VIBRATIONAL_FREQUENCIES = 'vibrational_frequencies'


@dataclass(frozen=True)
class CalculationInfo:
    """One row of the "Calculations to perform" table."""

    type: CalculationType
    name: str
    description: str
    results: str
    notes: str = ''


CATALOGUE = (
    CalculationInfo(
        CalculationType.SINGLE_POINT,
        'Single point energy',
        'Total electronic energy at the given geometry',
        'E_total, orbital energies, HOMO–LUMO gap, dipole',
    ),
    CalculationInfo(
        CalculationType.GEOMETRY_OPTIMISATION,
        'Geometry optimisation',
        'Relax atomic positions (and cell for periodic systems) to a minimum',
        'Optimised structure, E_final, convergence trace',
    ),
    CalculationInfo(
        CalculationType.VIBRATIONAL_FREQUENCIES,
        'Vibrational frequencies',
        'Harmonic frequencies, IR intensities, thermochemistry',
        'ν_i, IR/Raman intensities, ZPE, G(T), imaginary modes',
        'Runs after optimisation',
    ),
)

# The order the ticked calculations run in: dependencies first, independent of tick order.
_WORKFLOW_ORDER = (
    CalculationType.GEOMETRY_OPTIMISATION,
    CalculationType.SINGLE_POINT,
    CalculationType.VIBRATIONAL_FREQUENCIES,
)

# Option choices as (value, label) pairs, next to the dataclass they belong to.

SINGLE_POINT_GEOMETRIES = (('optimised', 'Use optimised'), ('input', 'Use input geometry'))


@dataclass
class SinglePointOptions:
    print_orbitals: bool = True
    geometry: str = 'optimised'


OPTIMISATION_CONVERGENCES = (
    ('loose', 'Loose'),
    ('normal', 'Normal'),
    ('tight', 'Tight'),
    ('verytight', 'Very tight'),
)
OPTIMISATION_TARGETS = (('positions', 'Positions only'), ('positions_and_cell', 'Positions and cell'))


@dataclass
class GeometryOptimisationOptions:
    convergence: str = 'tight'
    max_steps: int = 100
    optimise: str = 'positions'
    keep_trajectory: bool = True


FREQUENCY_TYPES = (('analytical', 'Analytical (if available)'), ('numerical', 'Numerical'))


@dataclass
class VibrationalFrequenciesOptions:
    type: str = 'analytical'
    temperature: float = 298.15  # K
    pressure: float = 1.0  # atm
    raman: bool = False


class Calculations:
    def __init__(self):
        self.reset()

    def reset(self) -> None:
        self.selected: set[CalculationType] = set()
        self.single_point = SinglePointOptions()
        self.geometry_optimisation = GeometryOptimisationOptions()
        self.vibrational_frequencies = VibrationalFrequenciesOptions()

    def is_selected(self, calculation: CalculationType) -> bool:
        return calculation in self.selected

    def set_selected(self, calculation: CalculationType, value: bool) -> None:
        if value:
            self.selected.add(calculation)
        else:
            self.selected.discard(calculation)

    def workflow(self) -> list[CalculationType]:
        order = list(_WORKFLOW_ORDER)
        if self.single_point.geometry == 'input':
            # The single point needs the input geometry, so it goes before the optimisation.
            order.remove(CalculationType.SINGLE_POINT)
            order.insert(0, CalculationType.SINGLE_POINT)
        return [calculation for calculation in order if calculation in self.selected]

    def selected_names(self) -> list[str]:
        return [info.name for info in CATALOGUE if info.type in self.selected]


def info(calculation: CalculationType) -> CalculationInfo:
    return next(entry for entry in CATALOGUE if entry.type is calculation)
