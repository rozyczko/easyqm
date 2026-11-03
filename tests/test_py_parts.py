# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Proxies of the Sample, Calculations and Method parts, and their relays in PyBackend."""

import json
import math
import re
import sys
import time
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtCore import QUrl

from Backends.Py.calculations import Calculations
from Backends.Py.job import Job
from Backends.Py.logic.calculations import CalculationType
from Backends.Py.logic.engines.base import Capabilities
from Backends.Py.logic.engines.base import EngineAdapter
from Backends.Py.logic.engines.base import EngineInfo
from Backends.Py.logic.engines.orca import CAPABILITIES
from Backends.Py.logic.engines.orca import OrcaAdapter
from Backends.Py.logic.engines.quantum_espresso import CAPABILITIES as QE_CAPABILITIES
from Backends.Py.logic.engines.quantum_espresso import QuantumEspressoAdapter
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


class FakeCrystalAdapter(FakeAdapter):
    name = 'Quantum ESPRESSO'
    systems = ('crystal',)
    programs = ('pw.x', 'pw')

    def capabilities(self) -> Capabilities:
        return QE_CAPABILITIES

    def default_method(self):
        return QuantumEspressoAdapter().default_method()


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
    assert sample.atoms[1] == {  # fractional 0 for a molecule
        'label': 'C2',
        'element': 'C',
        'x': 1.2051,
        'y': 0.6958,
        'z': 0.0,
        'fx': 0.0,
        'fy': 0.0,
        'fz': 0.0,
        'fixed': False,
    }
    assert len(sample.sceneBonds) == 12 and sample.sceneBonds[0] == [0, 1]


def test_sample_point_group_is_found_once_per_change(qcore_application, nacl_cif, monkeypatch):
    calls = []
    found = sys.modules['Backends.Py.sample'].point_group
    monkeypatch.setattr('Backends.Py.sample.point_group', lambda atoms: calls.append(1) or found(atoms))
    sample = Sample()

    assert sample.pointGroup == sample.pointGroup == 'D6h' and len(calls) == 1
    changes = _emissions(sample.sampleChanged)
    sample.setAtomCoordinate(0, 2, '0.3')  # C1 out of the ring plane
    assert changes and sample.pointGroup == 'Cs' and len(calls) == 2

    sample.loadStructure(str(nacl_cif))
    assert sample.pointGroup == '' and len(calls) == 2  # a crystal has a space group instead


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
    sample.loadStructure(str(xyz))

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

    sample.loadStructure(QUrl.fromLocalFile(str(water)).toString())  # as the file dialog hands it over

    assert sample.summary == 'water.xyz · H2O · 3 atoms'
    assert sample.sceneBonds == [[0, 1], [0, 2]]
    assert sample.selectedAtoms == []
    assert [len(calls) for calls in changes] == [1, 1, 1] and len(external) == 1


def test_sample_load_error_keeps_the_structure(qcore_application, tmp_path):
    sample = Sample()
    sample.selectAtom(1, 'only')
    errors = _emissions(sample.loadError)

    sample.loadStructure(str(tmp_path / 'missing.xyz'))
    (tmp_path / 'bad.xyz').write_text('1\n\nQ 0 0 0\n', encoding='utf-8')
    sample.loadStructure(str(tmp_path / 'bad.xyz'))

    assert sample.formula == 'C6H6' and sample.selectedAtoms == [1]
    assert 'missing.xyz" could not be read' in errors[0][0] and 'No such file' in errors[0][0]
    assert errors[1][0].endswith('Atom 1: "Q" is not an element.')


