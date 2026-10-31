# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Job backend part: runs the current workflow locally and streams the engine output to QML.

The Run card of the Method page drives it; the Summary page will read the same output.
Everything engine-specific comes from the adapter, everything about the process from the
Qt-free `logic.runner.JobRunner`. This class only adds a timer that follows the output file.
"""

import tempfile
import time
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Property
from PySide6.QtCore import QCoreApplication
from PySide6.QtCore import QObject
from PySide6.QtCore import QTimer
from PySide6.QtCore import Signal
from PySide6.QtCore import Slot

from .logic.engines.base import EngineAdapter
from .logic.runner import JobRunner
from .logic.runner import JobState
from .logic.runner import new_run_folder

POLL_INTERVAL_MS = 500
# Where runs go while no project has been created (see the Project page hint).
SCRATCH_ROOT = Path(tempfile.gettempdir()) / 'EasyQM'


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
        self._started = 0.0
        self._stopping = False

        self._timer = QTimer(self)
        self._timer.setInterval(POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._poll)
        application = QCoreApplication.instance()
        if application is not None:
            # A job must not outlive the window that shows it.
            application.aboutToQuit.connect(self.stop)

    # Relay targets (plain Python)

    def set_executable(self, path: str) -> None:
        self._executable = path

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
        try:
            if not self._executable:
                raise RuntimeError(f'{self._adapter.name} was not found. Configure its path first.')
            text = self._adapter.input_text(self._sample, self._calculations, self._method, self._settings)
            folder = new_run_folder(Path(self._root) if self._root else SCRATCH_ROOT)
            input_path = folder / self._adapter.input_file_name
            input_path.write_text(text, encoding='utf-8')
            output_path = folder / self._adapter.output_file_name
            self._set_files(folder, input_path, output_path)
            self._clear_output()
            self._runner.start(self._adapter.command(self._executable, input_path), folder, output_path)
        except (RuntimeError, ValueError, OSError) as error:
            self._set_state(JobState.FAILED, str(error))
            return
        self._started = time.monotonic()
        self._stopping = False
        self._set_state(JobState.RUNNING, f'Running {self._adapter.name}, serial')
        self._timer.start()

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
        elif code == 0 and self._adapter.succeeded(self.output):
            self._set_state(JobState.COMPLETED, f'Completed in {elapsed}')
        else:
            message = f'{self._adapter.name} ended with exit code {code} after {elapsed}; see the output'
            self._set_state(JobState.FAILED, message)

    def _append(self, text: str) -> None:
        if text:
            self._chunks.append(text)
            self.outputAppended.emit(text)

    def _clear_output(self) -> None:
        self._chunks = []
        self.outputChanged.emit()

    def _set_files(self, folder: Path, input_path: Path, output_path: Path) -> None:
        self._folder, self._input_path, self._output_path = str(folder), str(input_path), str(output_path)
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
