# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Proxies of the Sample, Calculations and Method parts, and their relays in PyBackend."""

import json
import sys
import time
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtCore import QUrl

from Backends.Py.calculations import Calculations
from Backends.Py.job import Job
from Backends.Py.logic.engines.base import Capabilities
from Backends.Py.logic.engines.base import EngineAdapter
from Backends.Py.logic.engines.base import EngineInfo
from Backends.Py.logic.engines.orca import CAPABILITIES
from Backends.Py.logic.engines.orca import OrcaAdapter
from Backends.Py.logic.method import RunSettings
from Backends.Py.logic.results import Results as ResultsLogic
from Backends.Py.logic.runner import JobState
from Backends.Py.method import Method
from Backends.Py.py_backend import PyBackend
from Backends.Py.results import Results
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


def test_sample_fix_applies_to_the_selection(qcore_application):
    sample = Sample()
    sample.selectAtom(0, 'only')
    sample.selectAtom(2, 'range')
    changes = _emissions(sample.atomsChanged)

    sample.setAtomFixed(1, True)  # a selected row: all three
    assert [atom['fixed'] for atom in sample.atoms[:4]] == [True, True, True, False]

    sample.setAtomFixed(3, True)  # an unselected row: that one only
    sample.setAtomFixed(0, False)
    assert [atom['fixed'] for atom in sample.atoms[:4]] == [False, False, False, True]
    assert len(changes) == 3


def test_sample_selection(qcore_application):
    sample = Sample()
    changes = _emissions(sample.selectionChanged)

    sample.selectAtom(0, 'only')
    sample.selectAtom(0, 'only')  # unchanged, no signal
    sample.selectAtom(6, 'toggle')
    assert sample.selectedAtoms == [0, 6] and sample.selectionText == 'C1, H7'

    sample.selectAtom(0, 'toggle')  # taken out
    assert sample.selectedAtoms == [6]

    sample.selectAtom(2, 'only')  # replaces
    assert sample.selectedAtoms == [2]

    sample.clearSelection()
    sample.clearSelection()
    assert sample.selectedAtoms == [] and sample.selectionText == ''
    assert len(changes) == 5


def test_sample_selection_measurement(qcore_application):
    sample = Sample()
    measurements = []
    for picks in ([0], [0, 1], [0, 1, 2], [6, 0, 1, 7], [0, 1, 2, 3], [6, 0, 5, 11], [0, 1, 2, 3, 4]):
        sample.clearSelection()
        for index in picks:
            sample.selectAtom(index, 'toggle')
        measurements.append(sample.selectionMeasurement)

    assert measurements == [
        '',
        'distance = 1.3915\u00a0Å',  # C1-C2
        'angle = 120.00°',  # C1-C2-C3, at C2
        'dihedral = 0.00°',  # H7-C1-C2-H8, cis in the ring plane
        'dihedral = 0.00°',
        'dihedral = 0.00°',
        '',  # five atoms
    ]

    sample.clearSelection()
    for index in (0, 1, 0):  # C1 picked twice is taken out again: C2 only
        sample.selectAtom(index, 'toggle')
    assert sample.selectionMeasurement == ''


def test_sample_measurement_sign_and_undefined(qcore_application, tmp_path):
    xyz = tmp_path / 'four.xyz'
    xyz.write_text('5\n\nC 1 0 0\nC 0 0 0\nC 0 0 1\nC 0 -1 1\nC 0 0 -1\n', encoding='utf-8')
    sample = Sample()
    sample.loadXyz(str(xyz))

    sample.selectAtom(0, 'only')
    sample.selectAtom(3, 'range')
    assert sample.selectionMeasurement == 'dihedral = \u221290.00°'

    sample.selectAtom(4, 'only')  # 5, 2, 3, 4 with 2 and 3 on a line with 5
    for index in (1, 2, 3):
        sample.selectAtom(index, 'toggle')
    assert sample.selectionMeasurement == 'dihedral undefined'


def test_sample_range_selection(qcore_application):
    sample = Sample()

    sample.selectAtom(3, 'range')  # no anchor yet: this atom alone
    assert sample.selectedAtoms == [3]

    sample.selectAtom(2, 'only')
    sample.selectAtom(6, 'range')
    assert sample.selectedAtoms == [2, 3, 4, 5, 6] and sample.selectionText == '5 atoms'

    sample.selectAtom(0, 'range')  # from the same anchor, the other way, replacing
    assert sample.selectedAtoms == [2, 1, 0]

    sample.selectAtom(9, 'toggle')  # Ctrl-click moves the anchor
    sample.selectAtom(11, 'range')
    assert sample.selectedAtoms == [9, 10, 11]

    sample.clearSelection()  # and clearing forgets it
    sample.selectAtom(4, 'range')
    assert sample.selectedAtoms == [4]


def test_sample_loads_xyz_and_clears_the_selection(qcore_application, tmp_path):
    water = tmp_path / 'water.xyz'
    water.write_text('3\nwater\nO 0 0 0.117\nH 0 0.757 -0.468\nH 0 -0.757 -0.468\n', encoding='utf-8')
    sample = Sample()
    sample.selectAtom(11, 'only')
    changes = [_emissions(signal) for signal in (sample.sampleChanged, sample.atomsChanged, sample.selectionChanged)]
    external = _emissions(sample.externalSampleChanged)

    sample.loadXyz(QUrl.fromLocalFile(str(water)).toString())  # as the file dialog hands it over

    assert sample.summary == 'water.xyz · H2O · 3 atoms'
    assert sample.bonds == [[0, 1], [0, 2]]
    assert sample.selectedAtoms == []
    assert [len(calls) for calls in changes] == [1, 1, 1] and len(external) == 1