def test_sample_loads_a_crystal(qcore_application, nacl_cif):
    sample = Sample()
    sample.selectAtom(0, 'only')
    sample.setViewRepeat(2, 1, 1)
    loads = _emissions(sample.sampleChanged)

    sample.loadStructure(str(nacl_cif))

    assert loads and sample.periodic and sample.summary == 'NaCl.cif · ClNa · Z = 4 · 8 atoms · Fm-3m'
    assert sample.cell == {
        'a': 5.6402, 'b': 5.6402, 'c': 5.6402, 'alpha': 90.0, 'beta': 90.0, 'gamma': 90.0, 'volume': 179.4252,
        'spaceGroup': 'Fm-3m', 'vectors': [[5.6402, 0.0, 0.0], [0.0, 5.6402, 0.0], [0.0, 0.0, 5.6402]],
    }  # fmt: skip
    assert sample.atoms[5]['label'] == 'Cl6' and (sample.atoms[5]['fx'], sample.atoms[5]['fy']) == (0.5, 0.0)
    assert sample.coordinates == 'fractional' and sample.viewRepeat == [1, 1, 1]
    assert sample.selectedAtoms == [] and len(sample.sceneAtoms) == 27 and len(sample.cellEdges) == 12

    oxygen = nacl_cif.with_name('oxygen.xyz')
    oxygen.write_text('1\n\nO 0 0 0\n', encoding='utf-8')
    sample.loadStructure(str(oxygen))
    assert not sample.periodic and sample.cell == {} and sample.coordinates == 'cartesian'


def test_sample_scene_is_built_once_per_change(qcore_application, nacl_cif, monkeypatch):
    import Backends.Py.sample as sample_module

    builds = []
    build = sample_module.build_scene
    monkeypatch.setattr(sample_module, 'build_scene', lambda *args: builds.append(args) or build(*args))
    sample = Sample()
    sample.loadStructure(str(nacl_cif))
    scene_changes = _emissions(sample.sceneChanged)

    for _ in range(2):
        sample.sceneAtoms, sample.sceneBonds, sample.cellEdges, sample.sceneCentre, sample.sceneExtent
    sample.setAtomFixed(0, True)  # drawn, so the scene changes, but its geometry does not
    sample.selectAtom(1, 'only')
    assert sample.sceneAtoms[0]['fixed'] and sample.selectedSceneAtoms
    assert len(builds) == 1 and len(scene_changes) == 1

    sample.setViewBoundaryAtoms(False)
    assert len(sample.sceneAtoms) == 8 and len(builds) == 2 and len(scene_changes) == 2


def test_sample_repeat_is_clamped_and_limited(qcore_application, nacl_cif, tmp_path):
    sample = Sample()
    sample.loadStructure(str(nacl_cif))
    sample.setViewRepeat(0, 9, 2)
    assert sample.viewRepeat == [1, 4, 2]

    big = tmp_path / 'big.xyz'  # 40 atoms: 4 × 4 × 3 cells are 1920, 4 × 4 × 4 are 2560
    big.write_text('40\nLattice="10 0 0 0 10 0 0 0 10"\n' + ''.join(f'Ar {i % 10} {i // 10} 0\n' for i in range(40)))
    sample.loadStructure(str(big))
    sample.setViewRepeat(4, 4, 3)
    refusals = _emissions(sample.viewChanged)
    sample.setViewRepeat(4, 4, 4)
    assert sample.viewRepeat == [4, 4, 3] and refusals  # the controls re-read the repeat


def test_sample_selects_copies_in_other_cells(qcore_application, nacl_cif):
    sample = Sample()
    sample.loadStructure(str(nacl_cif))
    scene = sample.sceneAtoms
    home = 0  # Na1 at the origin is the first scene atom
    along_a = next(i for i, atom in enumerate(scene) if atom['atom'] == 0 and atom['x'] > 5 and atom['y'] == atom['z'] == 0)

    sample.selectSceneAtom(home, 'only')
    sample.selectSceneAtom(along_a, 'toggle')

    assert sample.selectionText == 'Na1, Na1 [1 0 0]'
    assert sample.selectionMeasurement == 'distance = 5.6402\u00a0Å'  # the lattice parameter
    assert sample.selectedAtoms == [0] and sample.selectedSceneAtoms == [home, along_a]

    sample.selectAtom(0, 'only')  # a table row is the atom in its own cell
    assert sample.selectedSceneAtoms == [home] and sample.selectionText == 'Na1'

    sample.selectSceneAtom(along_a, 'toggle')
    sample.setViewBoundaryAtoms(False)  # the copy is no longer drawn but stays selected
    assert sample.selectedSceneAtoms == [0] and sample.selectionText == 'Na1, Na1 [1 0 0]'


