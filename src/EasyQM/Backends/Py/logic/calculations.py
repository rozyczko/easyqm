# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Qt-free calculations state: which calculations to run and their options (GENERAL_DESIGN.md, 3.3).

A calculation the sample's kind does not allow (excited states of a crystal) is shown greyed
with the reason, and cannot be selected.
"""

from dataclasses import dataclass
from enum import Enum


class CalculationType(Enum):
    SINGLE_POINT = 'single_point'
    GEOMETRY_OPTIMISATION = 'geometry_optimisation'
    VIBRATIONAL_FREQUENCIES = 'vibrational_frequencies'
    EXCITED_STATES = 'excited_states'


@dataclass(frozen=True)
class CalculationInfo:
    """One row of the "Calculations to perform" table."""

    type: CalculationType
    name: str
    description: str
    results: str
    notes: str = ''
    systems: tuple[str, ...] = ('molecule', 'crystal')  # as `EngineAdapter.systems`


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
    CalculationInfo(
        CalculationType.EXCITED_STATES,
        'Excited states',
        'Vertical excitation energies and oscillator strengths',
        'E_exc, f, UV-Vis spectrum',
        'ORCA: TD-DFT or EOM-CCSD',
        systems=('molecule',),
    ),
)
_SYSTEM_NAMES = {'molecule': 'Molecules', 'crystal': 'Periodic systems'}

# The order the ticked calculations run in: dependencies first, independent of tick order.
_WORKFLOW_ORDER = (
    CalculationType.GEOMETRY_OPTIMISATION,
    CalculationType.SINGLE_POINT,
    CalculationType.VIBRATIONAL_FREQUENCIES,
    CalculationType.EXCITED_STATES,
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


EXCITED_STATE_METHODS = (('tddft', 'TD-DFT'), ('eom_ccsd', 'EOM-CCSD'))


@dataclass
class ExcitedStatesOptions:
    method: str = 'tddft'
    states: int = 5
    # TD-DFT (CIS or TD-HF with the Hartree–Fock family)
    tda: bool = True
    triplets: bool = False
    # The highest occupied and the lowest virtual orbitals excitations may use; 0 leaves the
    # engine's choice (ORCA: all but the core orbitals).
    occupied_orbitals: int = 0
    virtual_orbitals: int = 0
    # EOM-CCSD
    frozen_core: bool = True


class Calculations:
    def __init__(self):
        self.periodic = False  # the sample's kind, which some calculations do not allow
        self.reset()

    def reset(self) -> None:
        self.selected: set[CalculationType] = set()
        self.single_point = SinglePointOptions()
        self.geometry_optimisation = GeometryOptimisationOptions()
        self.vibrational_frequencies = VibrationalFrequenciesOptions()
        self.excited_states = ExcitedStatesOptions()

    def is_selected(self, calculation: CalculationType) -> bool:
        return calculation in self.selected

    def set_selected(self, calculation: CalculationType, value: bool) -> None:
        if value and not self.unavailable(calculation):
            self.selected.add(calculation)
        else:
            self.selected.discard(calculation)

    def unavailable(self, calculation: CalculationType) -> str:
        """Why the sample's kind does not allow this calculation ('Molecules only'), or ''."""
        systems = info(calculation).systems
        if ('crystal' if self.periodic else 'molecule') in systems:
            return ''
        return ' and '.join(_SYSTEM_NAMES[system] for system in systems) + ' only'

    def set_periodic(self, periodic: bool) -> None:
        """Follow the sample's kind; calculations it does not allow are unselected."""
        self.periodic = periodic
        self.selected = {calculation for calculation in self.selected if not self.unavailable(calculation)}

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
