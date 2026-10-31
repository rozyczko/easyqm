# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""The local runner, with Python standing in for the engine."""

import sys
import time

import pytest

from Backends.Py.logic.runner import JobRunner
from Backends.Py.logic.runner import JobState
from Backends.Py.logic.runner import new_run_folder


def _wait(runner: JobRunner, seconds: float = 20) -> int:
    end = time.monotonic() + seconds
    while runner.poll() is None:
        assert time.monotonic() < end, 'process did not end'
        time.sleep(0.05)
    return runner.poll()


def test_run_folders_are_numbered(tmp_path):
    assert new_run_folder(tmp_path) == tmp_path / 'runs' / '001'
    (tmp_path / 'runs' / 'notes').mkdir()
    assert new_run_folder(tmp_path) == tmp_path / 'runs' / '002'
    assert sorted(path.name for path in (tmp_path / 'runs').iterdir()) == ['001', '002', 'notes']


def test_output_goes_to_the_file_and_is_read_incrementally(tmp_path):
    runner = JobRunner()
    output = tmp_path / 'job.out'
    script = 'import sys; print("first"); sys.stdout.flush(); print("ä second", file=sys.stderr); sys.exit(3)'

    runner.start([sys.executable, '-X', 'utf8', '-c', script], tmp_path, output)
    assert _wait(runner) == 3
    text = runner.read_new() + runner.finish()

    assert text.splitlines() == ['first', 'ä second']
    assert output.read_text(encoding='utf-8').splitlines() == ['first', 'ä second']
    assert runner.read_new() == ''
    assert not runner.running


def test_stop_ends_the_process(tmp_path):
    runner = JobRunner()
    runner.start([sys.executable, '-c', 'import time; time.sleep(60)'], tmp_path, tmp_path / 'job.out')
    assert runner.running
    with pytest.raises(RuntimeError):
        runner.start([sys.executable, '-c', 'pass'], tmp_path, tmp_path / 'other.out')

    started = time.monotonic()
    runner.stop()

    assert not runner.running and runner.poll() is not None
    assert time.monotonic() - started < 10
    runner.finish()


def test_state_labels():
    assert JobState.IDLE.label == 'Not run'
    assert JobState.COMPLETED.label == 'Completed'
