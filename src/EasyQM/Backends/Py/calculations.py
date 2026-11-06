# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Calculations page backend part: the QML-facing proxy of `logic.calculations.Calculations`."""

from typing import Optional

from PySide6.QtCore import Property
from PySide6.QtCore import QObject
from PySide6.QtCore import Signal
from PySide6.QtCore import Slot

from .helpers import apply
from .helpers import choices
from .logic.calculations import CATALOGUE
from .logic.calculations import EXCITED_STATE_METHODS
from .logic.calculations import FREQUENCY_TYPES
from .logic.calculations import OPTIMISATION_CONVERGENCES
from .logic.calculations import OPTIMISATION_TARGETS
from .logic.calculations import SINGLE_POINT_GEOMETRIES
from .logic.calculations import Calculations as CalculationsLogic
from .logic.calculations import CalculationType
from .logic.calculations import info


class Calculations(QObject):
    selectionChanged = Signal()
    singlePointChanged = Signal()
    optimisationChanged = Signal()
    frequenciesChanged = Signal()
    excitedStatesChanged = Signal()
    # Order or labels of the workflow steps: on selection and single point geometry changes.
    workflowChanged = Signal()

    # For the other backend parts.
    externalSelectionChanged = Signal()

    def __init__(self, logic: Optional[CalculationsLogic] = None, parent=None):
        super().__init__(parent)
        self._logic = logic if logic is not None else CalculationsLogic()

    @property
    def logic(self) -> CalculationsLogic:
        """For the other backend parts (plain Python, not exposed to QML)."""
        return self._logic

    def reset(self) -> None:
        """Nothing selected, every option at its default (for PyBackend.reset). The logic
        object stays the same one: the job holds it."""
        self._logic.reset()
        for signal in (
            self.selectionChanged,
            self.singlePointChanged,
            self.optimisationChanged,
            self.frequenciesChanged,
            self.excitedStatesChanged,
            self.workflowChanged,
            self.externalSelectionChanged,
        ):
            signal.emit()

    def set_periodic(self, periodic: bool) -> None:
        """Follow the sample's kind (for PyBackend): rows it does not allow are greyed and unticked."""
        if periodic == self._logic.periodic:
            return
        selected = set(self._logic.selected)
        self._logic.set_periodic(periodic)
        self.selectionChanged.emit()  # the rows' enabled state
        if self._logic.selected != selected:
            self.workflowChanged.emit()
            self.externalSelectionChanged.emit()

    # Table and workflow

    @Property('QVariantList', notify=selectionChanged)
    def rows(self) -> list:
        return [
            {
                'type': entry.type.value,
                'name': entry.name,
                'description': entry.description,
                'results': entry.results,
                'notes': entry.notes,
                'selected': self._logic.is_selected(entry.type),
                'enabled': not self._logic.unavailable(entry.type),
                'reason': self._logic.unavailable(entry.type),
            }
            for entry in CATALOGUE
        ]

    @Property(int, notify=selectionChanged)
    def selectedCount(self) -> int:
        return len(self._logic.selected)

    @Property('QVariantList', notify=selectionChanged)
    def selectedNames(self) -> list:
        return self._logic.selected_names()

    @Property('QVariantList', notify=workflowChanged)
    def workflow(self) -> list:
        steps = self._logic.workflow()
        result = []
        for number, calculation in enumerate(steps, start=1):
            label = info(calculation).name
            if calculation is CalculationType.SINGLE_POINT and CalculationType.GEOMETRY_OPTIMISATION in steps:
                at_input = self._logic.single_point.geometry == 'input'
                label += ' (at input geometry)' if at_input else ' (at optimised geometry)'
            result.append({'step': number, 'type': calculation.value, 'label': label})
        return result

    @Slot(str, result=bool)
    def isSelected(self, calculation: str) -> bool:
        return self._logic.is_selected(CalculationType(calculation))

    @Slot(str, bool)
    def setSelected(self, calculation: str, value: bool) -> None:
        calculation = CalculationType(calculation)
        selected = set(self._logic.selected)
        self.set_selection(selected | {calculation} if value else selected - {calculation})

    def set_selection(self, calculations: set) -> None:
        """Select exactly these `CalculationType`s, with one change notification; those the
        sample's kind does not allow stay unselected."""
        calculations = {calculation for calculation in calculations if not self._logic.unavailable(calculation)}
        if calculations == self._logic.selected:
            return
        self._logic.selected = set(calculations)
        self.selectionChanged.emit()
        self.workflowChanged.emit()
        self.externalSelectionChanged.emit()

    # Single point energy

    @Property(bool, notify=singlePointChanged)
    def singlePointPrintOrbitals(self) -> bool:
        return self._logic.single_point.print_orbitals

    @Slot(bool)
    def setSinglePointPrintOrbitals(self, value: bool) -> None:
        apply(self._logic.single_point, 'print_orbitals', bool(value), self.singlePointChanged)

    @Property(str, notify=singlePointChanged)
    def singlePointGeometry(self) -> str:
        return self._logic.single_point.geometry

    @Slot(str)
    def setSinglePointGeometry(self, value: str) -> None:
        apply(self._logic.single_point, 'geometry', value, self.singlePointChanged, self.workflowChanged)

    @Property('QVariantList', constant=True)
    def singlePointGeometryChoices(self) -> list:
        return choices(SINGLE_POINT_GEOMETRIES)

    # Geometry optimisation

    @Property(str, notify=optimisationChanged)
    def optConvergence(self) -> str:
        return self._logic.geometry_optimisation.convergence

    @Slot(str)
    def setOptConvergence(self, value: str) -> None:
        apply(self._logic.geometry_optimisation, 'convergence', value, self.optimisationChanged)

    @Property('QVariantList', constant=True)
    def optConvergenceChoices(self) -> list:
        return choices(OPTIMISATION_CONVERGENCES)

    @Property(int, notify=optimisationChanged)
    def optMaxSteps(self) -> int:
        return self._logic.geometry_optimisation.max_steps

    @Slot(int)
    def setOptMaxSteps(self, value: int) -> None:
        apply(self._logic.geometry_optimisation, 'max_steps', int(value), self.optimisationChanged)

    @Property(str, notify=optimisationChanged)
    def optOptimise(self) -> str:
        return self._logic.geometry_optimisation.optimise

    @Slot(str)
    def setOptOptimise(self, value: str) -> None:
        apply(self._logic.geometry_optimisation, 'optimise', value, self.optimisationChanged)

    @Property('QVariantList', constant=True)
    def optOptimiseChoices(self) -> list:
        return choices(OPTIMISATION_TARGETS)

    @Property(bool, notify=optimisationChanged)
    def optKeepTrajectory(self) -> bool:
        return self._logic.geometry_optimisation.keep_trajectory

    @Slot(bool)
    def setOptKeepTrajectory(self, value: bool) -> None:
        apply(self._logic.geometry_optimisation, 'keep_trajectory', bool(value), self.optimisationChanged)

    # Vibrational frequencies

    @Property(str, notify=frequenciesChanged)
    def freqType(self) -> str:
        return self._logic.vibrational_frequencies.type

    @Slot(str)
    def setFreqType(self, value: str) -> None:
        apply(self._logic.vibrational_frequencies, 'type', value, self.frequenciesChanged)

    @Property('QVariantList', constant=True)
    def freqTypeChoices(self) -> list:
        return choices(FREQUENCY_TYPES)

    @Property(float, notify=frequenciesChanged)
    def freqTemperature(self) -> float:
        return self._logic.vibrational_frequencies.temperature

    @Slot(float)
    def setFreqTemperature(self, value: float) -> None:
        apply(self._logic.vibrational_frequencies, 'temperature', float(value), self.frequenciesChanged)

    @Property(float, notify=frequenciesChanged)
    def freqPressure(self) -> float:
        return self._logic.vibrational_frequencies.pressure

    @Slot(float)
    def setFreqPressure(self, value: float) -> None:
        apply(self._logic.vibrational_frequencies, 'pressure', float(value), self.frequenciesChanged)

    @Property(bool, notify=frequenciesChanged)
    def freqRaman(self) -> bool:
        return self._logic.vibrational_frequencies.raman

    @Slot(bool)
    def setFreqRaman(self, value: bool) -> None:
        apply(self._logic.vibrational_frequencies, 'raman', bool(value), self.frequenciesChanged)

    # Excited states

    @Property(str, notify=excitedStatesChanged)
    def excMethod(self) -> str:
        return self._logic.excited_states.method

    @Slot(str)
    def setExcMethod(self, value: str) -> None:
        apply(self._logic.excited_states, 'method', value, self.excitedStatesChanged)

    @Property('QVariantList', constant=True)
    def excMethodChoices(self) -> list:
        return choices(EXCITED_STATE_METHODS)

    @Property(int, notify=excitedStatesChanged)
    def excStates(self) -> int:
        return self._logic.excited_states.states

    @Slot(int)
    def setExcStates(self, value: int) -> None:
        apply(self._logic.excited_states, 'states', int(value), self.excitedStatesChanged)

    @Property(bool, notify=excitedStatesChanged)
    def excTda(self) -> bool:
        return self._logic.excited_states.tda

    @Slot(bool)
    def setExcTda(self, value: bool) -> None:
        apply(self._logic.excited_states, 'tda', bool(value), self.excitedStatesChanged)

    @Property(bool, notify=excitedStatesChanged)
    def excTriplets(self) -> bool:
        return self._logic.excited_states.triplets

    @Slot(bool)
    def setExcTriplets(self, value: bool) -> None:
        apply(self._logic.excited_states, 'triplets', bool(value), self.excitedStatesChanged)

    @Property(int, notify=excitedStatesChanged)
    def excOccupiedOrbitals(self) -> int:
        return self._logic.excited_states.occupied_orbitals

    @Slot(int)
    def setExcOccupiedOrbitals(self, value: int) -> None:
        apply(self._logic.excited_states, 'occupied_orbitals', int(value), self.excitedStatesChanged)

    @Property(int, notify=excitedStatesChanged)
    def excVirtualOrbitals(self) -> int:
        return self._logic.excited_states.virtual_orbitals

    @Slot(int)
    def setExcVirtualOrbitals(self, value: int) -> None:
        apply(self._logic.excited_states, 'virtual_orbitals', int(value), self.excitedStatesChanged)

    @Property(bool, notify=excitedStatesChanged)
    def excFrozenCore(self) -> bool:
        return self._logic.excited_states.frozen_core

    @Slot(bool)
    def setExcFrozenCore(self, value: bool) -> None:
        apply(self._logic.excited_states, 'frozen_core', bool(value), self.excitedStatesChanged)
