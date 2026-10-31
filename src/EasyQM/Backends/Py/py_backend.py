# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
from PySide6.QtCore import Property
from PySide6.QtCore import QObject

from .calculations import Calculations
from .job import Job
from .method import Method
from .project import Project
from .sample import Sample


class PyBackend(QObject):
    """Entry point of the Python backend, registered as the QML singleton `Backends.PyBackend`.

    Holds one backend part per GUI page and the connections between them.
    """

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
        self._connect_parts()

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

    # Relays between parts. The project summarises the other parts; the setters it offers
    # go through its change tracking, so a created project is saved or flagged like any edit.

    def _connect_parts(self) -> None:
        self._sample.externalSampleChanged.connect(self._relay_sample)
        self._calculations.externalSelectionChanged.connect(self._relay_calculations)
        self._method.engineChanged.connect(self._relay_engine)
        self._project.createdChanged.connect(self._relay_project_folder)
        self._project.locationChanged.connect(self._relay_project_folder)
        self._job.stateChanged.connect(self._relay_job_state)
        # The parts hold their initial state before any signal fires.
        self._relay_sample()
        self._relay_calculations()
        self._relay_engine()
        self._relay_project_folder()

    def _relay_sample(self) -> None:
        self._project.setSampleName(f'{self._sample.formula}, {self._sample.atomCount} atoms')

    def _relay_calculations(self) -> None:
        self._project.setCalculations(self._calculations.selectedNames)

    def _relay_engine(self) -> None:
        self._project.setEngine(self._method.engineName)
        self._job.set_executable(self._method.enginePath if self._method.engineFound else '')

    def _relay_project_folder(self) -> None:
        # Runs go into the project folder once it exists, into the scratch folder before.
        self._job.set_root_folder(self._project.location if self._project.created else '')

    def _relay_job_state(self) -> None:
        # JobState and ProjectStatus share their values, except the idle state of a new job.
        if self._job.state != 'idle':
            self._project.setStatus(self._job.state)
