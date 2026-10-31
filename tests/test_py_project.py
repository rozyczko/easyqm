# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
import json

import pytest
from PySide6.QtCore import QUrl

from Backends.Py.logic.project import Project as ProjectLogic
from Backends.Py.project import Project


def _emissions(signal) -> list:
    calls = []
    signal.connect(lambda *args: calls.append(args))
    return calls


def _read(tmp_path, name='untitled') -> dict:
    return json.loads((tmp_path / name / 'project.json').read_text(encoding='utf-8'))


@pytest.fixture
def project(tmp_path, qcore_application):
    logic = ProjectLogic()
    logic.parent = tmp_path
    return Project(logic=logic)


def test_setters_emit_only_on_change(project):
    names = _emissions(project.nameChanged)
    locations = _emissions(project.locationChanged)

    project.setName('untitled')
    assert names == [] and locations == []

    project.setName('benzene')
    assert len(names) == 1 and len(locations) == 1
    assert project.name == 'benzene'
    assert project.location.endswith('benzene')


def test_set_location_keeps_parent_of_composed_path(project, tmp_path):
    project.setLocation(QUrl.fromLocalFile(str(tmp_path / 'sub' / 'benzene')).toString())

    assert project.parentDirectory == str(tmp_path / 'sub')
    assert project.location == str(tmp_path / 'sub' / 'untitled')


def test_create_writes_file_and_reports(project, tmp_path):
    saved = _emissions(project.projectSaved)
    replaced = _emissions(project.externalProjectChanged)
    project.setName('benzene')

    project.create()

    assert project.created
    assert saved == [(str(tmp_path / 'benzene' / 'project.json'),)]
    assert len(replaced) == 1
    assert project.lastSaved != ''
    assert project.createdAt != ''
    assert project.modifiedAt != ''
    assert not project.hasUnsavedChanges
    assert _read(tmp_path, 'benzene')['name'] == 'benzene'


def test_create_collision_reports_error(project, tmp_path):
    (tmp_path / 'untitled').mkdir()
    errors = _emissions(project.projectSaveError)

    project.create()

    assert not project.created
    assert len(errors) == 1
    assert 'already exists' in errors[0][0]


def test_auto_save_writes_every_change(project, tmp_path):
    project.create()

    project.setDescription('B3LYP')
    project.setEngine('ORCA')
    project.setCalculations(['Single point', 'Frequencies'])
    project.setSampleName('C6H6')
    project.setStatus('completed')

    data = _read(tmp_path)
    assert data['description'] == 'B3LYP'
    assert data['engine'] == 'ORCA'
    assert data['calculations'] == ['Single point', 'Frequencies']
    assert data['sample_name'] == 'C6H6'
    assert data['status'] == 'completed'
    assert project.statusLabel == 'Completed'
    assert not project.hasUnsavedChanges


def test_manual_save_flags_unsaved_changes(project, tmp_path):
    project.create()
    project.setAutoSave(False)
    flags = _emissions(project.hasUnsavedChangesChanged)

    project.setDescription('edited')
    assert project.hasUnsavedChanges
    assert len(flags) == 1
    assert _read(tmp_path)['description'] == ''

    project.save()
    assert not project.hasUnsavedChanges
    assert _read(tmp_path)['description'] == 'edited'


def test_turning_auto_save_on_saves_pending_changes(project, tmp_path):
    project.create()
    project.setAutoSave(False)
    project.setDescription('edited')

    project.setAutoSave(True)

    assert not project.hasUnsavedChanges
    assert _read(tmp_path)['description'] == 'edited'


def test_changes_before_create_are_not_flagged(project):
    project.setDescription('x')
    assert not project.hasUnsavedChanges


def test_save_without_project_reports_error(project):
    errors = _emissions(project.projectSaveError)
    project.save()
    assert len(errors) == 1


def test_load_from_url_then_reset(project, tmp_path, qcore_application):
    project.setName('benzene')
    project.create()
    project.setSampleName('C6H6')

    other = Project(logic=ProjectLogic())
    replaced = _emissions(other.externalProjectChanged)
    other.load(QUrl.fromLocalFile(str(tmp_path / 'benzene')).toString())
    assert other.created
    assert other.name == 'benzene'
    assert other.sampleName == 'C6H6'
    assert other.location == str(tmp_path / 'benzene')
    assert other.lastSaved == ''
    assert len(replaced) == 1

    other.reset()
    assert not other.created
    assert other.name == 'untitled'
    assert other.sampleName == ''
    assert len(replaced) == 2


def test_load_error_reports_and_keeps_state(project, tmp_path):
    errors = _emissions(project.projectLoadError)
    project.setName('keep')

    project.load(str(tmp_path / 'missing'))

    assert len(errors) == 1
    assert project.name == 'keep'
    assert not project.created
