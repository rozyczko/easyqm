# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Method page backend part: engine, level of theory, SCF and run settings for QML."""

from typing import Optional

from PySide6.QtCore import Property
from PySide6.QtCore import QObject
from PySide6.QtCore import QSettings
from PySide6.QtCore import Signal
from PySide6.QtCore import Slot

from .helpers import apply
from .helpers import choices
from .helpers import to_local_path
from .logic.engines.base import EngineAdapter
from .logic.engines.orca import OrcaAdapter
from .logic.method import Method as MethodLogic
from .logic.method import RunSettings


class Method(QObject):
    engineChanged = Signal()
    levelOfTheoryChanged = Signal()
    systemChanged = Signal()
    scfChanged = Signal()
    runSettingsChanged = Signal()

    def __init__(
        self,
        adapter: Optional[EngineAdapter] = None,
        logic: Optional[MethodLogic] = None,
        settings: Optional[QSettings] = None,
        parent=None,
    ):
        super().__init__(parent)
        # PoC1 has one engine; the Method page shows it as the only card.
        self._adapter = adapter if adapter is not None else OrcaAdapter()
        self._capabilities = self._adapter.capabilities()
        self._logic = logic if logic is not None else MethodLogic()
        self._run = RunSettings()
        # The configured executable is a machine setting, not a project one.
        self._settings = settings if settings is not None else QSettings('EasyScience', 'EasyQM')
        self._adapter.executable = self._settings.value(self._settings_key, '') or None
        self._info = self._adapter.detect()

    # For the other backend parts (plain Python, not exposed to QML)

    @property
    def adapter(self) -> EngineAdapter:
        return self._adapter

    @property
    def info(self):
        return self._info

    @property
    def logic(self) -> MethodLogic:
        return self._logic

    @property
    def run_settings(self) -> RunSettings:
        return self._run

    @property
    def _settings_key(self) -> str:
        return f'engines/{self._adapter.name}/executable'

    # Engine

    @Property(str, constant=True)
    def engineName(self) -> str:
        return self._adapter.name

    @Property(bool, notify=engineChanged)
    def engineFound(self) -> bool:
        return self._info.found

    @Property(str, notify=engineChanged)
    def engineVersion(self) -> str:
        return self._info.version

    @Property(str, notify=engineChanged)
    def enginePath(self) -> str:
        return self._info.path

    @Property(str, notify=engineChanged)
    def engineCardText(self) -> str:
        """Card subtitle: version line when found, otherwise why the card is grey."""
        if not self._info.found:
            return 'Not detected · add the executable to PATH or configure its path'
        parts = [f'Version {self._info.version}' if self._info.version else 'Version unknown']
        if self._info.detail:
            parts.append(self._info.detail)
        return ' · '.join(parts)

    @Slot()
    def redetect(self) -> None:
        self._info = self._adapter.detect()
        self.engineChanged.emit()

    @Slot(str)
    def setEnginePath(self, path: str) -> None:
        """Use this executable instead of the one on PATH; an empty path goes back to PATH."""
        path = to_local_path(path)
        self._adapter.executable = path or None
        self._settings.setValue(self._settings_key, path)
        self.redetect()

    # Level of theory

    @Property(str, notify=levelOfTheoryChanged)
    def family(self) -> str:
        return self._logic.family

    @Slot(str)
    def setFamily(self, value: str) -> None:
        apply(self._logic, 'family', value, self.levelOfTheoryChanged)

    @Property('QVariantList', constant=True)
    def familyChoices(self) -> list:
        return choices(self._capabilities.families)

    @Property(str, notify=levelOfTheoryChanged)
    def functional(self) -> str:
        return self._logic.functional

    @Slot(str)
    def setFunctional(self, value: str) -> None:
        apply(self._logic, 'functional', value, self.levelOfTheoryChanged)

    @Property('QVariantList', constant=True)
    def functionalChoices(self) -> list:
        return choices(self._capabilities.functionals)

    @Property(str, notify=levelOfTheoryChanged)
    def dispersion(self) -> str:
        return self._logic.dispersion

    @Slot(str)
    def setDispersion(self, value: str) -> None:
        apply(self._logic, 'dispersion', value, self.levelOfTheoryChanged)

    @Property('QVariantList', constant=True)
    def dispersionChoices(self) -> list:
        return choices(self._capabilities.dispersions)

    @Property(str, notify=levelOfTheoryChanged)
    def basisSet(self) -> str:
        return self._logic.basis_set

    @Slot(str)
    def setBasisSet(self, value: str) -> None:
        apply(self._logic, 'basis_set', value, self.levelOfTheoryChanged)

    @Property('QVariantList', constant=True)
    def basisSetChoices(self) -> list:
        return choices(self._capabilities.basis_sets)

    @Property(str, notify=levelOfTheoryChanged)
    def auxiliaryBasis(self) -> str:
        return self._logic.auxiliary_basis

    @Slot(str)
    def setAuxiliaryBasis(self, value: str) -> None:
        apply(self._logic, 'auxiliary_basis', value, self.levelOfTheoryChanged)

    @Property('QVariantList', constant=True)
    def auxiliaryBasisChoices(self) -> list:
        return choices(self._capabilities.auxiliary_bases)

    # System

    @Property(str, notify=systemChanged)
    def reference(self) -> str:
        return self._logic.reference

    @Slot(str)
    def setReference(self, value: str) -> None:
        apply(self._logic, 'reference', value, self.systemChanged)

    @Property('QVariantList', constant=True)
    def referenceChoices(self) -> list:
        return choices(self._capabilities.references)

    @Property(str, notify=systemChanged)
    def solvation(self) -> str:
        return self._logic.solvation

    @Slot(str)
    def setSolvation(self, value: str) -> None:
        apply(self._logic, 'solvation', value, self.systemChanged)

    @Property('QVariantList', constant=True)
    def solvationChoices(self) -> list:
        return choices(self._capabilities.solvations)

    # SCF

    @Property(str, notify=scfChanged)
    def scfConvergence(self) -> str:
        return self._logic.scf_convergence

    @Slot(str)
    def setScfConvergence(self, value: str) -> None:
        apply(self._logic, 'scf_convergence', value, self.scfChanged)

    @Property('QVariantList', constant=True)
    def scfConvergenceChoices(self) -> list:
        return choices(self._capabilities.scf_convergences)

    @Property(int, notify=scfChanged)
    def scfMaxIterations(self) -> int:
        return self._logic.scf_max_iterations

    @Slot(int)
    def setScfMaxIterations(self, value: int) -> None:
        apply(self._logic, 'scf_max_iterations', int(value), self.scfChanged)

    @Property(str, notify=scfChanged)
    def integrationGrid(self) -> str:
        return self._logic.integration_grid

    @Slot(str)
    def setIntegrationGrid(self, value: str) -> None:
        apply(self._logic, 'integration_grid', value, self.scfChanged)

    @Property('QVariantList', constant=True)
    def integrationGridChoices(self) -> list:
        return choices(self._capabilities.integration_grids)

    @Property(bool, notify=scfChanged)
    def stabilityCheck(self) -> bool:
        return self._logic.stability_check

    @Slot(bool)
    def setStabilityCheck(self, value: bool) -> None:
        apply(self._logic, 'stability_check', bool(value), self.scfChanged)

    # Run settings

    @Property(int, notify=runSettingsChanged)
    def cores(self) -> int:
        return self._run.cores

    @Slot(int)
    def setCores(self, value: int) -> None:
        apply(self._run, 'cores', int(value), self.runSettingsChanged)

    @Property(int, notify=runSettingsChanged)
    def memoryGb(self) -> int:
        return self._run.memory_gb

    @Slot(int)
    def setMemoryGb(self, value: int) -> None:
        apply(self._run, 'memory_gb', int(value), self.runSettingsChanged)
