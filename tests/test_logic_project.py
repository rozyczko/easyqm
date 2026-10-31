# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
import json
from pathlib import Path

import pytest

from Backends.Py.logic.project import FILE_FORMAT
from Backends.Py.logic.project import Engine
from Backends.Py.logic.project import Project
from Backends.Py.logic.project import ProjectStatus


def make_project(parent: Path, name: str = 'benzene') -> Project:
    project = Project()
    project.parent = parent
    project.name = name
    return project


def test_defaults():
    project = Project()

    assert project.created is False
    assert project.name == 'untitled'
    assert project.path == Path.home() / 'untitled'
    assert project.path_json == Path.home() / 'untitled' / 'project.json'
    assert project.engine is Engine.NONE
    assert project.status is ProjectStatus.NEW
    assert project.as_dict()['created'] == ''
    assert project.as_dict()['modified'] == ''


def test_parent_and_name_define_path_until_created(tmp_path):
    project = make_project(tmp_path)

    assert project.parent == tmp_path
    assert project.path == tmp_path / 'benzene'
    project.name = 'water'
    assert project.path == tmp_path / 'water'


def test_create_writes_project_file(tmp_path):
    project = make_project(tmp_path)
    project.description = 'B3LYP'

    project.create()

    assert project.created
    assert project.path == tmp_path / 'benzene'
    data = json.loads(project.path_json.read_text(encoding='utf-8'))
    assert data['file_format'] == FILE_FORMAT
    assert data['name'] == 'benzene'
    assert data['description'] == 'B3LYP'
    assert data['created'] and data['modified']


def test_create_refuses_existing_folder(tmp_path):
    (tmp_path / 'benzene').mkdir()
    project = make_project(tmp_path)

    with pytest.raises(FileExistsError):
        project.create()
    assert not project.created
    assert project.created_at is None


def test_save_requires_created():
    with pytest.raises(RuntimeError):
        Project().save()


def test_save_and_load_round_trip(tmp_path):
    project = make_project(tmp_path)
    project.create()
    project.description = 'Benzene optimisation + frequencies'
    project.sample_name = 'C6H6 · 12 atoms · molecular'
    project.calculations = ['Single point', 'Geometry optimisation', 'Frequencies']
    project.engine = Engine.ORCA
    project.status = ProjectStatus.COMPLETED
    project.save()

    loaded_from_folder = Project()
    loaded_from_folder.load(tmp_path / 'benzene')
    assert loaded_from_folder.created
    assert loaded_from_folder.path == tmp_path / 'benzene'
    assert loaded_from_folder.parent == tmp_path
    assert loaded_from_folder.as_dict() == project.as_dict()
    assert loaded_from_folder.engine is Engine.ORCA
    assert loaded_from_folder.status is ProjectStatus.COMPLETED

    loaded_from_file = Project()
    loaded_from_file.load(project.path_json)
    assert loaded_from_file.as_dict() == project.as_dict()


def test_rename_and_relocate_after_create_keep_the_folder(tmp_path):
    project = make_project(tmp_path, 'original')
    project.create()

    project.name = 'renamed'
    project.parent = tmp_path / 'elsewhere'
    assert project.path == tmp_path / 'original'

    project.save()
    assert json.loads(project.path_json.read_text(encoding='utf-8'))['name'] == 'renamed'


def test_load_rejects_bad_files_and_keeps_state(tmp_path):
    project = Project()
    project.name = 'keep'
    bad = tmp_path / 'bad'
    bad.mkdir()

    with pytest.raises(FileNotFoundError):
        project.load(tmp_path / 'missing')

    (bad / 'project.json').write_text('{"file_format": 99, "name": "x"}', encoding='utf-8')
    with pytest.raises(ValueError, match='file format'):
        project.load(bad)

    (bad / 'project.json').write_text('not json', encoding='utf-8')
    with pytest.raises(ValueError):
        project.load(bad)

    (bad / 'project.json').write_text('{"file_format": 1}', encoding='utf-8')
    with pytest.raises(ValueError, match='not a project file'):
        project.load(bad)

    (bad / 'project.json').write_text('{"file_format": 1, "name": "x", "engine": "GAUSSIAN"}', encoding='utf-8')
    with pytest.raises(ValueError):
        project.load(bad)

    assert project.name == 'keep'
    assert not project.created


def test_status_labels():
    assert ProjectStatus.NEW.label == 'Not run'
    assert ProjectStatus.ENGINE_NOT_FOUND.label == 'Engine not found'
