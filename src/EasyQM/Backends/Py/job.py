# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Job backend part: runs the current workflow locally and streams the engine output to QML.

The Run card of the Method page drives it; the Summary page will read the same output.
Everything engine-specific comes from the adapter, everything about the process from the
Qt-free `logic.runner.JobRunner`. This class only adds a timer that follows the output file.
"""

import hashlib
import json
import logging
import tempfile
import time
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Property
from PySide6.QtCore import QCoreApplication
from PySide6.QtCore import QObject
from PySide6.QtCore import QTimer
from PySide6.QtCore import Signal
from PySide6.QtCore import Slot

from .logic.calculations import CalculationType
from .logic.calculations import info
from .logic.engines.base import EngineAdapter
from .logic.method import describe
from .logic.method import reference_problem
from .logic.runner import JobRunner
from .logic.runner import JobState
from .logic.runner import new_run_folder

POLL_INTERVAL_MS = 500
# Output kept from the previous read, so that a step marker split between two reads is found.
_MARKER_OVERLAP = 200
# Where runs go while no project has been created (see the Project page hint).
SCRATCH_ROOT = Path(tempfile.gettempdir()) / 'EasyQM'

_log = logging.getLogger(__name__)


def configuration(sample, calculations, method, settings) -> dict:
    """Short hashes of what a job is computed from, to tell whether results belong to the
    current setup: {'sample', 'calculations', 'method'}."""
    sample_state = {
        'atoms': [(a.element, round(a.x, 4), round(a.y, 4), round(a.z, 4), a.fixed) for a in sample.atoms],
        'cell': sample.cell.vectors if sample.cell else None,
        'state': (sample.charge, sample.multiplicity),
    }
    calculations_state = {
        'steps': [step.value for step in calculations.workflow()],
        'options': [asdict(getattr(calculations, calculation.value)) for calculation in CalculationType],
    }
    method_state = {'method': asdict(method), 'settings': asdict(settings)}
    return {name: _digest(state) for name, state in
            (('sample', sample_state), ('calculations', calculations_state), ('method', method_state))}


def _digest(state) -> str:
    return hashlib.sha256(json.dumps(state, sort_keys=True, default=str).encode()).hexdigest()[:12]


class Job(QObject):
    stateChanged = Signal()
    filesChanged = Signal()
    # `output` changed as a whole: cleared when a job starts, complete when it ends.
    outputChanged = Signal()
    # Text the engine appended to the output file since the last signal.
    outputAppended = Signal(str)

    def __init__(
        self,
        adapter: EngineAdapter,
        sample,
        calculations,
        method,
        settings,
        runner: Optional[JobRunner] = None,
        parent=None,
    ):
        super().__init__(parent)
        # Logic objects of the other parts; read when a job starts.
        self._adapter = adapter
        self._job_adapter = adapter  # the engine of the job that runs or ran last
        self._sample = sample
        self._calculations = calculations
        self._method = method
        self._settings = settings
        self._runner = runner if runner is not None else JobRunner()

        # Set by PyBackend relays.
        self._executable = ''
        self._root = ''

        self._state = JobState.IDLE
        self._message = ''
        self._folder = ''
        self._input_path = ''
        self._output_path = ''
        self._chunks: list[str] = []
        self._steps = []  # the workflow of the job, and the index of the step it is in
        self._step = 0
        self._step_failed = False  # the output shows the step failed, so it stays the current one
        self._started = 0.0
        self._stopping = False
        self._record: Optional[dict] = None  # what the job that runs or ran last was computed from

        self._timer = QTimer(self)
        self._timer.setInterval(POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._poll)
        application = QCoreApplication.instance()
        if application is not None:
            # A job must not outlive the window that shows it.
            application.aboutToQuit.connect(self.stop)

    # Relay targets (plain Python)

    def set_engine(self, adapter: EngineAdapter, method) -> None:
        """The active engine and its method; a running job keeps its own."""
        self._adapter, self._method = adapter, method

    def set_executable(self, path: str) -> None:
        self._executable = path

    @property
    def adapter(self) -> EngineAdapter:
        """The engine of the job that runs or ran last, which can read its output."""
        return self._job_adapter

    def set_root_folder(self, path: str) -> None:
        """Folder whose `runs/` receives new jobs; empty for the scratch folder."""
        self._root = path

    # State

    @Property(str, notify=stateChanged)
    def state(self) -> str:
        return self._state.value

    @Property(str, notify=stateChanged)
    def stateLabel(self) -> str:
        return self._state.label

    @Property(bool, notify=stateChanged)
    def running(self) -> bool:
        return self._state is JobState.RUNNING

    @Property(str, notify=stateChanged)
    def message(self) -> str:
        return self._message

    @Property('QVariantMap', notify=stateChanged)
    def stepStates(self) -> dict:
        """The state of each step of the job by calculation type: steps before the current one
        are completed, the current one has the job's state, later ones have not run."""
        states = {}
        for index, step in enumerate(self._steps):
            if index < self._step or self._state is JobState.COMPLETED:
                state = JobState.COMPLETED
            else:
                state = self._state if index == self._step else JobState.IDLE
            states[step.value] = state.value
        return states

    # Files

    @Property(str, notify=filesChanged)
    def folder(self) -> str:
        return self._folder

    @Property(str, notify=filesChanged)
    def inputPath(self) -> str:
        return self._input_path

    @Property(str, notify=filesChanged)
    def outputPath(self) -> str:
        return self._output_path

    # Output

    @Property(str, notify=outputChanged)
    def output(self) -> str:
        return ''.join(self._chunks)

    # Control

    @Slot()
    def run(self) -> None:
        if self.running:
            return
        self._steps, self._step, self._step_failed = [], 0, False
        try:
            files, commands = self._prepare()
            folder = new_run_folder(self.runs_root)
            for name, text in files.items():
                (folder / name).write_text(text, encoding='utf-8')
            input_path = folder / next(iter(files))
            output_path = folder / self._adapter.output_file_name
            self._set_files(folder, input_path, output_path)
            self._clear_output()
            self._job_adapter = self._adapter
            self._runner.start(commands, folder, output_path)
            self._steps = self._calculations.workflow()
        except Exception as error:
            self._set_state(JobState.FAILED, _problem(error))
            return
        self._record = {
            'run_id': folder.name,
            'folder': str(folder),
            'engine': self._adapter.name,
            'method': describe(self._method, self._adapter.capabilities()),
            'calculations': [info(step).name for step in self._steps],
            'configuration': configuration(self._sample, self._calculations, self._method, self._settings),
            'geometry_applied': False,
        }
        self._started = time.monotonic()
        self._stopping = False
        self._set_state(JobState.RUNNING, f'Running {self._adapter.name}, serial')
        self._timer.start()

    def preflight(self) -> str:
        """Why a job could not start now (input generation, executables), or ''. Starts nothing."""
        try:
            self._prepare()
        except Exception as error:
            return _problem(error)
        return ''

    def _prepare(self) -> tuple[dict, list]:
        sample = self._sample
        problem = (sample.electronic_state_problem(sample.charge, sample.multiplicity)
                   or reference_problem(self._method.reference, sample.multiplicity))
        if problem:
            raise ValueError(f'{problem} Change it on the Sample or Method page.')
        if not self._executable:
            raise RuntimeError(f'{self._adapter.name} was not found. Configure its path first.')
        files = self._adapter.input_files(self._sample, self._calculations, self._method, self._settings)
        return files, self._adapter.commands(self._executable, list(files))

    # Provenance and output, for the assistant

    @property
    def runs_root(self) -> Path:
        """Where the next run folder goes: the project folder, or the scratch folder without a project."""
        return Path(self._root) if self._root else SCRATCH_ROOT

    @property
    def record(self) -> Optional[dict]:
        """{run_id, folder, engine, method, calculations, configuration, geometry_applied} of the
        job that runs or ran last; None before any."""
        return dict(self._record) if self._record else None

    def mark_geometry_applied(self, sample_configuration: str) -> None:
        """The sample moved to the optimised geometry: the results describe it again."""
        if self._record:
            self._record['configuration'] = {**self._record['configuration'], 'sample': sample_configuration}
            self._record['geometry_applied'] = True

    def tail(self, max_chars: int) -> str:
        """The last `max_chars` characters of the output, without joining all of it."""
        parts, size = [], 0
        for chunk in reversed(self._chunks):
            parts.append(chunk[-(max_chars - size):])
            size += len(parts[-1])
            if size >= max_chars:
                break
        return ''.join(reversed(parts))

    def reset(self) -> None:
        """No job run yet, as at start-up (for PyBackend.reset); refused while one runs. The
        run folders stay on disk."""
        if self.running:
            return
        self._steps, self._step, self._step_failed = [], 0, False
        self._job_adapter = self._adapter
        self._record = None
        self._set_files_paths('', '', '')
        self._clear_output()
        self._set_state(JobState.IDLE, '')

    @Slot()
    def stop(self) -> None:
        if not self.running:
            return
        self._stopping = True
        self._runner.stop()
        self._finish(self._runner.poll())

    # Following the output file

    def _poll(self) -> None:
        self._append(self._runner.read_new())
        code = self._runner.poll()
        if code is not None:
            self._finish(code)

    def _finish(self, code: int) -> None:
        self._timer.stop()
        self._append(self._runner.finish())
        self.outputChanged.emit()
        elapsed = _duration(time.monotonic() - self._started)
        if self._stopping:
            self._set_state(JobState.STOPPED, f'Stopped after {elapsed}')
        elif code == 0 and self._job_adapter.succeeded(self.output):
            self._set_state(JobState.COMPLETED, f'Completed in {elapsed}')
        else:
            message = f'{self._job_adapter.name} ended with exit code {code} after {elapsed}; see the output'
            self._set_state(JobState.FAILED, message)

    def _append(self, text: str) -> None:
        if text:
            recent = (self._chunks[-1][-_MARKER_OVERLAP:] if self._chunks else '') + text
            self._chunks.append(text)
            self.outputAppended.emit(text)
            if self._step_failed:
                return
            adapter = self._job_adapter
            step = max(self._step, adapter.current_step(recent, self._steps))
            self._step_failed = adapter.failure_marker is not None and adapter.failure_marker.search(recent) is not None
            if step != self._step:
                self._step = step
                self.stateChanged.emit()

    def _clear_output(self) -> None:
        self._chunks = []
        self.outputChanged.emit()

    def _set_files(self, folder: Path, input_path: Path, output_path: Path) -> None:
        self._set_files_paths(str(folder), str(input_path), str(output_path))

    def _set_files_paths(self, folder: str, input_path: str, output_path: str) -> None:
        self._folder, self._input_path, self._output_path = folder, input_path, output_path
        self.filesChanged.emit()

    def _set_state(self, state: JobState, message: str) -> None:
        self._state, self._message = state, message
        self.stateChanged.emit()


def _duration(seconds: float) -> str:
    seconds = round(seconds)
    if seconds < 60:
        return f'{seconds} s'
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f'{minutes} min {seconds:02d} s'
    hours, minutes = divmod(minutes, 60)
    return f'{hours} h {minutes:02d} min'


def _problem(error: Exception) -> str:
    """The message for a job that could not start; an unexpected error is logged in full."""
    if isinstance(error, (RuntimeError, ValueError, OSError)):
        return str(error)
    _log.exception('Unexpected error while preparing a job')
    return f'Unexpected {type(error).__name__} while preparing the job: {error}'