def test_sample_edits_atom_coordinates(qcore_application):
    sample = Sample()
    sample.selectAtom(0, 'only')
    sample.selectAtom(1, 'toggle')
    changes = [_emissions(signal) for signal in (sample.atomsChanged, sample.sceneChanged, sample.selectionChanged)]
    scene = sample.sceneAtoms

    sample.setAtomCoordinate(1, 2, '−0,5')  # minus sign and decimal comma as typed

    assert sample.atoms[1]['z'] == -0.5 and sample.sceneAtoms[1]['z'] == -0.5 and scene[1]['z'] == 0.0
    assert all(len(emitted) == 1 for emitted in changes)
    assert sample.selectedAtoms == [0, 1] and sample.selectionMeasurement.startswith('distance = 1.4786')

    for text in ('', 'abc', 'nan', '-0.5'):  # not a number, or no change
        sample.setAtomCoordinate(1, 2, text)
    sample.setAtomCoordinate(99, 0, '1')
    sample.setAtomCoordinate(1, 3, '1')
    assert all(len(emitted) == 1 for emitted in changes)


def test_sample_edits_fractional_coordinates_and_the_cell(qcore_application, nacl_cif):
    sample = Sample()
    sample.loadStructure(str(nacl_cif))
    loads = _emissions(sample.structureLoaded)
    changes = _emissions(sample.sampleChanged)

    sample.setAtomCoordinate(0, 0, '1.25')  # fractional, as the tables show a crystal

    assert sample.atoms[0]['fx'] == 0.25 and sample.atoms[0]['x'] == 1.4101
    assert sample.cell['spaceGroup'] == '' and sample.summary == 'NaCl.cif · ClNa · Z = 4 · 8 atoms'

    sample.setCoordinates('cartesian')
    sample.setAtomCoordinate(0, 0, '2.82010')
    assert sample.atoms[0]['fx'] == 0.5

    sample.setCellParameter('a', '6')
    assert sample.cell['a'] == 6.0 and sample.cell['b'] == 5.6402 and sample.atoms[0]['x'] == 3.0
    sample.setCellParameter('gamma', '100')
    assert sample.cell['gamma'] == 100.0 and sample.cell['alpha'] == 90.0
    assert len(changes) == 4 and not loads

    for name, text in (('a', '-1'), ('beta', '200'), ('gamma', 'x'), ('volume', '100'), ('a', '6')):
        sample.setCellParameter(name, text)
    assert len(changes) == 4 and sample.cell['a'] == 6.0


def test_sample_shows_a_zmatrix_for_molecules_only(qcore_application, nacl_cif):
    sample = Sample()
    assert sample.zmatrix == [] and sample.zmatrixError == ''
    changes = _emissions(sample.zmatrixChanged)

    sample.setCoordinates('zmatrix')

    rows = sample.zmatrix
    assert sample.coordinates == 'zmatrix' and changes and len(rows) == 12
    assert sorted(row['atom'] for row in rows) == list(range(12))
    assert (rows[0]['bondTo'], rows[0]['angleTo'], rows[0]['dihedralTo']) == ('', '', '')
    assert rows[1]['bondTo'] == rows[0]['label'] and rows[1]['angleTo'] == ''
    assert rows[2]['angleTo'] != '' and rows[2]['dihedralTo'] == ''
    assert all(row['dihedralTo'] for row in rows[3:])
    assert rows[1]['bond'] == pytest.approx(1.3915, abs=1e-3) and set(rows[1]) == {
        'atom', 'label', 'element', 'bondTo', 'bond', 'angleTo', 'angle', 'dihedralTo', 'dihedral'
    }  # fmt: skip

    sample.setCoordinates('fractional')  # a molecule has none
    assert sample.coordinates == 'zmatrix'

    sample.loadStructure(str(nacl_cif))
    sample.setCoordinates('zmatrix')  # a crystal has none
    assert sample.coordinates == 'fractional' and sample.zmatrix == []


