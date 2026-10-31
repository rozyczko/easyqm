# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Project page backend part: the QML-facing proxy of `logic.project.Project`."""

from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Property
from PySide6.QtCore import QObject
from PySide6.QtCore import Signal
from PySide6.QtCore import Slot

from .helpers import to_local_path
from .logic.project import Engine
from .logic.project import Project as ProjectLogic
from .logic.project import ProjectStatus


class Project(QObject):
    createdChanged = Signal()
    nameChanged = Signal()
    descriptionChanged = Signal()
    locationChanged = Signal()
    datesChanged = Signal()
    sampleNameChanged = Signal()
    calculationsChanged = Signal()
    engineChanged = Signal()
    statusChanged = Signal()
    autoSaveChanged = Signal()
    lastSavedChanged = Signal()
    hasUnsavedChangesChanged = Signal()

    # For the other backend parts: the project they work on was replaced (create, load, reset).
    externalProjectChanged = Signal()
    projectSaved = Signal(str)
    projectSaveError = Signal(str)
    projectLoadError = Signal(str)

    def __init__(self, logic: Optional[ProjectLogic] = None, parent=None):
        super().__init__(parent)
        self._logic = logic if logic is not None else ProjectLogic()
        self._last_saved = ''
        self._has_unsaved_changes = False
        # A session preference, not project content: every change is written to disk at once.
        self._auto_save = True

    # Read-only properties

    @Property(bool, notify=createdChanged)
    def created(self) -> bool:
        return self._logic.created

    @Property(str, notify=locationChanged)
    def location(self) -> str:
        """Full path of the project folder: where it is, or where `create` would put it."""
        return str(self._logic.path)

    @Property(str, notify=locationChanged)
    def parentDirectory(self) -> str:
        return str(self._logic.parent)

    @Property(str, notify=datesChanged)
    def createdAt(self) -> str:
        """ISO-8601, or '' before creation. QML formats it with the user's locale."""
        return self._logic.as_dict()['created']

    @Property(str, notify=datesChanged)
    def modifiedAt(self) -> str:
        return self._logic.as_dict()['modified']

    @Property(str, notify=statusChanged)
    def statusLabel(self) -> str:
        return self._logic.status.label

    @Property('QVariantList', constant=True)
    def engineNames(self) -> list:
        return [engine.value for engine in Engine if engine is not Engine.NONE]

    @Property(str, notify=lastSavedChanged)
    def lastSaved(self) -> str:
        """ISO-8601 time of the last save made in this session, or '' if none."""
        return self._last_saved

    @Property(bool, notify=hasUnsavedChangesChanged)
    def hasUnsavedChanges(self) -> bool:
        return self._has_unsaved_changes

    # Properties with setters. The other backend parts call the setters too (the Sample part
    # will set sampleName, the runner the status); every change goes through `_apply`, so it is
    # auto-saved or flagged as unsaved.

    @Property(str, notify=nameChanged)
    def name(self) -> str:
        return self._logic.name

    @Slot(str)
    def setName(self, value: str) -> None:
        # Before creation the name is also the folder name, so the location follows it.
        self._apply('name', value, self.nameChanged, self.locationChanged)

    @Property(str, notify=descriptionChanged)
    def description(self) -> str:
        return self._logic.description

    @Slot(str)
    def setDescription(self, value: str) -> None:
        self._apply('description', value, self.descriptionChanged)

    @Slot(str)
    def setLocation(self, value: str) -> None:
        """Set the full project path as the create dialog composes it; only its parent is kept.

        Ignored once the project is on disk: moving a project folder is not supported.
        """
        if self._logic.created:
            return
        self._apply('parent', Path(to_local_path(value)).parent, self.locationChanged)

    @Property(str, notify=sampleNameChanged)
    def sampleName(self) -> str:
        return self._logic.sample_name

    @Slot(str)
    def setSampleName(self, value: str) -> None:
        self._apply('sample_name', value, self.sampleNameChanged)

    @Property('QVariantList', notify=calculationsChanged)
    def calculations(self) -> list:
        return list(self._logic.calculations)

    @Slot('QVariantList')
    def setCalculations(self, value: list) -> None:
        self._apply('calculations', [str(item) for item in value], self.calculationsChanged)

    @Property(str, notify=engineChanged)
    def engine(self) -> str:
        return self._logic.engine.value

    @Slot(str)
    def setEngine(self, value: str) -> None:
        self._apply('engine', Engine(value), self.engineChanged)

    @Property(str, notify=statusChanged)
    def status(self) -> str:
        return self._logic.status.value

    @Slot(str)
    def setStatus(self, value: str) -> None:
        self._apply('status', ProjectStatus(value), self.statusChanged)

    @Property(bool, notify=autoSaveChanged)
    def autoSave(self) -> bool:
        return self._auto_save

    @Slot(bool)
    def setAutoSave(self, value: bool) -> None:
        value = bool(value)
        if self._auto_save == value:
            return
        self._auto_save = value
        self.autoSaveChanged.emit()
        if value and self._has_unsaved_changes:
            self.save()

    # Lifecycle

    @Slot()
    def create(self) -> None:
        try:
            self._logic.create()
        except Exception as error:
            self.projectSaveError.emit(self._save_error_message(error))
            if self._logic.created:
                # The folder was made but the file was not written: keep Save available.
                self._notify_all()
                self._set_unsaved(True)
            return
        self._notify_all()
        self._mark_saved()
        self.externalProjectChanged.emit()

    @Slot()
    def save(self) -> None:
        if not self._logic.created:
            self.projectSaveError.emit('No project has been created yet.\nCreate or open a project before saving.')
            return
        try:
            self._logic.save()
        except Exception as error:
            self.projectSaveError.emit(self._save_error_message(error))
            return
        self.datesChanged.emit()
        self._mark_saved()

    @Slot(str)
    def load(self, path: str) -> None:
        path = to_local_path(path)
        try:
            self._logic.load(path)
        except FileNotFoundError:
            self.projectLoadError.emit(f'No project file was found at "{path}".')
            return
        except ValueError as error:
            self.projectLoadError.emit(f'The project at "{path}" could not be read.\n\n{error}')
            return
        except OSError as error:
            self.projectLoadError.emit(f'The project at "{path}" could not be opened.\n\nDetails: {error}')
            return
        self._replace_project()

    @Slot()
    def reset(self) -> None:
        self._logic.reset()
        self._replace_project()

    # Helpers

    def _apply(self, attribute: str, value, *signals: Signal) -> None:
        """Set one logic attribute, notify QML and record the change, if the value differs."""
        if getattr(self._logic, attribute) == value:
            return
        setattr(self._logic, attribute, value)
        for signal in signals:
            signal.emit()
        self._mark_dirty()

    def _mark_dirty(self) -> None:
        # Nothing on disk to differ from until the project is created.
        if not self._logic.created:
            return
        if self._auto_save:
            self.save()
        else:
            self._set_unsaved(True)

    def _set_unsaved(self, value: bool) -> None:
        if self._has_unsaved_changes != value:
            self._has_unsaved_changes = value
            self.hasUnsavedChangesChanged.emit()

    def _mark_saved(self) -> None:
        self._set_unsaved(False)
        self._last_saved = datetime.now().astimezone().isoformat(timespec='seconds')
        self.lastSavedChanged.emit()
        self.projectSaved.emit(str(self._logic.path_json))

    def _replace_project(self) -> None:
        """Common tail of load and reset: a different project is now in memory."""
        if self._last_saved:
            self._last_saved = ''
            self.lastSavedChanged.emit()
        self._set_unsaved(False)
        self._notify_all()
        self.externalProjectChanged.emit()

    def _notify_all(self) -> None:
        for signal in (
            self.createdChanged,
            self.nameChanged,
            self.descriptionChanged,
            self.locationChanged,
            self.datesChanged,
            self.sampleNameChanged,
            self.calculationsChanged,
            self.engineChanged,
            self.statusChanged,
        ):
            signal.emit()

    def _save_error_message(self, error: Exception) -> str:
        path = self._logic.path_json
        if isinstance(error, FileExistsError):
            explanation = f'A project already exists at "{self._logic.path}".\nChoose a different name or location.'
        elif isinstance(error, PermissionError):
            explanation = f'No permission to write "{path}".'
        elif isinstance(error, OSError):
            explanation = f'The project could not be written to "{path}".'
        else:
            explanation = f'Failed to save the project to "{path}".'
        return f'{explanation}\n\nDetails: {error}'
