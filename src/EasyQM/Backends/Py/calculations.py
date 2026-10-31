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
        if self._logic.is_selected(calculation) == bool(value):
            return
        self._logic.set_selected(calculation, bool(value))
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