def test_sample_edits_the_zmatrix(qcore_application):
    from Backends.Py.logic.geometry import distance

    sample = Sample()
    sample.setCoordinates('zmatrix')
    rows = sample.zmatrix
    hydrogen = next(row for row in rows if row['element'] == 'H')
    bonded = next(i for i, atom in enumerate(sample.atoms) if atom['label'] == hydrogen['bondTo'])
    changes = [_emissions(signal) for signal in (sample.zmatrixChanged, sample.sceneChanged, sample.externalSampleChanged)]

    sample.setZmatrixValue(hydrogen['atom'], 'bond', '1,2')

    atoms = sample.logic.atoms
    assert distance(atoms[hydrogen['atom']], atoms[bonded]) == pytest.approx(1.2)
    after = sample.zmatrix
    assert [row['atom'] for row in after] == [row['atom'] for row in rows]  # same construction
    assert next(row for row in after if row['atom'] == hydrogen['atom'])['bond'] == 1.2
    assert all(len(emitted) == 1 for emitted in changes)

    for atom, field, text in (
        (hydrogen['atom'], 'bond', '1.2'),  # unchanged
        (hydrogen['atom'], 'bond', '-1'),  # out of range
        (hydrogen['atom'], 'angle', 'abc'),
        (hydrogen['atom'], 'charge', '1'),
        (rows[0]['atom'], 'bond', '2'),  # measured to the origin: not shown, not edited
        (99, 'bond', '1'),
    ):
        sample.setZmatrixValue(atom, field, text)
    assert all(len(emitted) == 1 for emitted in changes)

    sample.setCoordinates('cartesian')  # no Z-matrix edits in other coordinates
    sample.setZmatrixValue(hydrogen['atom'], 'bond', '1.0')
    assert all(len(emitted) == 1 for emitted in changes[1:])


def test_sample_range_selection_follows_the_zmatrix_rows(qcore_application):
    sample = Sample()
    sample.setCoordinates('zmatrix')
    order = [row['atom'] for row in sample.zmatrix]

    sample.selectAtom(order[2], 'only')
    sample.selectAtom(order[5], 'range')

    assert sample.selectedAtoms == order[2:6]


def test_sample_reports_a_linear_molecule_without_zmatrix(qcore_application, tmp_path):
    acetylene = tmp_path / 'acetylene.xyz'
    acetylene.write_text('4\n\nH 0 0 -1.66\nC 0 0 -0.6\nC 0 0 0.6\nH 0 0 1.66\n', encoding='utf-8')
    sample = Sample()
    sample.loadStructure(str(acetylene))

    sample.setCoordinates('zmatrix')

    assert sample.zmatrix == [] and 'linear' in sample.zmatrixError
    sample.selectAtom(0, 'only')
    sample.selectAtom(2, 'range')  # atom order when there are no rows
    assert sample.selectedAtoms == [0, 1, 2]

    sample.loadStructure(str(acetylene))  # a load starts again from Cartesian coordinates
    assert sample.coordinates == 'cartesian' and sample.zmatrixError == ''


def test_sample_edits_no_cell_of_a_molecule(qcore_application):
    sample = Sample()
    changes = _emissions(sample.sampleChanged)

    sample.setCoordinates('fractional')  # not offered for a molecule; edits stay Cartesian
    sample.setAtomCoordinate(0, 0, '0.5')
    sample.setCellParameter('a', '5')

    assert sample.atoms[0]['x'] == 0.5 and sample.cell == {} and len(changes) == 1


def test_sample_moves_an_atom_to_a_cartesian_position(qcore_application):
    sample = Sample()
    sample.setCoordinates('zmatrix')
    sample.selectAtom(0, 'only')
    sample.selectAtom(1, 'toggle')
    changes = [_emissions(signal) for signal in (sample.atomsChanged, sample.zmatrixChanged, sample.externalSampleChanged)]

    sample.setAtomPosition(1, 1.5, 0.5, 0.25)

    assert (sample.atoms[1]['x'], sample.atoms[1]['y'], sample.atoms[1]['z']) == (1.5, 0.5, 0.25)
    assert sample.selectedAtoms == [0, 1] and sample.selectionMeasurement.startswith('distance = ')
    assert all(len(emitted) == 1 for emitted in changes)

    sample.setAtomPosition(1, 1.5, 0.5, 0.25)  # unchanged
    sample.setAtomPosition(12, 0.0, 0.0, 0.0)
    sample.setAtomPosition(1, math.nan, 0.0, 0.0)
    assert all(len(emitted) == 1 for emitted in changes)


