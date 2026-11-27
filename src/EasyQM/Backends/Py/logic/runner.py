# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Qt-free local job runner (GENERAL_DESIGN.md, section 4, rule 5).

One engine process at a time, started in its run folder. A workflow is a list of steps
(pw.x, then ph.x); each starts when the one before has ended well, and all write to one
output file. The GUI follows the job by reading what was appended to that file, so the same
code shows a running job and a finished one, and nothing depends on the engine flushing a
pipe.

A step either writes its log to standard output, which then goes straight into the output
file, or to a log file of its own (CASTEP's ``<seed>.castep``). For the second kind the
runner is the only writer of the output file: it writes a header line, copies what the
program adds to its log on every poll, and when the program has ended appends the rest,
the program's own standard output and error (captured in ``<seed>.stdout``) and any error
files. A step has ended well when its exit code is 0 and the `check` given to `start`
accepts the step's text; CASTEP exits with 0 after a failure too.
"""

import codecs
import os
import signal
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable
from typing import Optional

# Keep console engines from opening a window when the app has none; their own child
# processes share the hidden console.
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)

RUNS_FOLDER_NAME = 'runs'
LAUNCH_FAILED = -1  # a program could not be started
STEP_FAILED = -2  # a program ended with exit code 0, but its output shows it failed


class JobState(Enum):
    IDLE = 'idle'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'
    STOPPED = 'stopped'

    @property
    def label(self) -> str:
        return 'Not run' if self is JobState.IDLE else self.value.capitalize()


@dataclass(frozen=True)
class Step:
    """One program of a workflow."""

    command: list[str]
    title: str = ''  # 'Band structure'; with a log, written in the header line before it
    log: str = ''  # file the program writes its log to, in the run folder; '' means standard output
    errors: str = ''  # glob of files appended after the step, e.g. 'job-bands.*.err'

    @property
    def header(self) -> str:
        """'==> job-bands: Band structure', the line before a step with a log of its own."""
        return f'==> {Path(self.log).stem}: {self.title}'


def new_run_folder(root: Path) -> Path:
    """Create and return the next numbered run folder, ``root/runs/001`` and so on."""
    runs = Path(root) / RUNS_FOLDER_NAME
    runs.mkdir(parents=True, exist_ok=True)
    numbers = [int(path.name) for path in runs.iterdir() if path.is_dir() and path.name.isdigit()]
    folder = runs / f'{max(numbers, default=0) + 1:03d}'
    folder.mkdir()
    return folder


def process_environment(extra: dict[str, str]) -> dict[str, str]:
    """The application's environment with `extra` on top; a PATH in `extra` goes in front."""
    environment = dict(os.environ)
    for key, value in extra.items():
        if key.upper() == 'PATH' and environment.get(key):
            value = value + os.pathsep + environment[key]
        environment[key] = value
    return environment


class JobRunner:
    def __init__(self):
        self._process: Optional[subprocess.Popen] = None
        self._step: Optional[Step] = None
        self._waiting: list[Step] = []  # steps still to run after the current one
        self._result: Optional[int] = None  # the exit code of the workflow, once it has ended
        self._folder: Optional[Path] = None
        self._output_path: Optional[Path] = None
        self._output_file = None
        self._capture = None  # standard output of a step with its own log
        self._log_offset = 0
        self._step_start = 0  # where the current step's text starts in the output file
        self._environment: Optional[dict] = None
        self._check: Optional[Callable[[str], bool]] = None
        self._reader = None
        self._decoder = None

    @property
    def running(self) -> bool:
        if self._process is None or self._result is not None:
            return False
        return self._process.poll() is None or bool(self._waiting)

    def start(
        self,
        steps: list[Step],
        folder: Path,
        output: Path,
        environment: Optional[dict[str, str]] = None,
        check: Optional[Callable[[str], bool]] = None,
    ) -> None:
        """Run `steps` one after the other in `folder`, writing their output to `output`.

        `environment` is added to the application's (`process_environment`); `check` gets the
        text of a step that ended with exit code 0 and says whether it ended well.

        :raises RuntimeError: if a job is already running.
        :raises OSError: if the first program cannot be started.
        """
        if self.running:
            raise RuntimeError('A job is already running.')
        self._close()
        self._folder, self._output_path = Path(folder), Path(output)
        self._waiting, self._result = list(steps[1:]), None
        self._environment = process_environment(environment) if environment else None
        self._check = check
        self._output_file = open(output, 'wb')
        try:
            self._launch(steps[0])
        except OSError:
            self._close()
            raise
        self._reader = open(output, 'rb')
        self._decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')

    def poll(self) -> Optional[int]:
        """The exit code once the workflow has ended, None while it runs or before a start.

        Copies the current step's log, and starts the next step when the current one has
        ended well. A program that cannot be started ends the workflow with `LAUNCH_FAILED`,
        its error written to the output; one whose output shows a failure with `STEP_FAILED`.
        """
        if self._process is None or self._result is not None:
            return self._result
        self._copy_log()
        code = self._process.poll()
        if code is None:
            return None
        self._end_step()
        if code == 0 and self._check is not None and not self._check(self._step_text()):
            code = STEP_FAILED
        if code != 0 or not self._waiting:
            self._result = code
            return code
        step = self._waiting.pop(0)
        try:
            self._launch(step)
        except OSError as error:
            self._waiting = []
            self._write(f'\nCould not start {step.command[0]}: {error}\n'.encode())
            self._result = LAUNCH_FAILED
            return self._result
        return None

    def read_new(self) -> str:
        """Text appended to the output file since the last call."""
        if self._reader is None:
            return ''
        return self._decoder.decode(self._reader.read())

    def stop(self) -> None:
        """End the engine and every process it started. Returns once it has ended."""
        self._waiting = []
        if self._process is None or self._process.poll() is not None:
            return
        if sys.platform == 'win32':
            # Killing orca.exe alone would leave its orca_scf.exe etc. running.
            subprocess.run(
                ['taskkill', '/F', '/T', '/PID', str(self._process.pid)], capture_output=True, creationflags=NO_WINDOW
            )
        else:
            os.killpg(self._process.pid, signal.SIGTERM)
        self._process.wait()

    def finish(self) -> str:
        """Release the files of an ended job and return the last unread output."""
        text = '' if self._reader is None else self._decoder.decode(self._reader.read(), final=True)
        self._close()
        return text

    def _launch(self, step: Step) -> None:
        self._step, self._log_offset = step, 0
        if step.log:
            self._write(f'{step.header}\n'.encode())
        # The file's size, not tell(): a program writing to standard output shares the file.
        self._step_start = self._output_path.stat().st_size
        if step.log:
            self._capture = open(self._folder / f'{Path(step.log).stem}.stdout', 'wb')
        self._process = subprocess.Popen(
            step.command,
            cwd=self._folder,
            env=self._environment,
            stdin=subprocess.DEVNULL,
            stdout=self._capture or self._output_file,
            stderr=subprocess.STDOUT,
            creationflags=NO_WINDOW,
            # Own process group on POSIX, so `stop` reaches the engine's children too.
            start_new_session=sys.platform != 'win32',
        )

    def _copy_log(self) -> None:
        """Append what the step's program added to its log since the last copy."""
        if self._step is None or not self._step.log:
            return
        try:
            with open(self._folder / self._step.log, 'rb') as log:
                log.seek(self._log_offset)
                text = log.read()
        except FileNotFoundError:
            return  # not written yet
        self._log_offset += len(text)
        self._write(text)

    def _end_step(self) -> None:
        """After the program ended: the rest of its log, its captured output, its error files."""
        if not self._step.log:
            return
        self._copy_log()
        self._capture.close()
        self._capture = None
        files = [self._folder / f'{Path(self._step.log).stem}.stdout']
        if self._step.errors:
            files += sorted(self._folder.glob(self._step.errors))
        for path in files:
            text = path.read_bytes()
            if text:
                self._write(b'\n' + text)

    def _step_text(self) -> str:
        self._output_file.flush()
        with open(self._output_path, 'rb') as file:
            file.seek(self._step_start)
            return file.read().decode('utf-8', errors='replace')

    def _write(self, data: bytes) -> None:
        self._output_file.write(data)
        self._output_file.flush()

    def _close(self) -> None:
        for file in (self._reader, self._output_file, self._capture):
            if file is not None:
                file.close()
        self._reader = self._output_file = self._capture = None
