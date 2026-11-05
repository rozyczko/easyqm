# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""The workspace as the assistant sees and changes it (LLM_INTEG_DESIGN.md, sections 5–7).

One registry of settable fields (`METHOD_FIELDS`, `OPTION_FIELDS`) gives the snapshot, the
tool schemas and the validation, so the three cannot disagree. Everything here runs on the
main thread: `prepare` checks a tool call and returns either an `Outcome` (a read, or a
refusal) or an `Action` that the assistant runs, after the user's approval when its effect
needs one (`approval_needed`).
"""

import json
import math
import re
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Callable
from typing import Optional
from typing import Union

from .job import configuration
from .logic.calculations import CalculationType
from .logic.calculations import info
from .logic.elements import SYMBOLS
from .logic.method import describe
from .logic.sample import STRUCTURES_DIR
from .logic.zmatrix import FIELDS as ZMATRIX_FIELDS
from .sample import REPEAT_MAX
from .sample import SCENE_ATOM_LIMIT

PAGES = ('home', 'project', 'sample', 'calculations', 'method', 'summary')
EXAMPLES_DIR = Path(__file__).resolve().parents[4] / 'examples'  # in a source checkout only
STRUCTURE_SUFFIXES = ('.xyz', '.cif')

SNAPSHOT_ATOMS = 50
OUTPUT_TAIL_LINES = 60
LINE_CHARS = 400
OUTPUT_TAIL_CHARS = 8000
TOOL_OUTPUT_CHARS = 16000
MODES_SHOWN = 30
SAVED_SCOPE = ('Saved the project file. It holds the project metadata (name, description, sample summary, '
               'calculation names, engine, status), not the coordinates, options or method settings.')

# The approval modes in which an effect asks the user first. Reads and navigation never ask.
GATES = {
    'mutate': ('every',),
    'replace': ('default', 'every'),
    'persist': ('default', 'every'),
    'start': ('default', 'every'),
    'stop': ('every',),
}
# Tools that change the setup, refused while a job runs: the changes would not reach it.
_SETUP_TOOLS = ('load_structure', 'add_atom', 'remove_atoms', 'move_atoms', 'set_zmatrix_value', 'set_cell',
                'set_electronic_state', 'set_atoms_fixed', 'select_calculations', 'set_calculation_options',
                'set_method')
# A project name is also its folder name until the project is created.
_PROJECT_NAME = re.compile(r'[^\\/:*?"<>|\x00-\x1f]{1,100}')
DESCRIPTION_CHARS = 2000


@dataclass
class Outcome:
    """What a tool call did, as the model and the action rows are told."""

    status: str  # ok | changed | declined | failed | already_running | stale_state | cancelled
    text: str

    @property
    def is_error(self) -> bool:
        return self.status in ('failed', 'stale_state')


@dataclass
class Action:
    """A validated tool call that changes something, run later by the assistant."""

    tool: str
    effect: str  # a key of GATES
    title: str
    detail: list[str]
    run: Callable[[], Outcome]
    page: str = ''
    revisions: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Field:
    """A settable value: snapshot key and tool argument `name`, part property and setter."""

    name: str
    prop: str
    setter: str
    kind: str  # enum | int | float | bool | grid (three integers)
    choices: str = ''  # part property with [{value, label}], for an enum
    limits: tuple = ()
    unit: str = ''

    def schema(self) -> dict:
        if self.kind == 'grid':
            return {'type': 'array', 'items': {'type': 'integer'},
                    'description': f'Three integers from {self.limits[0]} to {self.limits[1]}.'}
        kind = {'enum': 'string', 'int': 'integer', 'float': 'number', 'bool': 'boolean'}[self.kind]
        if self.kind == 'enum':
            return {'type': kind, 'description': f'One of `{self.name}_choices` in the workspace state.'}
        if self.limits:
            return {'type': kind, 'description': f'From {self.limits[0]} to {self.limits[1]} {self.unit}'.strip() + '.'}
        return {'type': kind}

    def problem(self, part, value) -> str:
        """Why `value` cannot be set, or ''."""
        if self.kind == 'enum':
            allowed = [choice['value'] for choice in getattr(part, self.choices)]
            return '' if value in allowed else f'{self.name} must be one of {", ".join(allowed)}; got {value!r}.'
        if self.kind == 'bool':
            return '' if isinstance(value, bool) else f'{self.name} must be true or false.'
        if self.kind == 'grid':
            low, high = self.limits
            ok = isinstance(value, list) and len(value) == 3 and all(isinstance(n, int) and low <= n <= high for n in value)
            return '' if ok else f'{self.name} must be three integers from {low} to {high}.'
        number = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
        if not number or (self.kind == 'int' and not isinstance(value, int)) or not self.limits[0] <= value <= self.limits[1]:
            kind = 'an integer' if self.kind == 'int' else 'a number'
            return f'{self.name} must be {kind} from {self.limits[0]} to {self.limits[1]} {self.unit}'.strip() + '.'
        return ''


METHOD_FIELDS = (
    Field('family', 'family', 'setFamily', 'enum', 'familyChoices'),
    Field('functional', 'functional', 'setFunctional', 'enum', 'functionalChoices'),
    Field('dispersion', 'dispersion', 'setDispersion', 'enum', 'dispersionChoices'),
    Field('basis_set', 'basisSet', 'setBasisSet', 'enum', 'basisSetChoices'),
    Field('auxiliary_basis', 'auxiliaryBasis', 'setAuxiliaryBasis', 'enum', 'auxiliaryBasisChoices'),
    Field('reference', 'reference', 'setReference', 'enum', 'referenceChoices'),
    Field('solvation', 'solvation', 'setSolvation', 'enum', 'solvationChoices'),
    Field('occupations', 'occupations', 'setOccupations', 'enum', 'occupationsChoices'),
    Field('scf_convergence', 'scfConvergence', 'setScfConvergence', 'enum', 'scfConvergenceChoices'),
    Field('scf_max_iterations', 'scfMaxIterations', 'setScfMaxIterations', 'int', limits=(1, 1000)),
    Field('integration_grid', 'integrationGrid', 'setIntegrationGrid', 'enum', 'integrationGridChoices'),
    Field('stability_check', 'stabilityCheck', 'setStabilityCheck', 'bool'),
    Field('memory_gb', 'memoryGb', 'setMemoryGb', 'int', limits=(1, 1024), unit='GB'),
    Field('kpoint_spacing', 'kpointSpacing', 'setKpointSpacing', 'float', limits=(0.01, 2.0), unit='1/Å'),
    Field('kpoint_grid', 'kpointGrid', 'setKpointGrid', 'grid', limits=(1, 50)),
)
OPTION_FIELDS = {
    'single_point': (
        Field('print_orbitals', 'singlePointPrintOrbitals', 'setSinglePointPrintOrbitals', 'bool'),
        Field('geometry', 'singlePointGeometry', 'setSinglePointGeometry', 'enum', 'singlePointGeometryChoices'),
    ),
    'geometry_optimisation': (
        Field('convergence', 'optConvergence', 'setOptConvergence', 'enum', 'optConvergenceChoices'),
        Field('max_steps', 'optMaxSteps', 'setOptMaxSteps', 'int', limits=(1, 10000)),
        Field('optimise', 'optOptimise', 'setOptOptimise', 'enum', 'optOptimiseChoices'),
    ),
    'vibrational_frequencies': (
        Field('type', 'freqType', 'setFreqType', 'enum', 'freqTypeChoices'),
        Field('temperature', 'freqTemperature', 'setFreqTemperature', 'float', limits=(1, 5000), unit='K'),
        Field('pressure', 'freqPressure', 'setFreqPressure', 'float', limits=(0.001, 1000), unit='atm'),
        Field('raman', 'freqRaman', 'setFreqRaman', 'bool'),
    ),
}


# The API caps the strict tools of a request (20) and their optional parameters together (24).
# The two patch tools have more optional fields than that on their own, so they are not strict;
# `Workspace` checks every key and value of a patch anyway.
MAX_STRICT_TOOLS = 20
MAX_STRICT_OPTIONAL = 24


def _tool(name: str, description: str, properties: Optional[dict] = None, required=(), strict=True) -> dict:
    return {
        'name': name,
        'description': description,
        'strict': strict,
        'input_schema': {
            'type': 'object',
            'properties': properties or {},
            'required': list(required),
            'additionalProperties': False,
        },
    }


def _object(fields) -> dict:
    properties = {f.name: f.schema() for f in fields}
    return {'type': 'object', 'properties': properties, 'required': [], 'additionalProperties': False}


_INT = {'type': 'integer'}
_NUMBER = {'type': 'number'}
_INDICES = {'type': 'array', 'items': _INT, 'description': 'Zero-based atom indices `i`.'}
_REVISION = {'type': 'integer', 'description': 'The current `revisions.sample`.'}
_POSITION = {'type': 'array', 'items': _NUMBER, 'description': 'Three numbers.'}
_FRAME = {'type': 'string', 'enum': ['cartesian', 'fractional'],
          'description': 'cartesian: x, y, z in Å; fractional: in the cell, for a crystal only.'}
_MOVES = {'type': 'array', 'items': {'type': 'object', 'properties': {'index': _INT, 'position': _POSITION},
                                     'required': ['index', 'position'], 'additionalProperties': False}}
TOOLS = [
    _tool('get_workspace', 'Read the current workspace state again. Call it after several changes, or when a tool '
          'result says the workspace changed.'),
    _tool('get_atoms', 'Read atoms beyond the first ones in the workspace state: zero-based index i, element, '
          'Cartesian x y z in Å (fractional fx fy fz for a crystal), label, fixed. At most 100 per call.',
          {'offset': _INT, 'count': _INT}, ('offset', 'count')),
    _tool('get_job_output', 'Read the last lines of the engine output of the running or last job. Call it to explain '
          'a failure or to check progress. `contains` keeps only lines that contain this literal text.',
          {'lines': {'type': 'integer', 'description': 'From 1 to 200.'}, 'contains': {'type': 'string'}}, ('lines',)),
    _tool('show_page', 'Switch the application to a page, so that the user sees what you are talking about.',
          {'page': {'type': 'string', 'enum': list(PAGES)}}, ('page',)),
    _tool('load_structure', 'Replace the structure with one from a file: a packaged example listed in '
          '`sample.examples`, a file in the project folder, or a file the user loaded in this session. Pass the file '
          'name, e.g. "benzene.xyz". Charge and multiplicity go back to their defaults.',
          {'name': {'type': 'string'}}, ('name',)),
    _tool('add_atom', 'Add an atom after the others, as the Add atom button does, at the position given. It gets '
          'the next index and is selected. A multiplicity the new electron count does not allow goes to the lowest '
          'one it allows.',
          {'element': {'type': 'string', 'description': 'Element symbol, e.g. "O".'}, 'position': _POSITION,
           'coordinates': _FRAME}, ('element', 'position', 'coordinates')),
    _tool('remove_atoms', 'Remove atoms, as Remove selected does for exactly these atoms. Later atoms move up, so '
          'their indices drop. At least one atom must stay.',
          {'indices': _INDICES, 'sample_revision': _REVISION}, ('indices', 'sample_revision')),
    _tool('move_atoms', 'Move atoms, as editing the coordinate tables does: each move gives an atom index and its '
          'whole new position. A crystal\'s atoms are wrapped into the cell.',
          {'moves': _MOVES, 'coordinates': _FRAME, 'sample_revision': _REVISION},
          ('moves', 'coordinates', 'sample_revision')),
    _tool('set_zmatrix_value', 'Set a bond length (Å), bond angle or dihedral (°) of a molecule in its Z-matrix, as '
          'editing the Z-matrix table does. The tables must show the Z-matrix (set_view coordinates "zmatrix"); '
          '`sample.zmatrix` then lists its rows. The atom moves, and with it the atoms placed from it. Only values '
          'with a reference atom (`*_to` not null) can be set.',
          {'atom': {'type': 'integer', 'description': 'The `i` of a `sample.zmatrix` row.'},
           'field': {'type': 'string', 'enum': list(ZMATRIX_FIELDS)}, 'value': _NUMBER, 'sample_revision': _REVISION},
          ('atom', 'field', 'value', 'sample_revision')),
    _tool('set_cell', 'Change the unit cell of a crystal, as the cell fields do. Give all six parameters, repeating '
          'the current ones from `sample.cell` that stay. The atoms keep their fractional coordinates.',
          {name: {'type': 'number', 'description': unit} for name, unit in
           (('a', 'Å'), ('b', 'Å'), ('c', 'Å'), ('alpha', '°'), ('beta', '°'), ('gamma', '°'))},
          ('a', 'b', 'c', 'alpha', 'beta', 'gamma')),
    _tool('set_view', 'Change what the Sample page shows, and switch to it: the coordinates of the atom tables '
          '(`sample.view.coordinates_choices`), the cells drawn for a crystal, whether a crystal\'s atoms on the cell '
          'boundary are drawn, and the selected atoms (an empty list clears the selection). The structure does not '
          'change and the user is not asked.',
          {'coordinates': {'type': 'string', 'enum': ['cartesian', 'fractional', 'zmatrix']},
           'repeat': {'type': 'array', 'items': _INT,
                      'description': f'Cells drawn along a, b, c: three integers from 1 to {REPEAT_MAX}.'},
           'boundary_atoms': {'type': 'boolean'}, 'selected': _INDICES}),
    _tool('set_project_details', 'Change the project name, description or autosave, as the Project page does. '
          'Before the project is created the name is also its folder name. With autosave on, each change is '
          'written to the project file at once.',
          {'name': {'type': 'string'}, 'description': {'type': 'string'}, 'autosave': {'type': 'boolean'}}),
    _tool('set_electronic_state', 'Set the charge and/or the spin multiplicity of the sample. The multiplicity must '
          'be one the electron count allows; above 1 the method reference must be open-shell (set_method first).',
          {'charge': _INT, 'multiplicity': _INT}),
    _tool('set_atoms_fixed', 'Fix atoms in place for a geometry optimisation, or free them. Indices are the '
          'zero-based `i` of the atom lists; pass the current `revisions.sample` as sample_revision.',
          {'indices': {'type': 'array', 'items': _INT}, 'fixed': {'type': 'boolean'}, 'sample_revision': _INT},
          ('indices', 'fixed', 'sample_revision')),
    _tool('select_calculations', 'Choose the calculations the workflow runs: replace the selection, or add or '
          'remove types.',
          {'types': {'type': 'array', 'items': {'type': 'string', 'enum': [t.value for t in CalculationType]}},
           'mode': {'type': 'string', 'enum': ['replace', 'add', 'remove']}}, ('types', 'mode')),
    _tool('set_calculation_options', 'Change options of the calculations. Only the fields given change, and only if '
          'all of them are valid.', {group: _object(fields) for group, fields in OPTION_FIELDS.items()},
          strict=False),
    _tool('set_method', 'Change the level of theory, SCF and run settings of the active engine. Only fields shown in '
          'the workspace `method` state apply to it. Only the fields given change, and only if all of them are valid. '
          'Give kpoint_spacing or kpoint_grid, not both.', {f.name: f.schema() for f in METHOD_FIELDS},
          strict=False),
    _tool('run_workflow', 'Start the selected calculations with the active engine. The user confirms in the '
          'application first. Do not call it while a job runs.'),
    _tool('stop_job', 'Stop the running job.'),
    _tool('save_project', 'Save the project file. It stores the project metadata only (name, description, sample '
          'summary, calculation names, engine, status), not coordinates, options or method settings.'),
]
TOOL_NAMES = tuple(tool['name'] for tool in TOOLS)


class Workspace:
    """The backend parts as one workspace, for the assistant."""

    def __init__(self, project, sample, calculations, method, job, results):
        self._project, self._sample, self._calculations = project, sample, calculations
        self._method, self._job, self._results = method, job, results
        self.page = 'home'  # the page the user looks at, set by the assistant panel
        self.navigate: Callable[[str], None] = lambda page: None  # switches the page; set by the assistant
        self.send_output = True  # engine output and its messages may go to the model
        self.send_results = True
        # One counter per part, raised on every change: approvals and atom indices refer to them.
        self.revisions = dict.fromkeys(('project', 'sample', 'calculations', 'method'), 0)
        self._loaded_revision = 0  # the sample's revision right after its last load
        changes = {
            'project': (project.createdChanged, project.locationChanged),
            'sample': (sample.sampleChanged, sample.atomsChanged, sample.electronicStateChanged),
            'calculations': (calculations.selectionChanged, calculations.singlePointChanged,
                             calculations.optimisationChanged, calculations.frequenciesChanged),
            'method': (method.engineChanged, method.levelOfTheoryChanged, method.systemChanged, method.scfChanged,
                       method.runSettingsChanged, method.kpointsChanged),
        }
        for part, signals in changes.items():
            for signal in signals:
                signal.connect(lambda part=part: self._changed(part))
        sample.structureLoaded.connect(self._structure_loaded)

    def _changed(self, part: str) -> None:
        self.revisions[part] += 1

    def _structure_loaded(self) -> None:
        self._loaded_revision = self.revisions['sample']

    # What the model sees

    def snapshot(self) -> tuple[dict, dict]:
        """(facts, data): application state, and the strings that came from files, the user or an
        engine. Facts go to the model as operator state, data as information only."""
        sample, method, job, project = self._sample, self._method, self._job, self._project
        rows = sample.atoms
        record = job.record
        facts = {
            'page': self.page,
            'revisions': dict(self.revisions),
            'project': {'created': project.created, 'autosave': project.autoSave,
                        'unsaved_changes': project.hasUnsavedChanges, 'status': project.status},
            'sample': {
                'formula': sample.formula,
                'atom_count': sample.atomCount,
                'periodic': sample.periodic,
                'point_group': sample.pointGroup,
                'charge': sample.charge,
                'multiplicity': sample.multiplicity,
                'multiplicity_choices': [choice['value'] for choice in sample.multiplicityChoices],
                'fixed_atoms': sample.fixedCount,
                'edited_since_load': self.revisions['sample'] > self._loaded_revision,
                'units': 'Å, degrees',
                'selected': [{'index': index, 'image': list(image)} for index, image in sample.selection],
                'atoms': {'items': [_atom(i, row, sample.periodic) for i, row in enumerate(rows[:SNAPSHOT_ATOMS])],
                          'total': len(rows), 'offset': 0, 'truncated': len(rows) > SNAPSHOT_ATOMS},
                'cell': {key: value for key, value in sample.cell.items() if key != 'vectors'} or None,
                'view': self._view_facts(),
                'examples': sorted({path.name for path in self._examples()}),
            },
            'calculations': {
                'selected': [step.value for step in self._calculations.logic.workflow()],
                'available': [t.value for t in CalculationType],
                'workflow': [step['label'] for step in self._calculations.workflow],
                'options': {group: _state(self._calculations, fields) for group, fields in OPTION_FIELDS.items()},
            },
            'method': {
                'engine': {'name': method.engineName, 'found': method.engineFound, 'version': method.engineVersion,
                           'can_run': method.canRun, 'cannot_run_reason': method.cannotRunReason},
                'engines': [{key: card[key] for key in ('name', 'active', 'found', 'problem')} for card in method.engines],
                **_state(method, [f for f in METHOD_FIELDS if not self._method_problem(f)]),
            },
            'job': {
                'state': job.state,
                'last_run': record['run_id'] if record else None,
                'running': {key: record[key] for key in ('run_id', 'engine', 'method', 'calculations')}
                if job.running and record else None,
                'next_run_destination': 'project folder' if project.created else 'scratch folder (no project open)',
            },
            'results': self._results_facts(record) if self.send_results else {'shared': False},
        }
        data = {
            'project_name': project.name,
            'project_description': project.description,
            'structure_file': sample.source,
            'atom_labels': [row['label'] for row in rows[:SNAPSHOT_ATOMS]],
            'run_folder': _home(record['folder']) if record else '',
        }
        if self.send_output:
            data['job_message'] = job.message
            lines = job.tail(OUTPUT_TAIL_CHARS * 2).splitlines()[-OUTPUT_TAIL_LINES:]
            data['output_tail'] = '\n'.join(line[:LINE_CHARS] for line in lines)[-OUTPUT_TAIL_CHARS:]
        return facts, {key: value for key, value in data.items() if value}

    def _view_facts(self) -> dict:
        sample = self._sample
        view = {'coordinates': sample.coordinates, 'coordinates_choices': list(sample.coordinate_choices)}
        if sample.periodic:
            view.update(repeat=sample.viewRepeat, boundary_atoms=sample.viewBoundaryAtoms)
        if sample.coordinates == 'zmatrix':
            rows = sample.zmatrix_rows()
            items = [{'i': row.atom, **{key: value for field, reference, value in zip(ZMATRIX_FIELDS, row.references,
                                                                                    row.values)
                                        for key, value in ((f'{field}_to', reference), (field, round(value, 4)))}}
                     for row in rows[:SNAPSHOT_ATOMS]]
            view['zmatrix'] = ({'items': items, 'total': len(rows), 'truncated': len(rows) > SNAPSHOT_ATOMS}
                               if rows else {'error': sample.zmatrixError})
        return view

    def brief(self) -> dict:
        """The few facts the offline suggestions depend on; cheap enough to build on every change."""
        return {'page': self.page, 'job': {'state': self._job.state}, 'results': {'available': self._results.available}}

    def _results_facts(self, record: Optional[dict]) -> dict:
        results = self._results
        if not results.available or record is None:
            return {'available': False}
        current = self._configuration()
        stale = [f'{part} changed since the run'
                 for part, digest in record['configuration'].items() if current[part] != digest]
        modes = results.modes
        return {
            'available': True,
            'run_id': record['run_id'],
            'job_state': self._job.state,
            'matches_current_state': not stale,
            'stale_reasons': stale,
            'geometry_applied': record['geometry_applied'],
            'tiles': [{key: tile[key] for key in ('title', 'value', 'detail')} for tile in results.tiles],
            'modes': {'items': [{'number': m['number'], 'frequency_cm1': m['frequency'], 'ir': m['irText'],
                                 'raman': m['ramanText']} for m in modes[:MODES_SHOWN]],
                      'total': len(modes)},
        }

    def _configuration(self) -> dict:
        return configuration(self._sample.logic, self._calculations.logic, self._method.logic, self._method.run_settings)

    def _examples(self) -> list[Path]:
        folders = [STRUCTURES_DIR, EXAMPLES_DIR / 'XYZ', EXAMPLES_DIR / 'CIF']
        return [path for folder in folders if folder.is_dir() for path in folder.iterdir()
                if path.suffix.lower() in STRUCTURE_SUFFIXES]

    def _method_problem(self, f: Field, family: str = '') -> str:
        """Why the active engine does not use this method field, or ''."""
        method = self._method
        family = family or method.family
        if f.choices and not getattr(method, f.choices):
            return f'{method.engineName} has no {f.name} setting.'
        if family == 'HF' and f.name in ('functional', 'dispersion'):
            return f'{f.name} is not used by Hartree–Fock.'
        if f.name == 'stability_check' and not method.stabilityCheckOffered:
            return f'{method.engineName} offers no stability check.'
        if f.name == 'memory_gb' and not method.adapter.uses_memory:
            return f'{method.engineName} does not use the memory setting.'
        if f.name.startswith('kpoint') and not method.periodic:
            return 'K-points apply to crystals only.'
        return ''

    # Tool calls

    def prepare(self, name: str, args: dict) -> Union[Outcome, Action]:
        """Check a tool call. A read or navigation is done at once and its `Outcome` returned;
        a change comes back as an `Action` to run, or as the `Outcome` that refuses it."""
        if name not in TOOL_NAMES:
            return Outcome('failed', f'There is no tool {name!r}.')
        if name in _SETUP_TOOLS and self._job.running:
            return Outcome('failed', 'A job is running; changes would only apply to the next run. Wait for it or stop it.')
        try:
            prepared = getattr(self, f'_tool_{name}')(**args)
        except TypeError as error:
            return Outcome('failed', f'Bad arguments for {name}: {error}')
        if isinstance(prepared, Action):
            prepared.revisions = dict(self.revisions)
        return prepared

    @staticmethod
    def approval_needed(action: Action, mode: str) -> bool:
        return mode in GATES.get(action.effect, ())

    def changed_since(self, action: Action) -> list[str]:
        """The parts that changed since the action was prepared."""
        return [part for part, revision in action.revisions.items() if self.revisions[part] != revision]

    # Reads

    def _tool_get_workspace(self) -> Outcome:
        facts, data = self.snapshot()
        return Outcome('ok', facts_text(facts) + '\n' + data_text(data))

    def _tool_get_atoms(self, offset: int, count: int) -> Outcome:
        rows = self._sample.atoms
        if not (isinstance(offset, int) and isinstance(count, int) and offset >= 0 and 1 <= count <= 100):
            return Outcome('failed', 'offset must be 0 or more and count from 1 to 100.')
        periodic = self._sample.periodic
        items = [{**_atom(i, row, periodic), 'label': row['label']}
                 for i, row in enumerate(rows[offset:offset + count], start=offset)]
        envelope = {'items': items, 'total': len(rows), 'offset': offset, 'truncated': offset + count < len(rows),
                    'sample_revision': self.revisions['sample']}
        return Outcome('ok', json.dumps(envelope, ensure_ascii=False))

    def _tool_get_job_output(self, lines: int, contains: str = '') -> Outcome:
        if not self.send_output:
            return Outcome('failed', 'The user has turned off sharing engine output with the assistant.')
        if not isinstance(lines, int) or not 1 <= lines <= 200:
            return Outcome('failed', 'lines must be from 1 to 200.')
        text = self._job.output if contains else self._job.tail(TOOL_OUTPUT_CHARS * 4)
        chosen = [line[:LINE_CHARS] for line in text.splitlines() if contains in line][-lines:]
        return Outcome('ok', '\n'.join(chosen)[-TOOL_OUTPUT_CHARS:] or '(no matching output)')

    def _tool_show_page(self, page: str) -> Outcome:
        if page not in PAGES:
            return Outcome('failed', f'page must be one of {", ".join(PAGES)}.')
        self.navigate(page)
        return Outcome('ok' if self.page == page else 'failed', f'The {self.page} page is shown.')

    # Changes

    def _tool_load_structure(self, name: str) -> Union[Outcome, Action]:
        path = self._resolve(name)
        if path is None:
            examples = ', '.join(sorted({p.name for p in self._examples()}))
            return Outcome('failed', f'{name!r} is not a packaged example, a file in the project folder or a file the '
                                     f'user loaded in this session. Examples: {examples}. Other files: ask the user to '
                                     'load them with "Load structure from file" on the Sample page.')
        sample = self._sample
        edited = self.revisions['sample'] > self._loaded_revision

        def run() -> Outcome:
            charge, multiplicity = sample.charge, sample.multiplicity
            error = sample.load_file(path)
            if error:
                return Outcome('failed', f'{path.name} could not be read: {_redact(error)}')
            kind = 'crystal' if sample.periodic else 'molecule'
            symmetry = f', {sample.pointGroup}' if sample.pointGroup else ''
            return Outcome('changed', f'Loaded {path.name}: {sample.formula}, {sample.atomCount} atoms, {kind}{symmetry}; '
                                      f'charge {charge:+d} → {sample.charge:+d}, multiplicity {multiplicity} → '
                                      f'{sample.multiplicity}; sample revision {self.revisions["sample"]}.')

        detail = ['Replaces the current structure, which was edited since it was loaded.' if edited
                  else 'Replaces the current structure.']
        return Action('load_structure', 'replace' if edited else 'mutate', f'Load {path.name}', detail, run, 'sample')

    def _resolve(self, name: str) -> Optional[Path]:
        """The file `name` refers to, if the assistant may read it: a packaged example, a file in
        the project folder, or a file the user picked this session."""
        candidate = Path(name)
        for picked in self._sample.picked_paths:
            if picked.name == name or (candidate.is_absolute() and candidate.resolve() == picked):
                return picked
        if candidate.suffix.lower() not in STRUCTURE_SUFFIXES:
            return None
        roots = [STRUCTURES_DIR, EXAMPLES_DIR / 'XYZ', EXAMPLES_DIR / 'CIF']
        if self._project.created:
            roots.append(Path(self._project.location))
        for root in (root.resolve() for root in roots if root.is_dir()):
            path = (root / candidate).resolve()
            if path.is_file() and path.is_relative_to(root):
                return path
        return None

    def _tool_set_electronic_state(self, charge: Optional[int] = None, multiplicity: Optional[int] = None):
        sample, logic = self._sample, self._sample.logic
        if not all(value is None or _integer(value) for value in (charge, multiplicity)):
            return Outcome('failed', 'charge and multiplicity must be integers.')
        charge = logic.charge if charge is None else charge
        if multiplicity is None:
            allowed = logic.multiplicities(charge)
            multiplicity = logic.multiplicity if logic.multiplicity in allowed or not allowed else allowed[0]
        problem = logic.electronic_state_problem(charge, multiplicity)
        if not problem and multiplicity > 1 and self._method.reference == 'RKS':
            problem = f'Multiplicity {multiplicity} needs an open-shell reference: set_method reference first.'
        if problem:
            return Outcome('failed', problem)
        before = (sample.charge, sample.multiplicity)

        def run() -> Outcome:
            sample.set_electronic_state(charge, multiplicity)
            return Outcome('changed', f'charge {before[0]:+d} → {charge:+d}, multiplicity {before[1]} → {multiplicity}.')

        return Action('set_electronic_state', 'mutate', 'Change the electronic state',
                      [f'Charge {charge:+d}, multiplicity {multiplicity}'], run, 'sample')

    def _tool_set_atoms_fixed(self, indices: list, fixed: bool, sample_revision: int):
        problem = self._stale(sample_revision) or self._indices_problem(indices, at_least_one=True)
        if problem:
            return problem

        def run() -> Outcome:
            changed = self._sample.set_atoms_fixed(indices, bool(fixed))
            verb = 'Fixed' if fixed else 'Freed'
            return Outcome('changed' if changed else 'ok', f'{verb} atoms {changed}; the others are as they were.'
                           if changed else f'Atoms {sorted(set(indices))} were already {"fixed" if fixed else "free"}.')

        return Action('set_atoms_fixed', 'mutate', f'{"Fix" if fixed else "Free"} atoms', [f'Atoms {sorted(set(indices))}'],
                      run, 'sample')

    def _stale(self, sample_revision) -> Optional[Outcome]:
        """The refusal of a call made for another revision of the structure, or None."""
        revision = self.revisions['sample']
        if sample_revision != revision:
            return Outcome('stale_state', f'The structure changed (revision {revision}); read the atoms again.')
        return None

    def _indices_problem(self, indices, at_least_one: bool = False) -> Optional[Outcome]:
        count = self._sample.atomCount
        if isinstance(indices, list) and (indices or not at_least_one) and \
                all(_integer(i) and 0 <= i < count for i in indices):
            return None
        some = 'a non-empty list' if at_least_one else 'a list'
        return Outcome('failed', f'indices must be {some} of atom indices from 0 to {count - 1}.')

    def _position_problem(self, position, coordinates) -> Optional[Outcome]:
        if not (isinstance(position, list) and len(position) == 3 and all(map(_finite, position))):
            return Outcome('failed', 'A position is three numbers.')
        if coordinates == 'cartesian' or (coordinates == 'fractional' and self._sample.periodic):
            return None
        return Outcome('failed', 'coordinates must be cartesian or, for a crystal, fractional.')

    def _sample_text(self) -> str:
        sample = self._sample
        return (f'{sample.formula}, {sample.atomCount} atoms, multiplicity {sample.multiplicity}; '
                f'sample revision {self.revisions["sample"]}.')

    def _tool_add_atom(self, element: str, position: list, coordinates: str):
        if element not in SYMBOLS:
            return Outcome('failed', f'{element!r} is not an element symbol.')
        problem = self._position_problem(position, coordinates)
        if problem:
            return problem
        sample = self._sample

        def run() -> Outcome:
            index = sample.add_atom(element, position, coordinates == 'fractional')
            return Outcome('changed', f'Added {element} as atom {index}, selected. Now {self._sample_text()}')

        return Action('add_atom', 'mutate', f'Add a {element} atom', [f'At {_xyz(position)} ({coordinates})'], run,
                      'sample')

    def _tool_remove_atoms(self, indices: list, sample_revision: int):
        problem = self._stale(sample_revision) or self._indices_problem(indices, at_least_one=True)
        if problem:
            return problem
        sample, removed = self._sample, sorted(set(indices))
        if len(removed) >= sample.atomCount:
            return Outcome('failed', 'A structure needs at least one atom.')
        rows = sample.atoms

        def run() -> Outcome:
            sample.remove_atoms(removed)
            return Outcome('changed', f'Removed atoms {removed}; later atoms moved up. Now {self._sample_text()}')

        return Action('remove_atoms', 'mutate', 'Remove atoms', [', '.join(f'{rows[i]["element"]} {i}' for i in removed)],
                      run, 'sample')

    def _tool_move_atoms(self, moves: list, coordinates: str, sample_revision: int):
        if not (isinstance(moves, list) and moves and all(isinstance(m, dict) and set(m) == {'index', 'position'}
                                                          for m in moves)):
            return Outcome('failed', 'moves must be a non-empty list of {index, position}.')
        indices = [m['index'] for m in moves]
        problem = self._stale(sample_revision) or self._indices_problem(indices) or next(
            filter(None, (self._position_problem(m['position'], coordinates) for m in moves)), None)
        if problem:
            return problem
        if len(set(indices)) < len(indices):
            return Outcome('failed', 'Each atom moves at most once per call.')
        positions, sample = {m['index']: m['position'] for m in moves}, self._sample

        def run() -> Outcome:
            sample.set_atom_positions(positions, coordinates == 'fractional')
            return Outcome('changed', f'Moved atoms {sorted(positions)}. Now {self._sample_text()}')

        detail = [f'Atom {index} to {_xyz(position)}' for index, position in positions.items()]
        if len(detail) > 10:
            detail = detail[:10] + [f'and {len(detail) - 10} more']
        return Action('move_atoms', 'mutate', f'Move atoms ({coordinates})', detail, run, 'sample')

    def _tool_set_zmatrix_value(self, atom: int, field: str, value: float, sample_revision: int):
        sample = self._sample
        stale = self._stale(sample_revision)
        if stale:
            return stale
        if sample.coordinates != 'zmatrix':
            return Outcome('failed', 'The tables do not show the Z-matrix: call set_view with coordinates "zmatrix" '
                                     'first (molecules only).')
        rows = {row.atom: row for row in sample.zmatrix_rows()}
        if not rows:
            return Outcome('failed', sample.zmatrixError or 'There is no Z-matrix.')
        if not (_integer(atom) and atom in rows and field in ZMATRIX_FIELDS and _finite(value)):
            return Outcome('failed', f'atom must be the i of a sample.zmatrix row, field one of '
                                     f'{", ".join(ZMATRIX_FIELDS)}, value a number.')
        row = rows[atom]
        if row.reference(field) is None:
            return Outcome('failed', f'The {field} of atom {atom} is measured to the origin or an axis, not to another '
                                     'atom; it cannot be set.')
        change = f'{field} {round(row.value(field), 4):g} → {value:g} {"Å" if field == "bond" else "°"}'

        def run() -> Outcome:
            try:
                sample.set_zmatrix_value(atom, field, float(value))
            except ValueError as error:
                return Outcome('failed', f'Nothing changed: {error}')
            return Outcome('changed', f'Atom {atom}: {change}; the atoms placed from it moved with it. '
                                      f'Now {self._sample_text()}')

        return Action('set_zmatrix_value', 'mutate', f'Set a Z-matrix {field}', [f'Atom {atom}: {change}'], run,
                      'sample')

    def _tool_set_cell(self, a: float, b: float, c: float, alpha: float, beta: float, gamma: float):
        sample, parameters = self._sample, {'a': a, 'b': b, 'c': c, 'alpha': alpha, 'beta': beta, 'gamma': gamma}
        if not sample.periodic:
            return Outcome('failed', 'A molecule has no unit cell.')
        if not all(map(_finite, parameters.values())):
            return Outcome('failed', 'The cell parameters must be numbers.')
        try:
            sample.logic.cell.with_parameters(**parameters)
        except ValueError as error:
            return Outcome('failed', f'Nothing changed: {error}')
        text = f'a, b, c = {a:g}, {b:g}, {c:g} Å; alpha, beta, gamma = {alpha:g}, {beta:g}, {gamma:g}°'

        def run() -> Outcome:
            sample.set_cell_parameters(parameters)
            return Outcome('changed', f'Cell {text}; the atoms kept their fractional coordinates. '
                                      f'Now {self._sample_text()}')

        return Action('set_cell', 'mutate', 'Change the unit cell', [text], run, 'sample')

    def _tool_set_view(self, coordinates: Optional[str] = None, repeat: Optional[list] = None,
                       boundary_atoms: Optional[bool] = None, selected: Optional[list] = None) -> Outcome:
        sample, problems = self._sample, []
        if coordinates is not None and coordinates not in sample.coordinate_choices:
            problems.append(f'coordinates must be one of {", ".join(sample.coordinate_choices)}.')
        if not sample.periodic and (repeat is not None or boundary_atoms is not None):
            problems.append('repeat and boundary_atoms apply to crystals only.')
        if sample.periodic and repeat is not None:
            if not (isinstance(repeat, list) and len(repeat) == 3 and all(_integer(n) and 1 <= n <= REPEAT_MAX
                                                                         for n in repeat)):
                problems.append(f'repeat must be three integers from 1 to {REPEAT_MAX}.')
            elif sample.atomCount * math.prod(repeat) > SCENE_ATOM_LIMIT:
                problems.append(f'These cells would draw more than {SCENE_ATOM_LIMIT} atoms.')
        if boundary_atoms is not None and not isinstance(boundary_atoms, bool):
            problems.append('boundary_atoms must be true or false.')
        if selected is not None and self._indices_problem(selected):
            problems.append(self._indices_problem(selected).text)
        if problems:
            return Outcome('failed', 'Nothing changed: ' + ' '.join(problems))
        if (coordinates, repeat, boundary_atoms, selected) == (None, None, None, None):
            return Outcome('failed', 'Nothing to change.')
        if coordinates is not None:
            sample.setCoordinates(coordinates)
        if repeat is not None:
            sample.setViewRepeat(*repeat)
        if boundary_atoms is not None:
            sample.setViewBoundaryAtoms(boundary_atoms)
        if selected is not None:
            sample.select_atoms(selected)
        self.navigate('sample')
        texts = [f'coordinates {sample.coordinates}', f'selected atoms {sample.selectedAtoms}']
        if sample.periodic:
            texts.insert(1, f'{"×".join(map(str, sample.viewRepeat))} cells')
        if sample.coordinates == 'zmatrix':
            texts.append(f'{len(sample.zmatrix_rows())} Z-matrix rows, read them with get_workspace'
                         if sample.zmatrix_rows() else sample.zmatrixError)
        return Outcome('changed', f'The {self.page} page is shown with ' + '; '.join(texts) + '.')

    def _tool_set_project_details(self, name: Optional[str] = None, description: Optional[str] = None,
                                  autosave: Optional[bool] = None):
        project, problems = self._project, []
        if name is not None and not (isinstance(name, str) and _PROJECT_NAME.fullmatch(name) and name == name.strip()
                                     and not name.endswith('.')):
            problems.append('name must be 1 to 100 characters that a folder name allows (none of \\ / : * ? " < > |), '
                            'without leading or trailing spaces or a trailing dot.')
        if description is not None and not (isinstance(description, str) and len(description) <= DESCRIPTION_CHARS):
            problems.append(f'description must be text of at most {DESCRIPTION_CHARS} characters.')
        if autosave is not None and not isinstance(autosave, bool):
            problems.append('autosave must be true or false.')
        if problems:
            return Outcome('failed', 'Nothing changed: ' + ' '.join(problems))
        changes = {key: value for key, value in (('name', name), ('description', description), ('autosave', autosave))
                   if value is not None}
        if not changes:
            return Outcome('failed', 'Nothing to change.')
        # Turning autosave on writes the unsaved changes of a created project.
        writes = autosave is True and not project.autoSave and project.created

        def run() -> Outcome:
            if name is not None:
                project.setName(name)
            if description is not None:
                project.setDescription(description)
            if autosave is not None:
                project.setAutoSave(autosave)
            return Outcome('changed', f'Changed the project {", ".join(changes)}.')

        detail = [f'{key.capitalize()}: {value}' for key, value in changes.items()]
        return Action('set_project_details', 'persist' if writes else 'mutate', 'Change project details', detail,
                      run, 'project')

    def _tool_select_calculations(self, types: list, mode: str):
        valid = {t.value for t in CalculationType}
        if mode not in ('replace', 'add', 'remove') or not all(t in valid for t in types):
            return Outcome('failed', f'types must be among {", ".join(sorted(valid))}; mode replace, add or remove.')
        current, requested = set(self._calculations.logic.selected), {CalculationType(t) for t in types}
        selection = {'replace': requested, 'add': current | requested, 'remove': current - requested}[mode]
        names = [info(t).name for t in CalculationType if t in selection]

        def run() -> Outcome:
            self._calculations.set_selection(selection)
            return Outcome('changed', f'Selected: {", ".join(names) or "nothing"}.')

        return Action('select_calculations', 'mutate', 'Select calculations', [', '.join(names) or 'Nothing'], run,
                      'calculations')

    def _tool_set_calculation_options(self, **groups):
        calculations, problems, changes = self._calculations, [], []
        for group, values in groups.items():
            fields = {f.name: f for f in OPTION_FIELDS.get(group, ())}
            if not fields or not isinstance(values, dict) or not set(values) <= set(fields):
                return Outcome('failed', f'Unknown options in {group}.')
            proposed = {name: getattr(calculations, f.prop) for name, f in fields.items()} | values
            problems += [fields[name].problem(calculations, value) for name, value in values.items()]
            problems.append(self._option_problem(group, proposed))
            changes += [(fields[name], value) for name, value in values.items()]
        return self._set_fields('set_calculation_options', calculations, changes, problems,
                                'Change calculation options', 'calculations')

    def _option_problem(self, group: str, proposed: dict) -> str:
        """Option combinations the engine would ignore or reject."""
        if group == 'geometry_optimisation' and proposed['optimise'] == 'positions_and_cell' and not self._sample.periodic:
            return 'Optimising the cell needs a crystal.'
        if group == 'vibrational_frequencies' and proposed['raman']:
            if self._method.adapter.name == 'Quantum ESPRESSO':
                return 'Quantum ESPRESSO does not compute Raman activities here.'
            if proposed['type'] != 'numerical':
                return 'Raman activities need type numerical.'
        return ''

    def _tool_set_method(self, **values):
        method, by_name = self._method, {f.name: f for f in METHOD_FIELDS}
        if not set(values) <= set(by_name):
            return Outcome('failed', f'Unknown method fields: {", ".join(sorted(set(values) - set(by_name)))}.')
        family = values.get('family', method.family)
        problems = [by_name[name].problem(method, value) or self._method_problem(by_name[name], family)
                    for name, value in values.items()]
        if values.get('reference') == 'RKS' and self._sample.multiplicity > 1:
            problems.append(f'Multiplicity {self._sample.multiplicity} needs an open-shell reference, not RKS.')
        if 'kpoint_spacing' in values and 'kpoint_grid' in values:
            problems.append('Give kpoint_spacing or kpoint_grid, not both.')
        changes = [(f, values[f.name]) for f in METHOD_FIELDS if f.name in values]  # family first
        return self._set_fields('set_method', method, changes, problems, 'Change the method', 'method')

    @staticmethod
    def _set_fields(tool: str, part, changes: list, problems: list, title: str, page: str) -> Union[Outcome, Action]:
        """All of `changes` ((Field, value) pairs) as one action, or the refusal of all of them."""
        problems = [problem for problem in problems if problem]
        if problems:
            return Outcome('failed', 'Nothing changed: ' + ' '.join(problems))
        if not changes:
            return Outcome('failed', 'Nothing to change.')

        def run() -> Outcome:
            texts = []
            for f, value in changes:
                before = getattr(part, f.prop)
                if before != value:
                    setter = getattr(part, f.setter)
                    setter(*value) if f.kind == 'grid' else setter(value)
                    texts.append(f'{f.name}: {before} → {value}')
            return Outcome('changed', '; '.join(texts) + '.') if texts else Outcome('ok', 'Already set.')

        return Action(tool, 'mutate', title, [f'{f.name} = {value}' for f, value in changes], run, page)

    def _tool_run_workflow(self):
        job, method, sample = self._job, self._method, self._sample
        if job.running:
            return Outcome('already_running', f'Run {job.record["run_id"]} is running.')
        problem = ('' if method.engineFound else f'{method.engineName} was not found on this machine.') \
            or method.cannotRunReason or job.preflight()
        if problem:
            return Outcome('failed', problem)
        destination = 'project folder' if self._project.created else 'scratch folder, no project is open'
        detail = [
            f'{method.engineName} {method.engineVersion}'.strip(),
            ' → '.join(step['label'] for step in self._calculations.workflow),
            describe(method.logic, method.adapter.capabilities()),
            f'{sample.formula}, {sample.atomCount} atoms, charge {sample.charge:+d}, multiplicity {sample.multiplicity}',
            f'Into {_home(job.runs_root)} ({destination})',
        ]

        def run() -> Outcome:
            job.run()
            if not job.running:
                return Outcome('failed', f'The job did not start: {job.message}')
            record = job.record
            return Outcome('changed', f'Started run {record["run_id"]} in {_home(record["folder"])}; it is running.')

        return Action('run_workflow', 'start', 'Run the workflow', detail, run, 'method')

    def _tool_stop_job(self):
        job = self._job
        if not job.running:
            return Outcome('failed', 'No job is running.')

        def run() -> Outcome:
            run_id = job.record['run_id']
            job.stop()
            return Outcome('changed', f'Stopped run {run_id}; state {job.state}.')

        return Action('stop_job', 'stop', 'Stop the job', [f'Run {job.record["run_id"]}'], run, 'method')

    def _tool_save_project(self):
        project = self._project
        if not project.created:
            return Outcome('failed', 'No project is open. Ask the user to create one on the Project page.')

        def run() -> Outcome:
            errors = []
            handler = errors.append
            project.projectSaveError.connect(handler)
            try:
                project.save()
            finally:
                project.projectSaveError.disconnect(handler)
            return Outcome('failed', f'Saving failed: {errors[0]}') if errors else Outcome('changed', SAVED_SCOPE)

        return Action('save_project', 'persist', 'Save the project', [_home(project.location)], run, 'project')


def facts_text(facts: dict) -> str:
    return 'Current EasyQM workspace (application state):\n' + json.dumps(facts, sort_keys=True, ensure_ascii=False)


def data_text(data: dict) -> str:
    return '<data origin="workspace">\n' + json.dumps(data, sort_keys=True, ensure_ascii=False) + '\n</data>'


def _state(part, fields) -> dict:
    """Value, and choices for an enum, of each field."""
    state = {}
    for f in fields:
        state[f.name] = getattr(part, f.prop)
        if f.kind == 'enum':
            state[f'{f.name}_choices'] = [choice['value'] for choice in getattr(part, f.choices)]
    return state


def _integer(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _finite(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _xyz(position) -> str:
    return '(' + ', '.join(f'{value:g}' for value in position) + ')'


def _atom(index: int, row: dict, periodic: bool) -> dict:
    atom = {'i': index, 'element': row['element'], 'x': row['x'], 'y': row['y'], 'z': row['z'], 'fixed': row['fixed']}
    if periodic:
        atom.update(fx=row['fx'], fy=row['fy'], fz=row['fz'])
    return atom


def _home(path) -> str:
    """A path with the home folder as '~', so that the user name does not leave the machine."""
    # Resolved, so that Windows short names (C:\Users\ABCDEF~1) are recognised too.
    text, home = str(Path(path).resolve()), str(Path.home().resolve())
    return '~' + text[len(home):] if text.lower().startswith(home.lower()) else text


def _redact(error: str) -> str:
    """An error without the quoted file content some parse errors carry."""
    return re.sub(r'"[^"]*"', '"…"', error)
