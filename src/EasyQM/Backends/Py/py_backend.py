# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
from PySide6.QtCore import Property
from PySide6.QtCore import QObject
from PySide6.QtCore import Signal
from PySide6.QtCore import Slot

from .calculations import Calculations
from .job import Job
from .logic.method import describe
from .method import Method
from .project import Project
from .results import Results
from .sample import Sample


class PyBackend(QObject):
    """Entry point of the Python backend, registered as the QML singleton `Backends.PyBackend`.

    Holds one backend part per GUI page and the connections between them.
    """

    editedChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project = Project(parent=self)
        self._sample = Sample(parent=self)
        self._calculations = Calculations(parent=self)
        self._method = Method(parent=self)
        self._job = Job(
            adapter=self._method.adapter,
            sample=self._sample.logic,
            calculations=self._calculations.logic,
            method=self._method.logic,
            settings=self._method.run_settings,
            parent=self,
        )
        self._results = Results(parent=self)
        # Changes since start-up or the last reset: to the parts, whose state the project file
        # does not hold, and to the project's own fields.
        self._parts_edited = False
        self._project_edited = False
        self._connect_parts()
        self._track_edits()

    @Property('QVariant', constant=True)
    def project(self) -> Project:
        return self._project

    @Property('QVariant', constant=True)
    def sample(self) -> Sample:
        return self._sample

    @Property('QVariant', constant=True)
    def calculations(self) -> Calculations:
        return self._calculations

    @Property('QVariant', constant=True)
    def method(self) -> Method:
        return self._method

    @Property('QVariant', constant=True)
    def job(self) -> Job:
        return self._job

    @Property('QVariant', constant=True)
    def results(self) -> Results:
        return self._results

    # Reset (the app bar button)

    @Property(bool, notify=editedChanged)
    def edited(self) -> bool:
        """Whether a reset would discard work: the sample, calculations or method changed or a
        job ran since start-up or the last reset (the project file holds none of it), the
        project has unsaved changes, or it was edited and never created."""
        project = self._project
        return self._parts_edited or project.hasUnsavedChanges or (not project.created and self._project_edited)

    @Slot()
    def reset(self) -> None:
        """Everything back to its start-up state: no project, the benzene sample, nothing
        selected, the default method and run settings, no job or results. The engines'
        executables stay, and so do the project and run folders on disk. Refused while a job
        runs. The parts reset their objects in place: the job holds the logic objects."""
        if self._job.running:
            return
        self._project.reset()
        self._sample.reset()  # the relay also gives the method part the molecule
        self._calculations.reset()
        self._method.reset()
        self._relay_engine()
        self._job.reset()
        self._results.reset()
        self._parts_edited = self._project_edited = False
        self.editedChanged.emit()

    def _track_edits(self) -> None:
        # After the start-up relays, which change the parts without the user.
        parts = (
            self._sample.externalSampleChanged,
            self._sample.atomsChanged,  # fixed flags
            self._calculations.selectionChanged,
            self._calculations.singlePointChanged,
            self._calculations.optimisationChanged,
            self._calculations.frequenciesChanged,
            self._method.levelOfTheoryChanged,
            self._method.systemChanged,
            self._method.scfChanged,
            self._method.runSettingsChanged,
            self._method.kpointsChanged,
            self._job.stateChanged,
        )
        for signal in parts:
            signal.connect(self._part_edited)
        for signal in (self._project.nameChanged, self._project.descriptionChanged):
            signal.connect(self._project_field_edited)
        for signal in (self._project.createdChanged, self._project.hasUnsavedChangesChanged):
            signal.connect(self.editedChanged)

    def _part_edited(self) -> None:
        if not self._parts_edited:
            self._parts_edited = True
            self.editedChanged.emit()

    def _project_field_edited(self) -> None:
        if not self._project_edited:
            self._project_edited = True
            self.editedChanged.emit()

    # Relays between parts. The project summarises the other parts; the setters it offers
    # go through its change tracking, so a created project is saved or flagged like any edit.

    def _connect_parts(self) -> None:
        self._sample.externalSampleChanged.connect(self._relay_sample)
        self._calculations.externalSelectionChanged.connect(self._relay_calculations)
        self._method.engineChanged.connect(self._relay_engine)
        self._project.createdChanged.connect(self._relay_project_folder)
        self._project.locationChanged.connect(self._relay_project_folder)
        self._job.stateChanged.connect(self._relay_job_state)
        self._job.stateChanged.connect(self._relay_results)
        # The parts hold their initial state before any signal fires.
        self._relay_sample()
        self._relay_calculations()
        self._relay_engine()
        self._relay_project_folder()

    def _relay_sample(self) -> None:
        self._project.setSampleName(f'{self._sample.formula}, {self._sample.atomCount} atoms')
        self._method.set_sample_cell(self._sample.logic.cell)

    def _relay_calculations(self) -> None:
        self._project.setCalculations(self._calculations.selectedNames)

    def _relay_engine(self) -> None:
        self._project.setEngine(self._method.engineName)
        self._job.set_engine(self._method.adapter, self._method.logic)
        self._job.set_executable(self._method.enginePath if self._method.engineFound else '')

    def _relay_project_folder(self) -> None:
        # Runs go into the project folder once it exists, into the scratch folder before.
        self._job.set_root_folder(self._project.location if self._project.created else '')

    def _relay_job_state(self) -> None:
        # JobState and ProjectStatus share their values, except the idle state of a new job.
        if self._job.state != 'idle':
            self._project.setStatus(self._job.state)

    def _relay_results(self) -> None:
        # A starting job invalidates the shown results; an ended one, even failed or stopped,
        # shows whatever its output holds. A converged optimisation also moves the sample to
        # its final geometry, so the next job starts from there.
        if self._job.state == 'running':
            self._results.clear(describe(self._method.logic, self._method.adapter.capabilities()))
        elif self._job.state != 'idle':
            results = self._job.adapter.parse(self._job.output)
            self._results.set_results(results)
            optimisation = results.optimisation
            if self._job.state == 'completed' and optimisation is not None and optimisation.converged:
                self._sample.apply_optimisation(optimisation)
