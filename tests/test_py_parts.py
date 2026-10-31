# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Proxies of the Sample, Calculations and Method parts, and their relays in PyBackend."""

import json
import sys
import time

import pytest
from PySide6.QtCore import QSettings

from Backends.Py.calculations import Calculations
from Backends.Py.job import Job
from Backends.Py.logic.engines.base import Capabilities
from Backends.Py.logic.engines.base import EngineAdapter
from Backends.Py.logic.engines.base import EngineInfo
from Backends.Py.logic.engines.orca import CAPABILITIES
from Backends.Py.logic.method import RunSettings
from Backends.Py.method import Method
from Backends.Py.py_backend import PyBackend
from Backends.Py.sample import Sample


def _emissions(signal) -> list:
    calls = []
    signal.connect(lambda *args: calls.append(args))
    return calls


class FakeAdapter(EngineAdapter):
    name = 'ORCA'

    def __init__(self):
        self.info = EngineInfo(found=False)

    def detect(self) -> EngineInfo:
        return self.info

    def capabilities(self) -> Capabilities:
        return CAPABILITIES


class ScriptAdapter(FakeAdapter):
    """Runs the input file as a Python script in place of an engine."""

    def input_text(self, sample, calculations, method, settings) -> str:
        if not calculations.workflow():
            raise ValueError('No calculation is selected.')
        return self.script

    def command(self, executable, input_path):
        return [sys.executable, input_path.name]

    def succeeded(self, output: str) -> bool:
        return 'DONE' in output


def _settings(tmp_path) -> QSettings:
    return QSettings(str(tmp_path / 'settings.ini'), QSettings.Format.IniFormat)


# Sample


def test_sample_starts_with_benzene(qcore_application):
    sample = Sample()
    assert sample.formula == 'C6H6'
    assert sample.summary == 'benzene.xyz · C6H6 · 12 atoms'
    assert len(sample.atoms) == 12
    assert sample.atoms[1] == {'label': 'C2', 'element': 'C', 'x': 1.2051, 'y': 0.6958, 'z': 0.0, 'fixed': False}
    assert len(sample.bonds) == 12 and sample.bonds[0] == [0, 1]


def test_sample_fix_flag(qcore_application):
    sample = Sample()
    changes = _emissions(sample.atomsChanged)

    sample.setAtomFixed(3, True)
    sample.setAtomFixed(3, True)

    assert len(changes) == 1
    assert sample.atoms[3]['fixed'] and sample.fixedCount == 1


# Calculations


def test_calculations_rows_and_workflow(qcore_application):
    calculations = Calculations()
    changes = _emissions(calculations.selectionChanged)
    external = _emissions(calculations.externalSelectionChanged)

    assert [row['name'] for row in calculations.rows] == [
        'Single point energy',
        'Geometry optimisation',
        'Vibrational frequencies',
    ]
    assert calculations.selectedCount == 0 and calculations.workflow == []

    calculations.setSelected('single_point', True)
    calculations.setSelected('single_point', True)
    calculations.setSelected('geometry_optimisation', True)

    assert len(changes) == 2 and len(external) == 2
    assert calculations.selectedCount == 2
    assert calculations.isSelected('single_point')
    assert calculations.rows[0]['selected'] and not calculations.rows[2]['selected']
    assert [step['label'] for step in calculations.workflow] == [
        'Geometry optimisation',
        'Single point energy (at optimised geometry)',
    ]
    assert calculations.workflow[1]['step'] == 2


def test_calculations_options(qcore_application):
    calculations = Calculations()
    opt = _emissions(calculations.optimisationChanged)
    freq = _emissions(calculations.frequenciesChanged)

    calculations.setOptMaxSteps(100)
    calculations.setOptMaxSteps(50)
    calculations.setOptConvergence('loose')
    calculations.setFreqTemperature(300.0)
    calculations.setFreqRaman(True)
    calculations.setSinglePointGeometry('input')

    assert len(opt) == 2 and len(freq) == 2
    assert calculations.optMaxSteps == 50 and calculations.optConvergence == 'loose'
    assert calculations.freqTemperature == 300.0 and calculations.freqRaman
    assert calculations.singlePointGeometry == 'input'
    assert calculations.optConvergenceChoices[2] == {'value': 'tight', 'label': 'Tight'}


# Method


def test_method_engine_detection(qcore_application):
    adapter = FakeAdapter()
    method = Method(adapter=adapter)
    changes = _emissions(method.engineChanged)

    assert method.engineName == 'ORCA'
    assert not method.engineFound
    assert method.engineCardText.startswith('Not detected')

    adapter.info = EngineInfo(found=True, version='6.0.1', path='/opt/orca/6.0.1/orca')
    method.redetect()

    assert len(changes) == 1
    assert method.engineFound and method.engineVersion == '6.0.1'
    assert method.engineCardText == 'Version 6.0.1'


def test_method_engine_path_is_remembered(qcore_application, tmp_path):
    adapter = FakeAdapter()
    method = Method(adapter=adapter, settings=_settings(tmp_path))
    changes = _emissions(method.engineChanged)

    method.setEnginePath('file:///F:/ORCA/orca.exe')

    assert adapter.executable == 'F:/ORCA/orca.exe'
    assert len(changes) == 1
    assert Method(adapter=FakeAdapter(), settings=_settings(tmp_path)).adapter.executable == 'F:/ORCA/orca.exe'

    method.setEnginePath('')
    assert adapter.executable is None


