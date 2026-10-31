# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Qt-free project state: what EasyQM remembers about a project between sessions.

A project is a folder with a ``project.json`` at its root (GENERAL_DESIGN.md, section 3.1). This
module owns that file. The other contents of the folder (structure file, run folders, report)
are written by the parts that produce them.
"""

import json
import os
import tempfile
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional
from typing import Union

FILE_FORMAT = 1
PROJECT_FILE_NAME = 'project.json'
DEFAULT_NAME = 'untitled'


class Engine(Enum):
    """Quantum-chemistry codes EasyQM can drive. NONE until the Method tab picks one."""

    NONE = ''
    ORCA = 'ORCA'
    PSI4 = 'PSI4'
    CASTEP = 'CASTEP'


class ProjectStatus(Enum):
    """State of the project's current or last job, as shown by the status pill."""

    NEW = 'new'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'
    STOPPED = 'stopped'
    ENGINE_NOT_FOUND = 'engine_not_found'

    @property
    def label(self) -> str:
        return _STATUS_LABELS[self]


_STATUS_LABELS = {
    ProjectStatus.NEW: 'Not run',
    ProjectStatus.RUNNING: 'Running',
    ProjectStatus.COMPLETED: 'Completed',
    ProjectStatus.FAILED: 'Failed',
    ProjectStatus.STOPPED: 'Stopped',
    ProjectStatus.ENGINE_NOT_FOUND: 'Engine not found',
}


def _now() -> datetime:
    # Aware, to the second: unambiguous if it is ever shown outside the local session.
    return datetime.now().astimezone().replace(microsecond=0)


def _to_iso(value: Optional[datetime]) -> str:
    return value.isoformat() if value is not None else ''


def _from_iso(value: str) -> Optional[datetime]:
    return datetime.fromisoformat(value) if value else None


def _write_atomically(path: Path, text: str) -> None:
    """Write `text` to `path` so that a failure leaves any previous file untouched."""
    file_descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f'{path.name}.', suffix='.tmp')
    try:
        with os.fdopen(file_descriptor, mode='w', encoding='utf-8') as file:
            file.write(text)
        os.replace(temporary_name, path)
    except Exception:
        Path(temporary_name).unlink(missing_ok=True)
        raise


class Project:
    """The project folder and its ``project.json``.

    Until `create` or `load` has been called the project exists only in memory, `created` is
    False and `path` is where `create` would put it (`parent / name`). Once it is on disk the
    folder is fixed: renaming the project changes the stored name, not the folder.
    """

    def __init__(self):
        self.reset()

    def reset(self) -> None:
        self.name = DEFAULT_NAME
        self.description = ''
        self.sample_name = ''
        self.calculations: list[str] = []
        self.engine = Engine.NONE
        self.status = ProjectStatus.NEW
        self.created_at: Optional[datetime] = None
        self.modified_at: Optional[datetime] = None
        self._parent = Path.home()
        self._path_on_disk: Optional[Path] = None

    # Location

    @property
    def created(self) -> bool:
        return self._path_on_disk is not None

    @property
    def parent(self) -> Path:
        """The folder the project folder is in, or will be created in."""
        return self.path.parent if self.created else self._parent

    @parent.setter
    def parent(self, value: Union[Path, str]) -> None:
        """Choose where `create` puts the project folder. Ignored once the project is on disk."""
        if not self.created:
            self._parent = Path(value).expanduser()

    @property
    def path(self) -> Path:
        return self._path_on_disk if self.created else self._parent / self.name

    @property
    def path_json(self) -> Path:
        return self.path / PROJECT_FILE_NAME

    # Persistence

    def as_dict(self) -> dict:
        # The location is not stored: it is wherever the file was read from, so a moved folder
        # stays valid.
        return {
            'file_format': FILE_FORMAT,
            'name': self.name,
            'description': self.description,
            'created': _to_iso(self.created_at),
            'modified': _to_iso(self.modified_at),
            'sample_name': self.sample_name,
            'calculations': list(self.calculations),
            'engine': self.engine.value,
            'status': self.status.value,
        }

    def _apply_dict(self, data: dict) -> None:
        """Set the state from `data`. Raises ValueError, KeyError or TypeError on a bad file."""
        file_format = data.get('file_format')
        if file_format != FILE_FORMAT:
            raise ValueError(f'Unsupported project file format {file_format!r}; this version reads format {FILE_FORMAT}.')
        self.name = str(data['name'])
        self.description = str(data.get('description', ''))
        self.created_at = _from_iso(data.get('created', ''))
        self.modified_at = _from_iso(data.get('modified', ''))
        self.sample_name = str(data.get('sample_name', ''))
        self.calculations = [str(item) for item in data.get('calculations', [])]
        self.engine = Engine(data.get('engine', Engine.NONE.value))
        self.status = ProjectStatus(data.get('status', ProjectStatus.NEW.value))

    def create(self) -> None:
        """Create the project folder and write ``project.json`` into it.

        :raises FileExistsError: if the folder already exists. Nothing is changed in that case.
        """
        path = self.path
        if path.exists():
            raise FileExistsError(f'Directory {path} already exists. Choose a different name or location.')
        path.mkdir(parents=True)
        self._path_on_disk = path
        self.created_at = _now()
        self.save()

    def save(self) -> None:
        """Write ``project.json``, stamping the modification time.

        :raises RuntimeError: if the project has not been created.
        :raises OSError: if the file cannot be written.
        """
        if not self.created:
            raise RuntimeError('No project has been created yet.')
        self.modified_at = _now()
        _write_atomically(self.path_json, json.dumps(self.as_dict(), indent=4))

    def load(self, path: Union[Path, str]) -> None:
        """Replace the state with the project at `path` (its folder or its ``project.json``).

        The current state is untouched if the file cannot be read or is not a project file.

        :raises FileNotFoundError: if there is no project file at `path`.
        :raises ValueError: if the file is not valid JSON or not a supported project file.
        """
        path_json = Path(path).expanduser()
        if path_json.is_dir():
            path_json = path_json / PROJECT_FILE_NAME
        with open(path_json, encoding='utf-8') as file:
            data = json.load(file)
        if not isinstance(data, dict):
            raise ValueError(f'{path_json} is not a project file.')
        loaded = Project()
        try:
            loaded._apply_dict(data)
        except (KeyError, TypeError) as error:
            raise ValueError(f'{path_json} is not a project file: {error}') from error
        self.__dict__.update(loaded.__dict__)
        self._path_on_disk = path_json.parent
