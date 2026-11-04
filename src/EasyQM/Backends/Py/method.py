# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Method page backend part: engines, level of theory, SCF and run settings for QML.

Every engine has an adapter. The active engine is the first one that can run the sample
(ORCA a molecule, Quantum ESPRESSO a crystal), so it changes when a molecule replaces a
crystal or the other way round. The choice lists and values the page shows are the active
engine's; each engine keeps its own `logic.method.Method`, so switching back loses nothing.
"""

from dataclasses import fields
from pathlib import Path
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
from .logic.engines.quantum_espresso import QuantumEspressoAdapter
from .logic.method import Method as MethodLogic
from .logic.method import RunSettings


class Method(QObject):
    # The active engine, or what an engine's detection found, changed.
    engineChanged = Signal()
    levelOfTheoryChanged = Signal()
    systemChanged = Signal()
    scfChanged = Signal()
    runSettingsChanged = Signal()
    # The sample became a molecule or a crystal, or another crystal.
    sampleChanged = Signal()
    kpointsChanged = Signal()

    def __init__(
        self,
        adapters: Optional[list[EngineAdapter]] = None,
        settings: Optional[QSettings] = None,
        parent=None,
    ):
        super().__init__(parent)
        # In card order; the first that can run the sample is the active one.
        self._adapters = adapters if adapters is not None else [OrcaAdapter(), QuantumEspressoAdapter()]
        self._run = RunSettings()
        # The configured executables are machine settings, not project ones.
        self._settings = settings if settings is not None else QSettings('EasyScience', 'EasyQM')
        for adapter in self._adapters:
            adapter.executable = self._settings.value(_settings_key(adapter), '') or None
        self._infos = [adapter.detect() for adapter in self._adapters]
        self._methods = [adapter.default_method() for adapter in self._adapters]
        self._active = 0
        self._cell = None  # the sample's unit cell, set by PyBackend; None for a molecule

    # For the other backend parts (plain Python, not exposed to QML)

    @property
    def adapter(self) -> EngineAdapter:
        """The active engine's adapter."""
        return self._adapters[self._active]

    @property
    def info(self):
        return self._infos[self._active]

    @property
    def logic(self) -> MethodLogic:
        """The active engine's method."""
        return self._methods[self._active]

    @property
    def run_settings(self) -> RunSettings:
        return self._run

    def reset(self) -> None:
        """Every engine's default method and the default run settings (for PyBackend.reset).
        The executables and what their detection found stay: they are machine settings. The
        run settings object stays the same one, as the job holds it; the methods reach the
        job through PyBackend's engine relay."""
        self._methods = [adapter.default_method() for adapter in self._adapters]
        defaults = RunSettings()
        for field in fields(RunSettings):
            setattr(self._run, field.name, getattr(defaults, field.name))
        for signal in (
            self.engineChanged,
            self.levelOfTheoryChanged,
            self.systemChanged,
            self.scfChanged,
            self.runSettingsChanged,
            self.kpointsChanged,
        ):
            signal.emit()

    def set_sample_cell(self, cell) -> None:
        """The sample's `logic.sample.Cell`, or None for a molecule."""
        kind_changed = (cell is None) != (self._cell is None)
        self._cell = cell
        usable = [index for index, adapter in enumerate(self._adapters) if not adapter.system_problem(cell is not None)]
        if usable and self._active not in usable:
            self._active = usable[0]
            # Everything the page shows is the new engine's.
            for signal in (self.levelOfTheoryChanged, self.systemChanged, self.scfChanged):
                signal.emit()
        if kind_changed:
            self.engineChanged.emit()  # the active card, and why the others are grey
        self.sampleChanged.emit()
        self.kpointsChanged.emit()

    @property
    def _capabilities(self):
        return self.adapter.capabilities()

    # Engines

    @Property('QVariantList', notify=engineChanged)
    def engines(self) -> list:
        """One card per engine: [{name, found, text, path, program, active, problem}]."""
        periodic = self._cell is not None
        return [
            {
                'name': adapter.name,
                'found': info.found,
                'text': _card_text(info),
                'path': info.path,
                'program': adapter.programs[0] if adapter.programs else adapter.name,
                'active': index == self._active,
                'problem': adapter.system_problem(periodic),
            }
            for index, (adapter, info) in enumerate(zip(self._adapters, self._infos))
        ]

    # The active engine

    @Property(str, notify=engineChanged)
    def engineName(self) -> str:
        return self.adapter.name

    @Property(bool, notify=engineChanged)
    def engineFound(self) -> bool:
        return self.info.found

    @Property(str, notify=engineChanged)
    def engineVersion(self) -> str:
        return self.info.version

    @Property(str, notify=engineChanged)
    def enginePath(self) -> str:
        return self.info.path

    @Property(str, notify=engineChanged)
    def engineCardText(self) -> str:
        return _card_text(self.info)

    @Property(str, notify=engineChanged)
    def engineExecutableFilter(self) -> str:
        """File dialog filter for the active engine's executable, e.g. 'ORCA executable (orca orca.exe)'."""
        names = dict.fromkeys(name for program in self.adapter.programs for name in (program, f'{Path(program).stem}.exe'))
        return f'{self.adapter.name} executable ({" ".join(names)})'

    @Slot()
    def redetect(self) -> None:
        self._infos = [adapter.detect() for adapter in self._adapters]
        self.engineChanged.emit()

    @Slot(str)
    def setEnginePath(self, path: str) -> None:
        """Use this executable for the active engine instead of the one on PATH; empty goes back to PATH."""
        path = to_local_path(path)
        self.adapter.executable = path or None
        self._settings.setValue(_settings_key(self.adapter), path)
        self.redetect()

    # Sample

    @Property(bool, notify=sampleChanged)
    def periodic(self) -> bool:
        return self._cell is not None

    @Property(bool, notify=sampleChanged)
    def canRun(self) -> bool:
        """Whether the engine runs this kind of system; the Run button also needs a found engine."""
        return not self.cannotRunReason

    @Property(str, notify=sampleChanged)
    def cannotRunReason(self) -> str:
        return self.adapter.system_problem(self._cell is not None)

    # K-points (crystals)

    @Property(float, notify=kpointsChanged)
    def kpointSpacing(self) -> float:
        return self.logic.kpoints.spacing

    @Slot(float)
    def setKpointSpacing(self, value: float) -> None:
        """A new spacing also replaces a grid set by hand."""
        if value > 0:
            self.logic.kpoints.spacing = float(value)
            self.logic.kpoints.grid = None
            self.kpointsChanged.emit()

    @Property('QVariantList', notify=kpointsChanged)
    def kpointGrid(self) -> list:
        """[n1, n2, n3]: the grid set by hand, else the one from the spacing; [] for a molecule."""
        if self._cell is None:
            return []
        return list(self.logic.kpoints.for_cell(self._cell))

    @Slot(int, int, int)
    def setKpointGrid(self, n1: int, n2: int, n3: int) -> None:
        self.logic.kpoints.grid = tuple(max(1, int(n)) for n in (n1, n2, n3))
        self.kpointsChanged.emit()

    # Level of theory

    @Property(str, notify=levelOfTheoryChanged)
    def family(self) -> str:
        return self.logic.family

    @Slot(str)
    def setFamily(self, value: str) -> None:
        apply(self.logic, 'family', value, self.levelOfTheoryChanged)

    @Property('QVariantList', notify=engineChanged)
    def familyChoices(self) -> list:
        return choices(self._capabilities.families)

    @Property(str, notify=levelOfTheoryChanged)
    def functional(self) -> str:
        return self.logic.functional

    @Slot(str)
    def setFunctional(self, value: str) -> None:
        apply(self.logic, 'functional', value, self.levelOfTheoryChanged)

    @Property('QVariantList', notify=engineChanged)
    def functionalChoices(self) -> list:
        return choices(self._capabilities.functionals)

    @Property(str, notify=levelOfTheoryChanged)
    def dispersion(self) -> str:
        return self.logic.dispersion

    @Slot(str)
    def setDispersion(self, value: str) -> None:
        apply(self.logic, 'dispersion', value, self.levelOfTheoryChanged)

    @Property('QVariantList', notify=engineChanged)
    def dispersionChoices(self) -> list:
        return choices(self._capabilities.dispersions)

    @Property(str, notify=levelOfTheoryChanged)
    def basisSet(self) -> str:
        return self.logic.basis_set

    @Slot(str)
    def setBasisSet(self, value: str) -> None:
        apply(self.logic, 'basis_set', value, self.levelOfTheoryChanged)

    @Property('QVariantList', notify=engineChanged)
    def basisSetChoices(self) -> list:
        return choices(self._capabilities.basis_sets)

    @Property(str, notify=levelOfTheoryChanged)
    def auxiliaryBasis(self) -> str:
        return self.logic.auxiliary_basis

    @Slot(str)
    def setAuxiliaryBasis(self, value: str) -> None:
        apply(self.logic, 'auxiliary_basis', value, self.levelOfTheoryChanged)

    @Property('QVariantList', notify=engineChanged)
    def auxiliaryBasisChoices(self) -> list:
        return choices(self._capabilities.auxiliary_bases)

    # System

    @Property(str, notify=systemChanged)
    def reference(self) -> str:
        return self.logic.reference

    @Slot(str)
    def setReference(self, value: str) -> None:
        apply(self.logic, 'reference', value, self.systemChanged)

    @Property('QVariantList', notify=engineChanged)
    def referenceChoices(self) -> list:
        return choices(self._capabilities.references)

    @Property(str, notify=systemChanged)
    def solvation(self) -> str:
        return self.logic.solvation

    @Slot(str)
    def setSolvation(self, value: str) -> None:
        apply(self.logic, 'solvation', value, self.systemChanged)

    @Property('QVariantList', notify=engineChanged)
    def solvationChoices(self) -> list:
        return choices(self._capabilities.solvations)

    @Property(str, notify=systemChanged)
    def occupations(self) -> str:
        return self.logic.occupations

    @Slot(str)
    def setOccupations(self, value: str) -> None:
        apply(self.logic, 'occupations', value, self.systemChanged)

    @Property('QVariantList', notify=engineChanged)
    def occupationsChoices(self) -> list:
        return choices(self._capabilities.occupations)

    # SCF

    @Property(str, notify=scfChanged)
    def scfConvergence(self) -> str:
        return self.logic.scf_convergence

    @Slot(str)
    def setScfConvergence(self, value: str) -> None:
        apply(self.logic, 'scf_convergence', value, self.scfChanged)

    @Property('QVariantList', notify=engineChanged)
    def scfConvergenceChoices(self) -> list:
        return choices(self._capabilities.scf_convergences)

    @Property(int, notify=scfChanged)
    def scfMaxIterations(self) -> int:
        return self.logic.scf_max_iterations

    @Slot(int)
    def setScfMaxIterations(self, value: int) -> None:
        apply(self.logic, 'scf_max_iterations', int(value), self.scfChanged)

    @Property(str, notify=scfChanged)
    def integrationGrid(self) -> str:
        return self.logic.integration_grid

    @Slot(str)
    def setIntegrationGrid(self, value: str) -> None:
        apply(self.logic, 'integration_grid', value, self.scfChanged)

    @Property('QVariantList', notify=engineChanged)
    def integrationGridChoices(self) -> list:
        return choices(self._capabilities.integration_grids)

    @Property(bool, notify=scfChanged)
    def stabilityCheck(self) -> bool:
        return self.logic.stability_check

    @Slot(bool)
    def setStabilityCheck(self, value: bool) -> None:
        apply(self.logic, 'stability_check', bool(value), self.scfChanged)

    @Property(bool, notify=engineChanged)
    def stabilityCheckOffered(self) -> bool:
        return self._capabilities.stability_check

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


def _settings_key(adapter: EngineAdapter) -> str:
    return f'engines/{adapter.name}/executable'


def _card_text(info) -> str:
    """Card subtitle: version line when found, otherwise why the card is grey."""
    if not info.found:
        return 'Not detected · add the executable to PATH or configure its path'
    parts = [f'Version {info.version}' if info.version else 'Version unknown']
    if info.detail:
        parts.append(info.detail)
    return ' · '.join(parts)