def test_sample_load_error_keeps_the_structure(qcore_application, tmp_path):
    sample = Sample()
    sample.selectAtom(1, 'only')
    errors = _emissions(sample.loadError)

    sample.loadXyz(str(tmp_path / 'missing.xyz'))
    (tmp_path / 'bad.xyz').write_text('1\n\nQ 0 0 0\n', encoding='utf-8')
    sample.loadXyz(str(tmp_path / 'bad.xyz'))

    assert sample.formula == 'C6H6' and sample.selectedAtoms == [1]
    assert 'missing.xyz" could not be read' in errors[0][0] and 'No such file' in errors[0][0]
    assert errors[1][0].endswith('Atom 1: "Q" is not an element.')


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


def test_backend_relays_a_loaded_structure(backend, tmp_path):
    water = tmp_path / 'water.xyz'
    water.write_text('3\n\nO 0 0 0\nH 0 0.76 -0.47\nH 0 -0.76 -0.47\n', encoding='utf-8')

    backend.sample.loadXyz(str(water))

    assert backend.project.sampleName == 'H2O, 3 atoms'
    assert backend.job._sample is backend.sample.logic  # the next run uses the loaded structure


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


# Results (Summary page)

WATER = Path(__file__).parent / 'data' / 'orca_water_opt_freq.out'


def _water() -> ResultsLogic:
    return OrcaAdapter().parse(WATER.read_text(encoding='utf-8'))


def test_results_offer_only_what_was_found(qcore_application):
    results = Results()
    assert not results.available and results.placeholder.startswith('No results yet')

    results.clear('HF/def2-SVP')
    assert results.placeholder.startswith('The results appear here')

    single_point = _water()
    single_point.optimisation = single_point.frequencies = None
    results.set_results(single_point)
    assert [tile['title'] for tile in results.tiles] == ['Final energy (Eh)', 'HOMO–LUMO gap (eV)', 'Dipole moment (D)']
    assert results.tiles[0] == {'title': 'Final energy (Eh)', 'value': '−76.301100', 'detail': 'HF/def2-SVP', 'tone': ''}
    assert results.tiles[2]['detail'] == 'at the input geometry'
    assert not results.hasOptimisation and not results.hasFrequencies
    assert results.geometryRows == [] and results.modes == []

    results.set_results(ResultsLogic())
    assert not results.available and results.placeholder.startswith('The output of the last job holds no results')


def test_results_of_an_optimisation_with_frequencies(qcore_application):
    results = Results()
    changes = _emissions(results.resultsChanged)
    results.set_results(_water())

    assert len(changes) == 1 and results.available and results.placeholder == ''
    assert [tile['title'] for tile in results.tiles] == [
        'Final energy (Eh)',
        'Optimisation',
        'Imaginary modes',
        'HOMO–LUMO gap (eV)',
        'Dipole moment (D)',
        'Gibbs free energy (Eh)',
    ]
    optimisation, imaginary, gap = results.tiles[1], results.tiles[2], results.tiles[3]
    assert (optimisation['value'], optimisation['tone']) == ('Converged', 'good')
    assert optimisation['detail'] == '2 steps · ΔE = −0.69 kcal/⁠mol'
    assert (imaginary['value'], imaginary['tone']) == ('1', 'warning')
    assert imaginary['detail'].startswith('not a minimum · ZPE 13.2')
    assert gap['value'] == '10.34' and gap['detail'] == 'HOMO −8.71 · LUMO 1.63'
    assert results.tiles[5]['detail'] == '298.15 K, 1 atm'

    assert results.geometryRows[0] == {
        'bond': 'O1–H2',
        'bondInitial': '0.9567',
        'bondFinal': '0.9621',
        'bondChange': '+0.0054',
        'angle': 'H2–O1–H3',
        'angleFinal': '104.35',
    }
    assert results.geometryRows[1]['angle'] == '' and len(results.geometryRows) == 2
    assert results.convergenceRows[0] == {
        'criterion': 'Energy change',
        'value': '−5.00e−07',
        'tolerance': '1.0e-06',
        'met': True,
    }

    assert results.hasFrequencies and results.hasRaman
    assert results.modes[0]['imaginary'] and results.modes[0]['frequencyText'] == '−50.00'
    assert results.modes[2]['irIntensity'] == 5.0 and results.modes[2]['ramanText'] == '90.00'


def test_backend_parses_the_output_when_the_job_ends(backend):
    backend.job._set_state(JobState.RUNNING, '')
    assert not backend.results.available
    assert backend.results.placeholder.startswith('The results appear here')

    backend.job._chunks = [WATER.read_text(encoding='utf-8')]
    backend.job._set_state(JobState.COMPLETED, '')

    assert backend.results.available
    assert backend.results.tiles[0]['detail'] == 'B3LYP-D3(BJ)/def2-TZVP'
    assert backend.results.hasOptimisation and backend.results.hasFrequencies
