# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""The local runner, with Python standing in for the engine."""

import os
import sys
import time

import pytest

from Backends.Py.logic.runner import LAUNCH_FAILED
from Backends.Py.logic.runner import STEP_FAILED
from Backends.Py.logic.runner import JobRunner
from Backends.Py.logic.runner import JobState
from Backends.Py.logic.runner import Step
from Backends.Py.logic.runner import new_run_folder
from Backends.Py.logic.runner import process_environment


def _python(code: str) -> Step:
    return Step([sys.executable, '-X', 'utf8', '-c', code])


def _logging(seed: str, lines: list[str], title: str = 'Ground state') -> Step:
    """A program of these lines of Python, which writes its log to <seed>.castep as CASTEP does."""
    script = '\n'.join(['import time', 'NL = chr(10)', *lines])
    return Step([sys.executable, '-X', 'utf8', '-c', script], title, f'{seed}.castep', f'{seed}.*.err')


def _log(seed: str, text: str) -> str:
    """A line of Python that writes `text` and a newline to the log of `seed`."""
    return f'open({seed + ".castep"!r}, "w").write({text!r} + NL)'


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

    runner.start([_python(script)], tmp_path, output)
    assert _wait(runner) == 3
    text = runner.read_new() + runner.finish()

    assert text.splitlines() == ['first', 'ä second']
    assert output.read_text(encoding='utf-8').splitlines() == ['first', 'ä second']
    assert runner.read_new() == ''
    assert not runner.running


def test_programs_run_one_after_the_other_into_one_file(tmp_path):
    runner = JobRunner()
    output = tmp_path / 'job.out'
    first, second = (['import time; time.sleep(0.3); print("pw")'], ['print("ph")'])

    runner.start([_python(*first), _python(*second)], tmp_path, output)
    assert runner.running
    assert _wait(runner) == 0 and not runner.running
    runner.finish()
    assert output.read_text(encoding='utf-8').splitlines() == ['pw', 'ph']


def test_a_failed_or_missing_program_ends_the_workflow(tmp_path):
    runner = JobRunner()
    output = tmp_path / 'job.out'
    runner.start([_python('raise SystemExit(2)'), _python('print("ph")')], tmp_path, output)
    assert _wait(runner) == 2
    runner.finish()
    assert 'ph' not in output.read_text(encoding='utf-8')

    runner.start([_python('pass'), Step([str(tmp_path / 'missing.exe')])], tmp_path, output)
    assert _wait(runner) == LAUNCH_FAILED
    runner.finish()
    assert 'Could not start' in output.read_text(encoding='utf-8')


def test_stop_ends_the_process(tmp_path):
    runner = JobRunner()
    runner.start([_python('import time; time.sleep(60)')], tmp_path, tmp_path / 'job.out')
    assert runner.running
    with pytest.raises(RuntimeError):
        runner.start([_python('pass')], tmp_path, tmp_path / 'other.out')

    started = time.monotonic()
    runner.stop()

    assert not runner.running and runner.poll() is not None
    assert time.monotonic() - started < 10
    runner.finish()


def test_a_step_with_its_own_log_is_followed_and_copied_once(tmp_path):
    runner = JobRunner()
    output = tmp_path / 'job.out'
    # The log appears only after a while, grows while the runner polls, and gets its last line
    # just before the program exits; the program also prints, and leaves an error file.
    lines = [
        'time.sleep(0.3)',
        'log = open("job.castep", "w")',
        'for line in ("one", "two", "Total time = 1 s"):',
        '    log.write(line + NL); log.flush(); time.sleep(0.2)',
        'open("job.0001.err", "w").write("Error in phonon_LO_analysis" + NL)',
        'print("from stdout")',
    ]
    runner.start([_logging('job', lines)], tmp_path, output, check=lambda text: 'Total time' in text)
    seen = ''
    while (result := runner.poll()) is None:
        seen += runner.read_new()
        time.sleep(0.05)
    seen += runner.finish()

    assert result == 0
    assert seen.split() == ['==>', 'job:', 'Ground', 'state', 'one', 'two', 'Total', 'time', '=', '1', 's',
                            'from', 'stdout', 'Error', 'in', 'phonon_LO_analysis']
    assert output.read_bytes().decode('utf-8') == seen
    assert runner.poll() == 0 and runner.finish() == ''  # nothing is appended twice


def test_a_step_that_exits_with_zero_but_failed_stops_the_workflow(tmp_path):
    runner = JobRunner()
    output = tmp_path / 'job.out'
    good = _logging('job', [_log('job', 'Total time = 1 s')])
    failed = _logging('job-dos', [_log('job-dos', 'SCF failed')], 'Density of states')
    later = _logging('job-bands', [_log('job-bands', 'Total time = 1 s')], 'Band structure')
    texts = []

    def check(text):
        texts.append(text)
        return 'Total time' in text

    runner.start([good, failed, later], tmp_path, output, check=check)
    assert _wait(runner) == STEP_FAILED and not runner.running
    runner.finish()

    # Each step was judged on its own text, so the first step's footer does not count for the second.
    assert [text.split() for text in texts] == [['Total', 'time', '=', '1', 's'], ['SCF', 'failed']]
    assert '==> job-bands' not in output.read_text(encoding='utf-8')


def test_the_environment_reaches_the_program(tmp_path, monkeypatch):
    monkeypatch.setenv('PATH', 'inherited')
    environment = process_environment({'PATH': 'first', 'OMP_NUM_THREADS': '1'})
    assert environment['PATH'] == f'first{os.pathsep}inherited' and environment['OMP_NUM_THREADS'] == '1'

    monkeypatch.undo()
    runner = JobRunner()
    output = tmp_path / 'job.out'
    runner.start([_python('import os; print(os.environ["OMP_NUM_THREADS"])')], tmp_path, output, {'OMP_NUM_THREADS': '3'})
    assert _wait(runner) == 0
    runner.finish()
    assert output.read_text(encoding='utf-8').strip() == '3'


def test_state_labels():
    assert JobState.IDLE.label == 'Not run'
    assert JobState.COMPLETED.label == 'Completed'
