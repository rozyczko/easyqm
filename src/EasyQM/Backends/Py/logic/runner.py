# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Qt-free local job runner (GENERAL_DESIGN.md, section 4, rule 5).

One engine process at a time, started in its run folder, with its standard output and error
written straight to the output file. A workflow may be several programs (pw.x, then ph.x);
each starts when the one before has ended with exit code 0, and all write to the same file.
The GUI follows the job by reading what was appended to that file, so the same code shows a
running job and a finished one, and nothing depends on the engine flushing a pipe.
"""

import codecs
import os
import signal
import subprocess
import sys
from enum import Enum
from pathlib import Path
from typing import Optional

# Keep console engines from opening a window when the app has none; their own child
# processes share the hidden console.
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)

RUNS_FOLDER_NAME = 'runs'


class JobState(Enum):
    IDLE = 'idle'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'
    STOPPED = 'stopped'

    @property
    def label(self) -> str:
        return 'Not run' if self is JobState.IDLE else self.value.capitalize()


def new_run_folder(root: Path) -> Path:
    """Create and return the next numbered run folder, ``root/runs/001`` and so on."""
    runs = Path(root) / RUNS_FOLDER_NAME
    runs.mkdir(parents=True, exist_ok=True)
    numbers = [int(path.name) for path in runs.iterdir() if path.is_dir() and path.name.isdigit()]
    folder = runs / f'{max(numbers, default=0) + 1:03d}'
    folder.mkdir()
    return folder


class JobRunner:
    def __init__(self):
        self._process: Optional[subprocess.Popen] = None
        self._waiting: list[list[str]] = []  # commands still to run after the current one
        self._launch_failed = False
        self._folder: Optional[Path] = None
        self._output_file = None
        self._reader = None
        self._decoder = None

    @property
    def running(self) -> bool:
        return self._process is not None and (self._process.poll() is None or self._next_waits())

    def start(self, commands: list[list[str]], folder: Path, output: Path) -> None:
        """Run `commands` one after the other in `folder`, writing their output to `output`.

        :raises RuntimeError: if a job is already running.
        :raises OSError: if the first program cannot be started.
        """
        if self.running:
            raise RuntimeError('A job is already running.')
        self._close()
        self._folder, self._waiting, self._launch_failed = folder, list(commands[1:]), False
        self._output_file = open(output, 'wb')
        try:
            self._launch(commands[0])
        except OSError:
            self._close()
            raise
        self._reader = open(output, 'rb')
        self._decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')

    def poll(self) -> Optional[int]:
        """The exit code once the workflow has ended, None while it runs or before a start.

        Starts the next program when the current one has ended well. A program that cannot be
        started ends the workflow with exit code -1, its error written to the output.
        """
        if self._process is None:
            return None
        if self._launch_failed:
            return -1
        if self._next_waits():
            command = self._waiting.pop(0)
            try:
                self._launch(command)
            except OSError as error:
                self._waiting, self._launch_failed = [], True
                self._output_file.write(f'\nCould not start {command[0]}: {error}\n'.encode())
                self._output_file.flush()
                return -1
            return None
        return self._process.poll()

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

    def _next_waits(self) -> bool:
        return bool(self._waiting) and self._process.poll() == 0

    def _launch(self, command: list[str]) -> None:
        self._process = subprocess.Popen(
            command,
            cwd=self._folder,
            stdin=subprocess.DEVNULL,
            stdout=self._output_file,
            stderr=subprocess.STDOUT,
            creationflags=NO_WINDOW,
            # Own process group on POSIX, so `stop` reaches the engine's children too.
            start_new_session=sys.platform != 'win32',
        )

    def _close(self) -> None:
        for file in (self._reader, self._output_file):
            if file is not None:
                file.close()
        self._reader = self._output_file = None