def test_sample_adds_an_atom_at_the_origin_and_selects_it(qcore_application, nacl_cif):
    sample = Sample()
    sample.selectAtom(0, 'only')
    changes = [_emissions(signal) for signal in (sample.atomsChanged, sample.sceneChanged, sample.externalSampleChanged)]

    sample.addAtom()

    assert sample.atomCount == 13 and sample.formula == 'C7H6' and len(sample.sceneAtoms) == 13
    new = sample.atoms[12]
    assert (new['label'], new['element'], new['x'], new['y'], new['z']) == ('C13', 'C', 0.0, 0.0, 0.0)
    assert sample.selectedAtoms == [12]
    assert all(len(emitted) == 1 for emitted in changes)

    sample.loadStructure(str(nacl_cif))
    sample.addAtom()
    new = sample.atoms[8]
    assert (new['fx'], new['fy'], new['fz']) == (0.0, 0.0, 0.0) and sample.cell['spaceGroup'] == ''


def test_sample_removes_the_selected_atoms(qcore_application):
    sample = Sample()
    sample.setCoordinates('zmatrix')
    sample.removeSelectedAtoms()  # nothing selected
    assert sample.atomCount == 12

    sample.selectAtom(6, 'only')
    sample.selectAtom(0, 'toggle')
    sample.removeSelectedAtoms()

    assert sample.atomCount == 10 and sample.formula == 'C5H5' and sample.multiplicity == 2
    assert [atom['label'] for atom in sample.atoms][:6] == ['C2', 'C3', 'C4', 'C5', 'C6', 'H8']
    assert sample.selectedAtoms == [] and sample.selectionText == ''
    assert sorted(row['atom'] for row in sample.zmatrix) == list(range(10))  # new references

    for index in range(10):
        sample.selectAtom(index, 'toggle')
    sample.removeSelectedAtoms()  # all of them: refused
    assert sample.atomCount == 10 and len(sample.selectedAtoms) == 10


def test_sample_add_atom_keeps_the_scene_under_its_limit(qcore_application, tmp_path):
    crystal = tmp_path / 'crystal.xyz'
    atoms = ''.join(f'H {0.1 * n} 0 0\n' for n in range(31))
    crystal.write_text(f'31\nLattice="10 0 0 0 10 0 0 0 10"\n{atoms}', encoding='utf-8')
    sample = Sample()
    sample.loadStructure(str(crystal))
    sample.setViewRepeat(4, 4, 4)  # 31 × 64 = 1984 drawn atoms
    assert sample.viewRepeat == [4, 4, 4]

    sample.addAtom()  # 32 × 64 would be over the limit

    assert sample.viewRepeat == [1, 1, 1] and sample.atomCount == 32


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
    method = Method(adapters=[adapter])
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
    method = Method(adapters=[adapter], settings=_settings(tmp_path))
    changes = _emissions(method.engineChanged)

    method.setEnginePath('file:///F:/ORCA/orca.exe')

    assert adapter.executable == 'F:/ORCA/orca.exe'
    assert len(changes) == 1
    assert Method(adapters=[FakeAdapter()], settings=_settings(tmp_path)).adapter.executable == 'F:/ORCA/orca.exe'

    method.setEnginePath('')
    assert adapter.executable is None


def test_method_settings(qcore_application):
    method = Method(adapters=[FakeAdapter()])
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


