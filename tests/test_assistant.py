# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""The assistant (LLM_INTEG_DESIGN.md): the backend changes it relies on, the workspace it sees
and changes, the turn loop with a fake Anthropic client, the controller and its settings.
No test reaches the network or a real engine."""

import json
import os
import threading
import time
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QSettings

import Backends.Py.assistant_settings as assistant_settings
from Backends.Py.assistant import Assistant
from Backends.Py.assistant_settings import KEYRING_SERVICE
from Backends.Py.assistant_settings import KEYRING_USER
from Backends.Py.assistant_settings import AssistantSettings
from Backends.Py.calculations import Calculations
from Backends.Py.job import Job
from Backends.Py.logic import sample as sample_logic
from Backends.Py.logic.assistant import StubAssistant
from Backends.Py.logic.calculations import CalculationType
from Backends.Py.logic.claude_backend import FALLBACK_BETA
from Backends.Py.logic.claude_backend import MAX_REQUESTS
from Backends.Py.logic.claude_backend import SYSTEM_MESSAGES_BETA
from Backends.Py.logic.results import Excitation
from Backends.Py.logic.results import ExcitedStates
from Backends.Py.logic.results import Results as ResultsLogic
from Backends.Py.logic.sample import STRUCTURES_DIR
from Backends.Py.method import Method
from Backends.Py.project import Project
from Backends.Py.results import Results
from Backends.Py.sample import Sample
from Backends.Py.workspace import MAX_STRICT_OPTIONAL
from Backends.Py.workspace import MAX_STRICT_TOOLS
from Backends.Py.workspace import TOOLS
from Backends.Py.workspace import Action
from Backends.Py.workspace import Outcome
from Backends.Py.workspace import Workspace
from Backends.Py.workspace import data_text
from Backends.Py.workspace import facts_text
from fakes import ScriptAdapter
from fakes import emissions

DONE_SCRIPT = 'print("DONE")\n'
SLOW_SCRIPT = 'import time\ntime.sleep(30)\nprint("DONE")\n'


def _settings(tmp_path) -> QSettings:
    return QSettings(str(tmp_path / 'settings.ini'), QSettings.Format.IniFormat)


def _wait(condition, application, seconds: float = 10) -> None:
    end = time.monotonic() + seconds
    while not condition():
        assert time.monotonic() < end, 'timed out'
        application.processEvents()
        time.sleep(0.01)


class Parts(SimpleNamespace):
    """The backend parts of one workspace, an engine that runs a Python script."""


@pytest.fixture
def parts(qcore_application, tmp_path):
    adapter = ScriptAdapter()
    adapter.script = DONE_SCRIPT
    adapter.info = adapter.info.__class__(found=True, version='6.1.1', path='python')
    project, sample, calculations = Project(), Sample(), Calculations()
    method = Method(adapters=[adapter], settings=_settings(tmp_path))
    job = Job(method.adapter, sample.logic, calculations.logic, method.logic, method.run_settings)
    job.set_executable('python')
    job.set_root_folder(str(tmp_path))
    results = Results()
    workspace = Workspace(project, sample, calculations, method, job, results)
    yield Parts(adapter=adapter, project=project, sample=sample, calculations=calculations, method=method,
                job=job, results=results, workspace=workspace)
    job.stop()


def _run(workspace: Workspace, name: str, args: dict) -> Outcome:
    """A tool call as the assistant makes it without approval."""
    prepared = workspace.prepare(name, args)
    return prepared.run() if isinstance(prepared, Action) else prepared


# Backend changes the assistant relies on


def test_electronic_state_follows_the_electron_count(qcore_application):
    sample = Sample()  # benzene: 42 electrons
    changed = emissions(sample.electronicStateChanged)
    assert sample.logic.multiplicities() == [1, 3, 5, 7]
    assert [choice['label'] for choice in sample.multiplicityChoices][:2] == ['1 (singlet)', '3 (triplet)']

    sample.setCharge(1)  # 41 electrons: a singlet is impossible, so the lowest allowed doublet
    assert (sample.charge, sample.multiplicity) == (1, 2) and changed
    sample.setMultiplicity(3)  # wrong parity: refused
    assert sample.multiplicity == 2
    with pytest.raises(ValueError, match='allow multiplicity 2, 4, 6'):
        sample.set_electronic_state(1, 1)
    sample.set_electronic_state(0, 3)
    assert (sample.charge, sample.multiplicity) == (0, 3)
    assert 'fewer than no electrons' in sample.logic.electronic_state_problem(50, 1)


def test_fixing_atoms_by_index_ignores_the_selection(qcore_application):
    sample = Sample()
    sample.selectAtom(0, 'only')
    sample.selectAtom(1, 'toggle')

    assert sample.set_atoms_fixed([0, 0], True) == [0]
    assert [atom['fixed'] for atom in sample.atoms][:3] == [True, False, False]
    sample.setAtomFixed(0, False)  # the table's checkbox still frees every selected atom
    sample.setAtomFixed(1, True)
    assert [atom['fixed'] for atom in sample.atoms][:3] == [True, True, False]
    with pytest.raises(ValueError):
        sample.set_atoms_fixed([2, 99], True)
    assert not sample.atoms[2]['fixed']


def test_structure_files_over_the_size_limit_are_refused(qcore_application, tmp_path, monkeypatch):
    sample = Sample()
    monkeypatch.setattr(sample_logic, 'MAX_FILE_BYTES', 10)
    path = tmp_path / 'water.xyz'
    path.write_text('3\n\nO 0 0 0\nH 0 0 1\nH 0 1 0\n', encoding='utf-8')
    assert 'larger than' in sample.load_file(path) and sample.formula == 'C6H6'


def test_selection_is_replaced_with_one_notification(qcore_application):
    calculations = Calculations()
    changed = emissions(calculations.externalSelectionChanged)
    calculations.set_selection({CalculationType.SINGLE_POINT, CalculationType.VIBRATIONAL_FREQUENCIES})
    calculations.set_selection({CalculationType.SINGLE_POINT, CalculationType.VIBRATIONAL_FREQUENCIES})
    assert len(changed) == 1 and calculations.selectedCount == 2


def test_job_preflight_and_unexpected_input_errors(parts, qcore_application):
    job = parts.job
    assert job.preflight() == 'No calculation is selected.'
    parts.calculations.setSelected('single_point', True)
    assert job.preflight() == ''

    parts.adapter.input_text = lambda *args: {}['missing']  # a KeyError, as from a keyword table
    job.run()
    assert job.state == 'failed' and 'Unexpected KeyError' in job.message and job.record is None


def test_job_records_what_it_was_computed_from(parts, qcore_application):
    parts.calculations.setSelected('single_point', True)
    parts.job.run()
    record = parts.job.record
    assert record['run_id'] == '001' and record['engine'] == 'ORCA' and record['calculations'] == ['Single point energy']
    assert set(record['configuration']) == {'sample', 'calculations', 'method'}
    _wait(lambda: not parts.job.running, qcore_application)
    assert 'DONE' in parts.job.tail(10) and len(parts.job.tail(2)) == 2


# Workspace: what the model sees


def test_snapshot_separates_application_facts_from_file_data(parts):
    facts, data = parts.workspace.snapshot()
    method = facts['method']
    assert method['basis_set'] == 'def2-TZVP' and 'cc-pVDZ' in method['basis_set_choices']
    assert method['family_choices'] == ['HF', 'DFT'] and 'kpoint_spacing' not in method  # a molecule
    assert facts['sample']['atoms']['total'] == 12 and facts['sample']['multiplicity_choices'] == [1, 3, 5, 7]
    assert facts['calculations']['options']['geometry_optimisation']['convergence'] == 'tight'
    assert 'benzene.xyz' in facts['sample']['examples']
    assert data['structure_file'] == 'benzene.xyz' and data['atom_labels'][0] == 'C1'
    # Labels and the structure file name are data, never part of the operator facts.
    assert '"label"' not in facts_text(facts) and 'structure_file' not in json.dumps(facts)
    assert data_text(data).startswith('<data origin="workspace">')


def test_engine_output_is_not_shared_when_turned_off(parts, qcore_application):
    parts.calculations.setSelected('single_point', True)
    parts.job.run()
    _wait(lambda: not parts.job.running, qcore_application)
    assert 'DONE' in parts.workspace.snapshot()[1]['output_tail']
    assert _run(parts.workspace, 'get_job_output', {'lines': 5}).text == 'DONE'

    parts.workspace.send_output = False
    assert 'output_tail' not in parts.workspace.snapshot()[1]
    outcome = _run(parts.workspace, 'get_job_output', {'lines': 5})
    assert outcome.status == 'failed' and 'turned off' in outcome.text


# Workspace: tools


def _optional(schema: dict) -> int:
    """Optional parameters of a schema, nested objects included, counted as the API counts them."""
    properties = schema.get('properties', {})
    nested = sum(_optional(value) for value in properties.values() if value.get('type') == 'object')
    return len(set(properties) - set(schema.get('required', []))) + nested


def test_strict_tools_stay_within_the_api_limits():
    # The API refuses the whole request when the strict tools are too many or have too many optional parameters.
    strict = [tool for tool in TOOLS if tool['strict']]
    assert len(strict) <= MAX_STRICT_TOOLS
    assert sum(_optional(tool['input_schema']) for tool in strict) <= MAX_STRICT_OPTIONAL
    assert 'anyOf' not in json.dumps(strict)  # union types have a limit of their own


def test_patches_are_checked_without_a_strict_schema(parts):
    workspace, method = parts.workspace, parts.method
    for args in ({'scf_max_iterations': '50'}, {'scf_max_iterations': True}, {'stability_check': 'yes'},
                 {'kpoint_grid': [2, 2]}, {'basis_set': ['cc-pVDZ']}):
        assert _run(workspace, 'set_method', args).status == 'failed', args
    for args in ({'geometry_optimisation': 50}, {'geometry_optimisation': {'max_steps': 'many'}},
                 {'geometry_optimisation': {'colour': 'red'}}, {'phonons': {}}):
        assert _run(workspace, 'set_calculation_options', args).status == 'failed', args
    assert method.scfMaxIterations != '50' and parts.calculations.optMaxSteps != 'many'


def test_set_method_applies_all_fields_or_none(parts):
    workspace, method = parts.workspace, parts.method
    outcome = _run(workspace, 'set_method', {'basis_set': 'cc-pVDZ', 'functional': 'PBE0'})
    assert outcome.status == 'changed' and (method.basisSet, method.functional) == ('cc-pVDZ', 'PBE0')
    assert 'def2-TZVP → cc-pVDZ' in outcome.text

    outcome = _run(workspace, 'set_method', {'basis_set': 'def2-SVP', 'functional': 'BLYP'})
    assert outcome.status == 'failed' and 'B3LYP, PBE' in outcome.text and method.basisSet == 'cc-pVDZ'
    assert 'Hartree–Fock' in _run(workspace, 'set_method', {'family': 'HF', 'dispersion': 'D3'}).text
    assert 'does not use the memory' in _run(workspace, 'set_method', {'memory_gb': 8}).text  # ScriptAdapter
    assert 'crystals only' in _run(workspace, 'set_method', {'kpoint_grid': [2, 2, 2]}).text
    assert _run(workspace, 'set_method', {}).status == 'failed'
    assert workspace.prepare('set_method', {'colour': 'red'}).status == 'failed'


def test_calculation_options_refuse_combinations_the_engine_ignores(parts):
    workspace = parts.workspace
    outcome = _run(workspace, 'set_calculation_options', {'vibrational_frequencies': {'raman': True}})
    assert outcome.status == 'failed' and 'numerical' in outcome.text and not parts.calculations.freqRaman
    outcome = _run(workspace, 'set_calculation_options',
                   {'vibrational_frequencies': {'raman': True, 'type': 'numerical'},
                    'geometry_optimisation': {'max_steps': 50}})
    assert outcome.status == 'changed' and parts.calculations.freqRaman and parts.calculations.optMaxSteps == 50
    assert 'needs a crystal' in _run(workspace, 'set_calculation_options',
                                     {'geometry_optimisation': {'optimise': 'positions_and_cell'}}).text


def test_structures_load_only_from_allowed_places(parts, tmp_path):
    workspace, sample = parts.workspace, parts.sample
    action = workspace.prepare('load_structure', {'name': 'toluene.xyz'})
    assert isinstance(action, Action) and action.effect == 'mutate'
    assert 'C7H8, 15 atoms' in action.run().text

    secret = tmp_path / 'private.xyz'
    secret.write_text('1\n\nXx 0 0 0\n', encoding='utf-8')
    names = [str(secret), '../../pyproject.toml', 'private.xyz']
    if secret.drive == STRUCTURES_DIR.drive:  # Windows has no relative path from one drive to another
        names.append(os.path.relpath(secret, STRUCTURES_DIR))  # ../../…/private.xyz: out of the examples
    for name in names:
        assert workspace.prepare('load_structure', {'name': name}).status == 'failed', name

    sample.loadStructure(str(secret))  # picked in the file dialog: now allowed, and its error is redacted
    outcome = _run(workspace, 'load_structure', {'name': 'private.xyz'})
    assert outcome.status == 'failed' and 'Xx' not in outcome.text

    sample.set_atoms_fixed([0], True)  # an edit since the last load: replacing it asks first
    assert workspace.prepare('load_structure', {'name': 'benzene.xyz'}).effect == 'replace'


def test_atoms_are_fixed_by_index_at_a_known_revision(parts):
    workspace = parts.workspace
    revision = workspace.revisions['sample']
    outcome = _run(workspace, 'set_atoms_fixed', {'indices': [3], 'fixed': True, 'sample_revision': revision})
    assert outcome.status == 'changed' and parts.sample.fixedCount == 1
    stale = _run(workspace, 'set_atoms_fixed', {'indices': [4], 'fixed': True, 'sample_revision': revision})
    assert stale.status == 'stale_state' and stale.is_error and parts.sample.fixedCount == 1


def test_atoms_are_added_moved_and_removed(parts):
    workspace, sample = parts.workspace, parts.sample
    outcome = _run(workspace, 'add_atom', {'element': 'O', 'position': [0, 0, 3], 'coordinates': 'cartesian'})
    assert outcome.status == 'changed' and sample.formula == 'C6H6O' and sample.selectedAtoms == [12]
    assert sample.atoms[12]['z'] == 3
    assert 'not an element' in _run(workspace, 'add_atom', {'element': 'Xx', 'position': [0, 0, 0],
                                                            'coordinates': 'cartesian'}).text
    assert 'crystal' in _run(workspace, 'add_atom', {'element': 'O', 'position': [0, 0, 0],
                                                     'coordinates': 'fractional'}).text

    revision = workspace.revisions['sample']
    move = {'moves': [{'index': 12, 'position': [0, 0, 4]}], 'coordinates': 'cartesian', 'sample_revision': revision}
    assert _run(workspace, 'move_atoms', move).status == 'changed' and sample.atoms[12]['z'] == 4
    assert _run(workspace, 'move_atoms', move).status == 'stale_state'  # the move raised the revision
    revision = workspace.revisions['sample']
    twice = [{'index': 0, 'position': [0, 0, 0]}, {'index': 0, 'position': [1, 0, 0]}]
    assert 'at most once' in _run(workspace, 'move_atoms', {'moves': twice, 'coordinates': 'cartesian',
                                                            'sample_revision': revision}).text
    assert _run(workspace, 'move_atoms', {'moves': [{'index': 0, 'position': [0, 0]}], 'coordinates': 'cartesian',
                                          'sample_revision': revision}).status == 'failed'

    assert 'at least one atom' in _run(workspace, 'remove_atoms', {'indices': list(range(13)),
                                                                   'sample_revision': revision}).text
    outcome = _run(workspace, 'remove_atoms', {'indices': [12], 'sample_revision': revision})
    assert outcome.status == 'changed' and sample.formula == 'C6H6' and sample.atomCount == 12


def test_zmatrix_values_are_set_while_the_zmatrix_is_shown(parts):
    workspace, sample = parts.workspace, parts.sample
    shown = []
    workspace.navigate = shown.append
    revision = workspace.revisions['sample']
    edit = {'atom': 1, 'field': 'bond', 'value': 1.2, 'sample_revision': revision}
    assert 'set_view' in _run(workspace, 'set_zmatrix_value', edit).text

    outcome = workspace.prepare('set_view', {'coordinates': 'zmatrix'})
    assert outcome.status == 'changed' and sample.coordinates == 'zmatrix' and shown == ['sample']
    assert workspace.revisions['sample'] == revision  # the view is not the structure
    rows = workspace.snapshot()[0]['sample']['view']['zmatrix']['items']
    first, row = rows[0], next(row for row in rows if row['bond_to'] is not None)
    assert 'origin or an axis' in _run(workspace, 'set_zmatrix_value', {**edit, 'atom': first['i']}).text

    outcome = _run(workspace, 'set_zmatrix_value', {**edit, 'atom': row['i']})
    assert outcome.status == 'changed'
    rows = workspace.snapshot()[0]['sample']['view']['zmatrix']['items']
    assert next(r for r in rows if r['i'] == row['i'])['bond'] == 1.2
    refused = _run(workspace, 'set_zmatrix_value', {**edit, 'atom': row['i'], 'value': -1.0,
                                                    'sample_revision': workspace.revisions['sample']})
    assert refused.status == 'failed' and 'positive' in refused.text


def test_the_view_changes_at_once_and_only_as_the_sample_allows(parts):
    workspace, sample = parts.workspace, parts.sample
    outcome = workspace.prepare('set_view', {'coordinates': 'fractional', 'selected': [0, 2]})
    assert outcome.status == 'failed' and sample.coordinates == 'cartesian' and sample.selectedAtoms == []
    assert 'crystals only' in workspace.prepare('set_view', {'repeat': [2, 2, 2]}).text
    assert workspace.prepare('set_view', {'selected': [0, 2]}).status == 'changed' and sample.selectedAtoms == [0, 2]
    assert workspace.prepare('set_view', {'selected': []}).status == 'changed' and sample.selectedAtoms == []
    assert workspace.prepare('set_view', {}).status == 'failed'


def test_a_crystal_cell_and_its_drawn_cells(parts):
    workspace, sample = parts.workspace, parts.sample
    cell = {'a': 5.0, 'b': 5.0, 'c': 5.0, 'alpha': 90.0, 'beta': 90.0, 'gamma': 90.0}
    assert 'no unit cell' in _run(workspace, 'set_cell', cell).text
    assert _run(workspace, 'load_structure', {'name': 'Si.cif'}).status == 'changed' and sample.periodic

    outcome = _run(workspace, 'set_cell', cell)
    assert outcome.status == 'changed' and sample.cell['a'] == 5.0
    assert 'between 0° and 180°' in _run(workspace, 'set_cell', {**cell, 'gamma': 180.0}).text

    assert workspace.prepare('set_view', {'repeat': [2, 2, 2], 'boundary_atoms': False}).status == 'changed'
    assert sample.viewRepeat == [2, 2, 2] and not sample.viewBoundaryAtoms
    assert workspace.prepare('set_view', {'repeat': [5, 1, 1]}).status == 'failed' and sample.viewRepeat == [2, 2, 2]

    move = {'moves': [{'index': 0, 'position': [0.5, 0.5, 0.5]}], 'coordinates': 'fractional',
            'sample_revision': workspace.revisions['sample']}
    assert _run(workspace, 'move_atoms', move).status == 'changed' and sample.atoms[0]['fx'] == 0.5


def test_project_details_and_autosave(parts, tmp_path):
    workspace, project = parts.workspace, parts.project
    assert _run(workspace, 'set_project_details', {'name': 'Benzene run', 'description': 'A test.'}).status == 'changed'
    assert (project.name, project.description) == ('Benzene run', 'A test.')
    assert workspace.snapshot()[1]['project_name'] == 'Benzene run'
    outcome = _run(workspace, 'set_project_details', {'name': 'a/b', 'description': 'Other.'})
    assert outcome.status == 'failed' and project.description == 'A test.'
    assert workspace.prepare('set_project_details', {'autosave': True}).effect == 'mutate'  # nothing on disk yet

    project.setAutoSave(False)
    project.setLocation(str(tmp_path / 'any'))
    project.create()
    assert workspace.prepare('set_project_details', {'autosave': True}).effect == 'persist'  # writes the file


def test_electronic_state_needs_an_open_shell_reference(parts):
    workspace = parts.workspace
    assert 'open-shell' in _run(workspace, 'set_electronic_state', {'multiplicity': 3}).text
    _run(workspace, 'set_method', {'reference': 'UKS'})
    assert _run(workspace, 'set_electronic_state', {'charge': 1}).text == 'charge +0 → +1, multiplicity 1 → 2.'
    assert 'allow multiplicity' in _run(workspace, 'set_electronic_state', {'multiplicity': 3}).text
    assert 'not RKS' in _run(workspace, 'set_method', {'reference': 'RKS'}).text


def test_run_workflow_shows_what_and_where_and_runs_once(parts, qcore_application):
    workspace = parts.workspace
    assert _run(workspace, 'run_workflow', {}).text == 'No calculation is selected.'  # preflight
    _run(workspace, 'select_calculations', {'types': ['single_point'], 'mode': 'replace'})
    parts.adapter.script = SLOW_SCRIPT
    action = workspace.prepare('run_workflow', {})
    assert action.effect == 'start' and 'B3LYP-D3(BJ)/def2-TZVP' in action.detail
    assert 'scratch folder' in action.detail[-1] or 'project folder' in action.detail[-1]
    assert action.run().text.startswith('Started run 001')
    assert workspace.prepare('run_workflow', {}).status == 'already_running'
    assert 'job is running' in workspace.prepare('set_method', {'basis_set': 'def2-SVP'}).text
    assert _run(workspace, 'stop_job', {}).text == 'Stopped run 001; state stopped.'


def test_results_say_whether_they_belong_to_the_current_setup(parts, qcore_application):
    workspace = parts.workspace
    parts.calculations.setSelected('single_point', True)
    parts.job.run()
    _wait(lambda: not parts.job.running, qcore_application)
    results = ResultsLogic()
    results.final_energy = -232.1
    parts.results.set_results(results)
    assert workspace.snapshot()[0]['results']['matches_current_state']

    parts.method.setBasisSet('def2-SVP')
    facts = workspace.snapshot()[0]['results']
    assert not facts['matches_current_state'] and facts['stale_reasons'] == ['method changed since the run']
    workspace.send_results = False
    assert workspace.snapshot()[0]['results'] == {'shared': False}


def test_the_assistant_sets_up_excited_states(parts):
    workspace, options = parts.workspace, parts.calculations.logic.excited_states
    assert _run(workspace, 'select_calculations', {'types': ['excited_states'], 'mode': 'add'}).status == 'changed'
    state = workspace.snapshot()[0]['calculations']['options']['excited_states']
    assert state['method_choices'] == ['tddft', 'eom_ccsd'] and state['states'] == 5 and state['tda']

    outcome = _run(workspace, 'set_calculation_options',
                   {'excited_states': {'method': 'eom_ccsd', 'states': 3, 'frozen_core': False}})
    assert outcome.status == 'changed' and (options.method, options.states, options.frozen_core) == ('eom_ccsd', 3, False)

    _run(workspace, 'set_method', {'reference': 'UKS'})
    outcome = _run(workspace, 'set_calculation_options', {'excited_states': {'method': 'tddft', 'triplets': True}})
    assert outcome.status == 'failed' and 'closed-shell' in outcome.text and options.method == 'eom_ccsd'
    assert _run(workspace, 'set_calculation_options', {'excited_states': {'states': 0}}).status == 'failed'
    assert _run(workspace, 'set_calculation_options', {'excited_states': {'method': 'cc3'}}).status == 'failed'


def test_excited_states_are_refused_for_a_crystal(parts):
    workspace = parts.workspace
    _run(workspace, 'load_structure', {'name': 'Si.cif'})
    parts.calculations.set_periodic(True)  # as PyBackend relays the sample's kind
    facts = workspace.snapshot()[0]['calculations']
    assert 'excited_states' not in facts['available'] and facts['unavailable'] == {'excited_states': 'Molecules only'}

    outcome = _run(workspace, 'select_calculations', {'types': ['single_point', 'excited_states'], 'mode': 'replace'})
    assert outcome.status == 'failed' and 'Molecules only' in outcome.text and parts.calculations.selectedCount == 0
    assert _run(workspace, 'select_calculations', {'types': ['excited_states'], 'mode': 'remove'}).status == 'changed'


def test_excited_state_results_are_in_the_snapshot(parts, qcore_application):
    parts.calculations.setSelected('excited_states', True)
    parts.job.run()
    _wait(lambda: not parts.job.running, qcore_application)
    states = [Excitation(1, 7.535, 1, 0.0172), Excitation(2, 9.429, 1, 0.0)]
    parts.results.set_results(ResultsLogic(excited_states=ExcitedStates('TD-DFT/TDA', states)))

    facts = parts.workspace.snapshot()[0]['results']['excited_states']
    assert facts['method'] == 'TD-DFT/TDA' and facts['total'] == 2
    assert facts['items'][0] == {'state': 1, 'spin': 'singlet', 'energy_ev': 7.535, 'wavelength_nm': '164.5',
                                 'f': '0.0172'}


def test_approval_follows_the_effect_and_the_mode(parts):
    workspace = parts.workspace
    mutate = workspace.prepare('set_method', {'basis_set': 'def2-SVP'})
    save = Action('save_project', 'persist', '', [], lambda: Outcome('ok', ''))
    assert [workspace.approval_needed(mutate, mode) for mode in ('default', 'every', 'never')] == [False, True, False]
    assert [workspace.approval_needed(save, mode) for mode in ('default', 'every', 'never')] == [True, True, False]
    assert workspace.prepare('save_project', {}).text.startswith('No project is open')


def test_stub_answers_from_the_snapshot(parts):
    stub, (facts, data) = StubAssistant(), parts.workspace.snapshot()
    assert 'D6h' in stub.reply('what is the point group?', facts, data)
    assert 'def2-TZVP' in stub.reply('is the basis ok?', facts, data)
    assert 'C6H6, 12 atoms, D6h' in stub.reply('hello', facts, data)
    assert stub.suggestions({'page': 'sample', 'job': {'state': 'idle'}, 'results': {}})[0].startswith('What is the point')


# A fake Anthropic client


def _text(text):
    return SimpleNamespace(type='text', text=text)


def _tool(call_id, name, args):
    return SimpleNamespace(type='tool_use', id=call_id, name=name, input=args)


def _message(*blocks, stop='end_turn', model='claude-opus-5-5'):
    usage = SimpleNamespace(input_tokens=100, cache_read_input_tokens=50, cache_creation_input_tokens=10, output_tokens=5)
    return SimpleNamespace(content=list(blocks), stop_reason=stop, model=model, usage=usage)


class FakeStream:
    def __init__(self, reply, gate=None):
        self._reply, self._gate = reply, gate

    def __enter__(self):
        if isinstance(self._reply, Exception):
            raise self._reply
        return self

    def __exit__(self, *exc):
        return False

    @property
    def text_stream(self):
        if self._gate is not None:
            self._gate.wait(5)
        return iter([block.text for block in self._reply.content if block.type == 'text'])

    def get_final_message(self):
        return self._reply

    def close(self):
        if self._gate is not None:
            self._gate.set()


class FakeClient:
    """Answers each request with the next scripted reply (a message or an exception)."""

    def __init__(self, *replies, gate=None):
        self.replies, self.requests, self.gate = list(replies), [], gate
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    def _stream(self, **params):
        self.requests.append(params)
        return FakeStream(self.replies.pop(0), self.gate)


class FakeKeyring:
    def __init__(self, works=True):
        self.store, self.works = {}, works

    def set_password(self, service, user, value):
        if not self.works:
            raise RuntimeError('no backend')
        self.store[(service, user)] = value

    def get_password(self, service, user):
        return self.store.get((service, user))

    def delete_password(self, service, user):
        self.store.pop((service, user), None)


@pytest.fixture
def chat(parts, tmp_path, monkeypatch):
    """An assistant with a key in its settings and a fake client to script."""
    monkeypatch.setattr(assistant_settings, 'sdk_available', lambda: True)
    settings = AssistantSettings(_settings(tmp_path), FakeKeyring())
    settings.setKey('sk-test', False)
    assistant = Assistant(parts.workspace, settings, delay_ms=10)
    parts.assistant, parts.settings = assistant, settings

    def script(*replies, gate=None):
        client = FakeClient(*replies, gate=gate)
        settings.client_factory = lambda key: client
        return client

    parts.script = script
    yield parts
    assistant.shutdown()


def _turn(chat, question, qcore_application):
    chat.assistant.send(question)
    _wait(lambda: not chat.assistant.busy, qcore_application)


# Turns


def test_a_turn_runs_tools_and_keeps_the_conversation_append_only(chat, qcore_application):
    client = chat.script(
        _message(_text('Setting the basis.'), _tool('t1', 'set_method', {'basis_set': 'cc-pVDZ'}), stop='tool_use'),
        _message(_text('Done: cc-pVDZ.')),
        _message(_text('It is cc-pVDZ.')),
    )
    _turn(chat, 'Use cc-pVDZ', qcore_application)
    assert chat.method.basisSet == 'cc-pVDZ'
    roles = [item['role'] for item in chat.assistant.messages]
    assert roles == ['user', 'notice', 'assistant', 'action', 'assistant']  # notice: what is sent, once
    assert chat.assistant.messages[3]['text'] == 'basis_set: def2-TZVP → cc-pVDZ.'

    first, second = client.requests[0], client.requests[1]
    assert first['model'] == 'claude-opus-5-5' and first['output_config'] == {'effort': 'medium'}
    assert first['fallbacks'] == 'default' and set(first['betas']) == {SYSTEM_MESSAGES_BETA, FALLBACK_BETA}
    snapshot = first['messages'][1]
    assert snapshot['role'] == 'system' and snapshot['clear_at'] == 'next_user_message'
    assert 'basis_set_choices' in snapshot['content'] and '<data' in first['messages'][0]['content'][1]['text']
    assert second['messages'][3]['content'][0]['content'] == 'basis_set: def2-TZVP → cc-pVDZ.'

    _turn(chat, 'Which basis?', qcore_application)
    third = client.requests[2]['messages']
    assert [m['role'] for m in third] == ['user', 'system', 'assistant', 'user', 'assistant', 'user', 'system']
    questions = [m['content'][0]['text'] for m in third if m['role'] == 'user' and m['content'][0]['type'] == 'text']
    assert questions == ['Use cc-pVDZ', 'Which basis?']
    assert third[1] is client.requests[0]['messages'][1]  # the first snapshot, kept as sent
    assert 'cache_control' in third[5]['content'][-1] and 'cache_control' not in third[0]['content'][-1]
    assert chat.assistant.usageText.startswith('300 input, 150 cached, 30 written to cache and 15 output')


def test_runs_wait_for_the_users_approval(chat, qcore_application):
    chat.calculations.setSelected('single_point', True)
    chat.script(_message(_tool('t1', 'run_workflow', {}), stop='tool_use'), _message(_text('Not started.')))
    chat.assistant.send('Run it')
    _wait(lambda: chat.assistant.approval, qcore_application)
    approval = chat.assistant.approval
    assert approval['title'] == 'Run the workflow' and approval['confirm'] == 'Run'
    assert chat.assistant.status == 'Waiting for your confirmation'

    chat.assistant.answerApproval('wrong id', True)  # a stale card does nothing
    chat.assistant.answerApproval(approval['id'], False)
    _wait(lambda: not chat.assistant.busy, qcore_application)
    assert chat.job.state == 'idle' and 'Not done: Run the workflow' in chat.assistant.messages[-2]['text']


def test_an_approved_run_starts_unless_the_setup_changed(chat, qcore_application):
    chat.calculations.setSelected('single_point', True)
    chat.adapter.script = SLOW_SCRIPT
    client = chat.script(_message(_tool('t1', 'run_workflow', {}), stop='tool_use'), _message(_text('Changed meanwhile.')),
                         _message(_tool('t2', 'run_workflow', {}), stop='tool_use'), _message(_text('Started.')))
    chat.assistant.send('Run it')
    _wait(lambda: chat.assistant.approval, qcore_application)
    chat.method.setBasisSet('def2-SVP')  # the user edits the method while the card waits
    chat.assistant.answerApproval(chat.assistant.approval['id'], True)
    _wait(lambda: not chat.assistant.busy, qcore_application)
    assert chat.job.state == 'idle'
    assert 'method changed while this waited' in client.requests[1]['messages'][3]['content'][0]['content']

    chat.assistant.send('Run it now')
    _wait(lambda: chat.assistant.approval, qcore_application)
    chat.assistant.answerApproval(chat.assistant.approval['id'], True)
    _wait(lambda: not chat.assistant.busy, qcore_application)
    assert chat.job.running and chat.job.record['configuration']['method']


def test_a_declined_action_skips_the_rest_of_its_step(chat, qcore_application):
    chat.settings.setApprovalMode('every')
    client = chat.script(
        _message(_tool('t1', 'set_method', {'basis_set': 'def2-SVP'}), _tool('t2', 'set_method', {'functional': 'PBE'}),
                 stop='tool_use'),
        _message(_tool('t3', 'set_method', {'basis_set': 'def2-SVP'}), stop='tool_use'),
        _message(_text('Understood.')))
    chat.assistant.send('Change things')
    _wait(lambda: chat.assistant.approval, qcore_application)
    chat.assistant.answerApproval(chat.assistant.approval['id'], False)
    _wait(lambda: not chat.assistant.busy, qcore_application)
    results = client.requests[1]['messages'][3]['content']
    assert results[0]['content'].startswith('Not done: the user declined')
    assert results[1]['content'] == 'Not executed: an earlier action in this step was declined.'
    again = client.requests[2]['messages'][5]['content'][0]['content']
    assert again == 'The user already declined this; it was not done.'  # no second card
    assert (chat.method.basisSet, chat.method.functional) == ('def2-TZVP', 'B3LYP')


def test_cancelling_during_an_approval_runs_nothing(chat, qcore_application):
    chat.calculations.setSelected('single_point', True)
    chat.script(_message(_tool('t1', 'run_workflow', {}), stop='tool_use'))
    chat.assistant.send('Run it')
    _wait(lambda: chat.assistant.approval, qcore_application)
    chat.assistant.cancel()
    assert not chat.assistant.approval
    _wait(lambda: not chat.assistant.busy, qcore_application)
    assert chat.job.state == 'idle' and chat.assistant.messages[-1]['text'] == 'Cancelled.'


def test_a_failed_request_keeps_what_already_ran(chat, qcore_application):
    chat.script(_message(_tool('t1', 'set_method', {'basis_set': 'cc-pVDZ'}), stop='tool_use'), ConnectionError('down'))
    _turn(chat, 'Use cc-pVDZ', qcore_application)
    assert chat.method.basisSet == 'cc-pVDZ'
    assert chat.assistant.messages[-1]['role'] == 'error'
    history = chat.assistant._history
    assert [m['role'] for m in history] == ['user', 'system', 'assistant', 'user']  # the exchange that happened

    client = chat.script(ConnectionError('still down'))
    _turn(chat, 'Hello?', qcore_application)
    assert len(chat.assistant._history) == 4  # an unanswered question is not kept
    assert len(client.requests) == 1


def test_a_cut_off_tool_call_is_answered_without_running(chat, qcore_application):
    client = chat.script(_message(_tool('t1', 'set_method', {'basis_set': 'cc-pVDZ'}), stop='max_tokens'),
                         _message(_text('ok')))
    _turn(chat, 'Use cc-pVDZ', qcore_application)
    assert chat.method.basisSet == 'def2-TZVP'
    assert chat.assistant.messages[-1]['text'] == 'The answer was cut off at the output limit.'
    _turn(chat, 'Again', qcore_application)
    assert client.requests[1]['messages'][3]['content'][0]['content'] == 'Not executed: the answer was cut off.'


def test_a_turn_ends_at_its_request_limit(chat, qcore_application):
    chat.script(*[_message(_tool(f't{i}', 'get_workspace', {}), stop='tool_use') for i in range(MAX_REQUESTS)])
    _turn(chat, 'Look around', qcore_application)
    assert chat.assistant.messages[-1]['text'] == 'Stopped: the request limit of this turn was reached.'


def test_clearing_during_a_turn_drops_its_answer(chat, qcore_application):
    gate = threading.Event()
    chat.script(_message(_text('late answer')), gate=gate)
    chat.assistant.send('Hello')
    chat.assistant.clear()
    gate.set()
    _wait(lambda: not chat.assistant.busy, qcore_application)
    assert chat.assistant.messages == [] and chat.assistant._history == []


def test_the_request_follows_the_model_policy(chat, qcore_application):
    chat.settings.setModel('claude-haiku-5-5')
    client = chat.script(_message(_text('hi'), model='claude-haiku-5-5'))
    _turn(chat, 'Hi', qcore_application)
    assert 'fallbacks' not in client.requests[0] and client.requests[0]['betas'] == [SYSTEM_MESSAGES_BETA]

    chat.settings.setModel('some-new-model')
    client = chat.script(_message(_text('hi'), model='some-new-model'))
    _turn(chat, 'Hi', qcore_application)
    request = client.requests[0]
    assert 'betas' not in request and 'output_config' not in request
    new = request['messages'][-1]
    assert new['role'] == 'user' and 'Current EasyQM workspace' in new['content'][-1]['text']


def test_the_answering_model_is_shown(chat, qcore_application):
    chat.script(_message(_text('hi'), model='claude-opus-4-8'))
    _turn(chat, 'Hi', qcore_application)
    assert chat.assistant.modelName == 'claude-opus-5-5 · answered by claude-opus-4-8'
    assert chat.assistant.usageText.startswith('100 input, 50 cached, 10 written to cache and 5 output')


def test_offline_the_stub_answers(chat, qcore_application):
    chat.settings.setOffline(True)
    client = chat.script()
    _turn(chat, 'What is the point group?', qcore_application)
    assert 'D6h' in chat.assistant.messages[-1]['text'] and client.requests == []
    assert chat.assistant.modelName == StubAssistant.name


def test_show_page_reports_the_page_actually_shown(chat):
    chat.assistant.navigateRequested.connect(chat.assistant.setPage)  # as the panel does
    assert _run(chat.workspace, 'show_page', {'page': 'method'}).text == 'The method page is shown.'


# Settings


def test_a_remembered_key_goes_to_the_credential_store(qcore_application, tmp_path, monkeypatch):
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    monkeypatch.delenv('ANTHROPIC_AUTH_TOKEN', raising=False)
    monkeypatch.setattr(assistant_settings, 'CLI_PROFILE_DIR', tmp_path / 'none')
    keyring = FakeKeyring()
    settings = AssistantSettings(_settings(tmp_path), keyring)
    assert settings.keySource == '' and not settings.configured

    settings.setKey(' sk-one ', True)
    assert keyring.store[(KEYRING_SERVICE, KEYRING_USER)] == 'sk-one' and settings.keyStorage == 'keyring'
    assert AssistantSettings(_settings(tmp_path), keyring).hasKey  # read back at the next start
    settings._settings.sync()
    assert 'sk-one' not in (tmp_path / 'settings.ini').read_text(encoding='utf-8')
    settings.clearKey()
    assert not keyring.store.get((KEYRING_SERVICE, KEYRING_USER)) and not settings.hasKey

    monkeypatch.setenv('ANTHROPIC_API_KEY', 'sk-env')
    assert settings.keySource == 'environment variable'


def test_without_a_working_store_a_remembered_key_is_plain_text(qcore_application, tmp_path):
    settings = AssistantSettings(_settings(tmp_path), FakeKeyring(works=False))
    assert not settings.secureStoreAvailable
    settings.setKey('sk-two', True)
    assert settings.keyStorage == 'settings'
    assert AssistantSettings(_settings(tmp_path), FakeKeyring(works=False)).hasKey
    settings.setKey('sk-three', False)  # session only: the stored copy goes
    assert settings.keyStorage == 'session'
    assert not AssistantSettings(_settings(tmp_path), FakeKeyring(works=False)).hasKey


def test_options_are_validated_and_kept(qcore_application, tmp_path):
    settings = AssistantSettings(_settings(tmp_path), FakeKeyring())
    settings.setEffort('extreme')
    settings.setApprovalMode('sometimes')
    settings.setModel('  ')
    assert (settings.effort, settings.approvalMode, settings.model) == ('medium', 'default', 'claude-opus-5-5')
    settings.setSendOutput(False)
    settings.setApprovalMode('every')
    again = AssistantSettings(_settings(tmp_path), FakeKeyring())
    assert not again.sendOutput and again.approvalMode == 'every' and again.sendResults