def test_method_settings(qcore_application):
    method = Method(adapter=FakeAdapter())
    theory = _emissions(method.levelOfTheoryChanged)
    scf = _emissions(method.scfChanged)
    run = _emissions(method.runSettingsChanged)

    method.setFunctional('B3LYP')
    method.setFunctional('PBE0')
    method.setBasisSet('def2-SVP')
    method.setScfMaxIterations(200)
    method.setStabilityCheck(True)
    method.setCores(4)

    assert len(theory) == 2 and len(scf) == 2 and len(run) == 1
    assert method.functional == 'PBE0' and method.basisSet == 'def2-SVP'
    assert method.scfMaxIterations == 200 and method.stabilityCheck
    assert method.cores == 4 and method.memoryGb == 16
    assert [choice['value'] for choice in method.functionalChoices][:2] == ['B3LYP', 'PBE']


# Job


def _job(tmp_path, script: str, selected: bool = True) -> Job:
    adapter = ScriptAdapter()
    adapter.script = script
    calculations = Calculations()
    calculations.setSelected('single_point', selected)
    job = Job(adapter, Sample().logic, calculations.logic, None, RunSettings())
    job.set_executable('python')
    job.set_root_folder(str(tmp_path))
    return job


def _wait_for(job: Job, application, seconds: float = 20) -> None:
    end = time.monotonic() + seconds
    while job.running:
        assert time.monotonic() < end, 'job did not end'
        application.processEvents()
        time.sleep(0.05)


def test_job_runs_and_streams_output(qcore_application, tmp_path):
    job = _job(tmp_path, 'import time\nprint("step 1", flush=True)\ntime.sleep(1)\nprint("DONE")\n')
    appended = _emissions(job.outputAppended)
    reset = _emissions(job.outputChanged)

    job.run()
    assert job.running and job.state == 'running' and job.stateLabel == 'Running'
    assert job.folder == str(tmp_path / 'runs' / '001')
    assert (tmp_path / 'runs' / '001' / 'job.inp').read_text(encoding='utf-8').startswith('import time')
    _wait_for(job, qcore_application)

    assert job.state == 'completed' and job.message.startswith('Completed in ')
    assert job.output.splitlines() == ['step 1', 'DONE']
    assert ''.join(text for (text,) in appended) == job.output
    assert len(reset) == 2  # cleared at the start, complete at the end
    assert job.outputPath == str(tmp_path / 'runs' / '001' / 'job.out')


def test_job_fails_on_exit_code_or_missing_success_line(qcore_application, tmp_path):
    job = _job(tmp_path, 'print("DONE")\nraise SystemExit(2)\n')
    job.run()
    _wait_for(job, qcore_application)
    assert job.state == 'failed' and 'exit code 2' in job.message

    job._adapter.script = 'print("no marker")\n'
    job.run()
    _wait_for(job, qcore_application)
    assert job.state == 'failed' and job.folder.endswith('002')


def test_job_does_not_start_without_engine_or_calculation(qcore_application, tmp_path):
    job = _job(tmp_path, 'print("DONE")\n', selected=False)
    job.run()
    assert job.state == 'failed' and job.message == 'No calculation is selected.'

    job.set_executable('')
    job.run()
    assert job.state == 'failed' and 'not found' in job.message
    assert not (tmp_path / 'runs').exists()


def test_job_stop(qcore_application, tmp_path):
    job = _job(tmp_path, 'import time\nprint("started", flush=True)\ntime.sleep(60)\n')
    job.run()
    time.sleep(0.5)

    job.stop()

    assert job.state == 'stopped' and job.message.startswith('Stopped after ')
    assert not job.running


# PyBackend relays


@pytest.fixture
def backend(qcore_application):
    return PyBackend()


def test_backend_fills_project_summary(backend):
    assert backend.project.sampleName == 'C6H6, 12 atoms'
    assert backend.project.engine == 'ORCA'
    assert backend.project.calculations == []

    backend.calculations.setSelected('vibrational_frequencies', True)
    assert backend.project.calculations == ['Vibrational frequencies']


def test_backend_relay_is_saved_with_the_project(backend, tmp_path):
    backend.project.setLocation(str(tmp_path / 'any'))
    backend.project.create()

    backend.calculations.setSelected('single_point', True)

    data = json.loads((tmp_path / 'untitled' / 'project.json').read_text(encoding='utf-8'))
    assert data['calculations'] == ['Single point energy']
    assert data['sample_name'] == 'C6H6, 12 atoms'
    assert data['engine'] == 'ORCA'


def test_backend_relays_job_state_and_folder(backend, tmp_path):
    backend.job.set_executable('')  # as if ORCA were not found
    backend.job.run()
    assert backend.job.state == 'failed'
    assert backend.project.status == 'failed'

    backend.project.setLocation(str(tmp_path / 'any'))
    backend.project.create()
    assert backend.job._root == str(tmp_path / 'untitled')


def test_workflow_label_follows_single_point_geometry(qcore_application):
    calculations = Calculations()
    calculations.setSelected('single_point', True)
    calculations.setSelected('geometry_optimisation', True)
    changes = _emissions(calculations.workflowChanged)

    calculations.setSinglePointGeometry('input')

    assert len(changes) == 1
    assert [step['label'] for step in calculations.workflow] == [
        'Single point energy (at input geometry)',
        'Geometry optimisation',
    ]