def test_method_follows_the_sample_to_the_engine_that_runs_it(qcore_application, nacl_cif):
    method = Method(adapters=[FakeAdapter(), FakeCrystalAdapter()])
    engine = _emissions(method.engineChanged)
    theory = _emissions(method.levelOfTheoryChanged)
    method.setFunctional('PBE0')

    method.set_sample_cell(Sample().logic.cell)  # still a molecule: nothing switches
    assert method.engineName == 'ORCA' and not engine

    crystal = Sample()
    crystal.loadStructure(str(nacl_cif))
    method.set_sample_cell(crystal.logic.cell)

    assert method.engineName == 'Quantum ESPRESSO' and method.canRun and len(engine) == 1
    assert method.functional == 'PBE' and method.basisSet == 'pw' and len(theory) == 2
    assert [choice['value'] for choice in method.functionalChoices] == ['PBE']
    assert method.auxiliaryBasisChoices == [] and not method.stabilityCheckOffered
    assert [(card['name'], card['active'], card['problem']) for card in method.engines] == [
        ('ORCA', False, 'ORCA runs molecules only; this sample is periodic.'),
        ('Quantum ESPRESSO', True, ''),
    ]
    assert method.engineExecutableFilter == 'Quantum ESPRESSO executable (pw.x pw.exe pw)'

    method.set_sample_cell(None)  # each engine kept its own settings
    assert method.engineName == 'ORCA' and method.functional == 'PBE0' and method.stabilityCheckOffered
    assert method.engines[1]['problem'] == 'Quantum ESPRESSO runs crystals only; this sample is a molecule.'


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
    assert job.stepStates == {'single_point': 'completed'}


def test_job_step_states_follow_the_output(qcore_application, tmp_path):
    job = _job(
        tmp_path, 'import time\nprint("energy", flush=True)\ntime.sleep(1)\nprint("frequencies")\nraise SystemExit(3)\n'
    )
    job._adapter.step_markers = {CalculationType.VIBRATIONAL_FREQUENCIES: re.compile('frequencies')}
    job._calculations.set_selected(CalculationType.VIBRATIONAL_FREQUENCIES, True)

    job.run()
    assert job.stepStates == {'single_point': 'running', 'vibrational_frequencies': 'idle'}
    _wait_for(job, qcore_application)

    assert job.stepStates == {'single_point': 'completed', 'vibrational_frequencies': 'failed'}


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
    assert job.stepStates == {}  # no step ran
    assert not (tmp_path / 'runs').exists()


def test_job_stop(qcore_application, tmp_path):
    job = _job(tmp_path, 'import time\nprint("started", flush=True)\ntime.sleep(60)\n')
    job.run()
    time.sleep(0.5)

    job.stop()

    assert job.state == 'stopped' and job.message.startswith('Stopped after ')
    assert job.stepStates == {'single_point': 'stopped'}
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


def test_backend_relays_the_cell_to_the_method_part(backend, nacl_cif):
    backend.sample.loadStructure(str(nacl_cif))

    assert backend.project.sampleName == 'ClNa, 8 atoms'
    assert backend.method.periodic and backend.method.canRun and backend.method.cannotRunReason == ''
    assert backend.method.engineName == backend.project.engine == 'Quantum ESPRESSO'
    assert backend.job._adapter is backend.method.adapter  # the next job runs on it
    assert backend.method.kpointGrid == [2, 2, 2]

    backend.method.setKpointGrid(3, 3, 1)
    assert backend.method.kpointGrid == [3, 3, 1]
    backend.method.setKpointSpacing(0.05)  # a new spacing replaces the grid set by hand
    assert backend.method.kpointGrid == [4, 4, 4]


def test_backend_relays_a_loaded_structure(backend, tmp_path):
    water = tmp_path / 'water.xyz'
    water.write_text('3\n\nO 0 0 0\nH 0 0.76 -0.47\nH 0 -0.76 -0.47\n', encoding='utf-8')

    backend.sample.loadStructure(str(water))

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


def test_results_of_a_crystal_show_the_band_gap_or_the_fermi_energy(qcore_application):
    results = Results()
    results.set_results(ResultsLogic(final_energy=-45.6, homo=6.2527, lumo=6.9439, crystal=True))
    assert results.tiles[1] == {
        'title': 'Band gap (eV)',
        'value': '0.69',
        'detail': 'VBM 6.25 · CBM 6.94 · on the k-point grid',
        'tone': '',
    }

    results.set_results(ResultsLogic(final_energy=-45.6, fermi_energy=-0.5, crystal=True))
    assert results.tiles[1] == {
        'title': 'Fermi energy (eV)',
        'value': '−0.50',
        'detail': 'metallic on the k-point grid',
        'tone': '',
    }


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


def _load_water(backend, tmp_path) -> None:
    """Water at the start geometry of the optimisation in WATER."""
    water = tmp_path / 'water.xyz'
    water.write_text('3\n\nO 0 0 0.117\nH 0 0.757 -0.468\nH 0 -0.757 -0.468\n', encoding='utf-8')
    backend.sample.loadStructure(str(water))


def _positions(sample: Sample) -> list:
    return [(atom.x, atom.y, atom.z) for atom in sample.logic.atoms]


def test_backend_moves_the_sample_to_a_converged_optimisation(backend, tmp_path):
    _load_water(backend, tmp_path)
    backend.sample.setAtomFixed(0, True)
    backend.sample.selectAtom(1, 'only')
    scene = _emissions(backend.sample.sceneChanged)
    relayed = _emissions(backend.sample.externalSampleChanged)

    backend.job._chunks = [WATER.read_text(encoding='utf-8')]
    backend.job._set_state(JobState.COMPLETED, '')

    assert _positions(backend.sample) == [(0.0, 0.0, 0.12), (0.0, 0.76, -0.47), (0.0, -0.76, -0.47)]
    assert backend.sample.logic.atoms[0].fixed and backend.sample.selectedAtoms == [1]
    assert scene and len(relayed) == 1
    # The results still compare the start geometry with the final one.
    assert backend.results.geometryRows[0]['bondInitial'] == '0.9567'

    backend.job._set_state(JobState.COMPLETED, '')  # the sample has moved on: no second move
    assert len(relayed) == 1


@pytest.mark.parametrize('state', [JobState.FAILED, JobState.STOPPED])
def test_backend_keeps_the_sample_after_an_unfinished_job(backend, tmp_path, state):
    _load_water(backend, tmp_path)
    before = _positions(backend.sample)

    backend.job._chunks = [WATER.read_text(encoding='utf-8')]
    backend.job._set_state(state, '')

    assert _positions(backend.sample) == before


def test_backend_keeps_a_structure_loaded_during_the_job(backend):
    before = _positions(backend.sample)  # benzene, not the water the job optimised

    backend.job._chunks = [WATER.read_text(encoding='utf-8')]
    backend.job._set_state(JobState.COMPLETED, '')

    assert _positions(backend.sample) == before


def test_backend_takes_an_optimisation_after_edits_and_edits_after_it(backend, tmp_path):
    # Edits before the job are the start geometry the job optimises.
    _load_water(backend, tmp_path)
    backend.sample.setAtomCoordinate(0, 2, '0.117')  # unchanged: still at the job's start
    backend.job._chunks = [WATER.read_text(encoding='utf-8')]
    backend.job._set_state(JobState.COMPLETED, '')
    assert _positions(backend.sample)[0] == (0.0, 0.0, 0.12)

    # The optimised geometry is edited like any other.
    backend.sample.setAtomCoordinate(0, 2, '0.2')
    assert _positions(backend.sample)[0] == (0.0, 0.0, 0.2)
    assert backend.project.sampleName == 'H2O, 3 atoms'


def test_backend_keeps_a_structure_edited_during_the_job(backend, tmp_path):
    _load_water(backend, tmp_path)
    backend.sample.setAtomCoordinate(1, 1, '0.8')  # the GUI disables this while a job runs
    edited = _positions(backend.sample)

    backend.job._chunks = [WATER.read_text(encoding='utf-8')]
    backend.job._set_state(JobState.COMPLETED, '')

    assert _positions(backend.sample) == edited


def test_backend_relays_an_edited_cell_to_the_method_part(backend, nacl_cif):
    backend.sample.loadStructure(str(nacl_cif))
    assert backend.method.kpointGrid == [2, 2, 2]

    backend.sample.setCellParameter('c', '2.5')

    assert backend.method.kpointGrid == [2, 2, 4]


def test_backend_optimisation_updates_the_zmatrix(backend, tmp_path):
    _load_water(backend, tmp_path)
    backend.sample.setCoordinates('zmatrix')
    before = backend.sample.zmatrix
    changes = _emissions(backend.sample.zmatrixChanged)

    backend.job._chunks = [WATER.read_text(encoding='utf-8')]
    backend.job._set_state(JobState.COMPLETED, '')

    after = backend.sample.zmatrix
    assert changes and [row['atom'] for row in after] == [row['atom'] for row in before]
    assert after[1]['bond'] != before[1]['bond'] and backend.sample.coordinates == 'zmatrix'
