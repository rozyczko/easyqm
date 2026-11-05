# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Sample page backend part: the QML-facing proxy of `logic.sample.Sample`."""

import contextlib
import math
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Property
from PySide6.QtCore import QObject
from PySide6.QtCore import Signal
from PySide6.QtCore import Slot

from .helpers import to_local_path
from .logic.geometry import measure
from .logic.sample import BENZENE
from .logic.sample import MULTIPLICITY_NAMES
from .logic.sample import Sample as SampleLogic
from .logic.scene import HOME
from .logic.scene import Image
from .logic.scene import Scene
from .logic.scene import build_scene
from .logic.scene import place
from .logic.symmetry import ATOM_LIMIT as POINT_GROUP_ATOM_LIMIT
from .logic.symmetry import point_group
from .logic.zmatrix import FIELDS as ZMATRIX_FIELDS
from .logic.zmatrix import ZMatrix

_COORDINATE_DECIMALS = 4
_ANGLE_DECIMALS = 2
_SELECTION_LABELS_SHOWN = 4
REPEAT_MAX = 4
_CELL_PARAMETERS = ('a', 'b', 'c', 'alpha', 'beta', 'gamma')
_UNCHANGED = 1e-9  # a typed value this close to the current one is no edit
_NEW_ATOM_ELEMENT = 'C'
# Above this the viewer, one 3D model per atom, gets slow (PERIODIC-DESIGN.md, section 4).
SCENE_ATOM_LIMIT = 2000


class Sample(QObject):
    # The structure was replaced or edited: every property may have changed.
    sampleChanged = Signal()
    # A structure was loaded from a file (not emitted for edits).
    structureLoaded = Signal()
    # Per-atom data changed: positions or the fixed flag.
    atomsChanged = Signal()
    # The selected atoms, shared by the viewer and the atom tables.
    selectionChanged = Signal()
    # What the viewer draws: the structure, the view settings or an atom's flags changed.
    sceneChanged = Signal()
    # Display settings: repeat, boundary atoms, coordinates in the tables.
    viewChanged = Signal()
    # The Z-matrix rows: the structure or the coordinates shown changed.
    zmatrixChanged = Signal()
    # Charge or multiplicity changed (also with every structure change).
    electronicStateChanged = Signal()
    loadError = Signal(str)

    # For the other backend parts.
    externalSampleChanged = Signal()

    def __init__(self, logic: Optional[SampleLogic] = None, parent=None):
        super().__init__(parent)
        # The bundled benzene until a structure is loaded from a file.
        self._logic = logic if logic is not None else SampleLogic.benzene()
        # (atom index, image) in the order picked; the image says which drawn copy of a
        # crystal's atom was picked, so measurements across cell faces are right.
        self._selected: list[tuple[int, Image]] = []
        self._anchor: Optional[int] = None  # atom where a range selection starts
        self._repeat: Image = (1, 1, 1)
        self._boundary_atoms = True
        self._coordinates = self._default_coordinates()
        self._scene: Optional[Scene] = None  # built on first read
        self._point_group: Optional[str] = None  # found on first read
        # Built on first read in 'zmatrix' mode; the construction (which atoms place which)
        # is kept from one Z-matrix to the next, so rows do not reorder while atoms move.
        self._zmatrix: Optional[ZMatrix] = None
        self._zmatrix_error = ''
        self._zmatrix_stale = True
        self._construction = None
        # Files the user picked in a file dialog this session (the assistant may load these).
        self.picked_paths: set[Path] = set()
        self.atomsChanged.connect(self.sceneChanged)

    @property
    def logic(self) -> SampleLogic:
        """For the other backend parts (plain Python, not exposed to QML)."""
        return self._logic

    # Read-only properties

    @Property(str, notify=sampleChanged)
    def name(self) -> str:
        return self._logic.name

    @Property(str, notify=sampleChanged)
    def source(self) -> str:
        return self._logic.source

    @Property(str, notify=sampleChanged)
    def formula(self) -> str:
        return self._logic.formula

    @Property(str, notify=sampleChanged)
    def summary(self) -> str:
        return self._logic.summary

    @Property(int, notify=sampleChanged)
    def atomCount(self) -> int:
        return self._logic.atom_count

    @Property(bool, notify=sampleChanged)
    def periodic(self) -> bool:
        return self._logic.periodic

    @Property('QVariantMap', notify=sampleChanged)
    def cell(self) -> dict:
        """{a, b, c, alpha, beta, gamma, volume, spaceGroup, vectors}; empty for a molecule."""
        cell = self._logic.cell
        if cell is None:
            return {}
        values = dict(zip(('a', 'b', 'c', 'alpha', 'beta', 'gamma'), (*cell.lengths, *cell.angles)))
        values['volume'] = cell.volume
        values = {key: round(value, _COORDINATE_DECIMALS) for key, value in values.items()}
        values['spaceGroup'] = cell.space_group
        values['vectors'] = [_rounded(vector) for vector in cell.vectors]
        return values

    @Property(str, notify=sampleChanged)
    def pointGroup(self) -> str:
        """Schoenflies symbol of a molecule ('C2v'); '' for a crystal or when not determined."""
        if self._logic.periodic:
            return ''
        if self._point_group is None:
            self._point_group = point_group(self._logic.atoms)
        return self._point_group

    @Property(int, constant=True)
    def pointGroupAtomLimit(self) -> int:
        return POINT_GROUP_ATOM_LIMIT

    @Property(int, notify=electronicStateChanged)
    def charge(self) -> int:
        return self._logic.charge

    @Property(int, notify=electronicStateChanged)
    def multiplicity(self) -> int:
        return self._logic.multiplicity

    @Property('QVariantList', notify=electronicStateChanged)
    def multiplicityChoices(self) -> list:
        """[{value, label}] of the multiplicities the electron count allows: '1 (singlet)', …."""
        return [{'value': m, 'label': f'{m} ({MULTIPLICITY_NAMES[m - 1]})'} for m in self._logic.multiplicities()]

    @Property('QVariantList', notify=atomsChanged)
    def atoms(self) -> list:
        """[{label, element, x, y, z, fx, fy, fz, fixed}]; fractional fx, fy, fz are 0 for a molecule."""
        cell = self._logic.cell
        rows = []
        for atom in self._logic.atoms:
            fractional = cell.fractional(atom.x, atom.y, atom.z) if cell else (0.0, 0.0, 0.0)
            x, y, z = _rounded((atom.x, atom.y, atom.z))
            fx, fy, fz = _rounded(fractional)
            rows.append(dict(label=atom.label, element=atom.element, x=x, y=y, z=z, fx=fx, fy=fy, fz=fz, fixed=atom.fixed))
        return rows

    @Property(int, notify=atomsChanged)
    def fixedCount(self) -> int:
        return self._logic.fixed_count

    # Scene: what the viewer draws (logic/scene.py)

    @Property('QVariantList', notify=sceneChanged)
    def sceneAtoms(self) -> list:
        """[{atom, label, element, fixed, x, y, z}]; `atom` indexes `atoms`."""
        atoms = self._logic.atoms
        return [
            {
                'atom': drawn.atom,
                'label': atoms[drawn.atom].label,
                'element': drawn.element,
                'fixed': atoms[drawn.atom].fixed,
                'x': drawn.x,
                'y': drawn.y,
                'z': drawn.z,
            }
            for drawn in self._current_scene().atoms
        ]

    @Property('QVariantList', notify=sceneChanged)
    def sceneBonds(self) -> list:
        return [list(pair) for pair in self._current_scene().bonds]

    @Property('QVariantList', notify=sceneChanged)
    def cellEdges(self) -> list:
        """[[start, end], …] with points [x, y, z]; edges 0, 4 and 8 run from the origin along a, b, c."""
        return [[list(start), list(end)] for start, end in self._current_scene().cell_edges]

    @Property('QVariantList', notify=sceneChanged)
    def sceneCentre(self) -> list:
        return list(self._current_scene().centre)

    @Property(float, notify=sceneChanged)
    def sceneExtent(self) -> float:
        return self._current_scene().extent

    @Property(int, constant=True)
    def sceneAtomLimit(self) -> int:
        return SCENE_ATOM_LIMIT

    # Selection

    @Property('QVariantList', notify=selectionChanged)
    def selectedAtoms(self) -> list:
        """Selected atom indices, each once, in the order picked."""
        return list(dict.fromkeys(index for index, _ in self._selected))

    @property
    def selection(self) -> list:
        """(atom index, image) pairs as picked; the image tells which drawn copy of a crystal's atom."""
        return list(self._selected)

    @Property('QVariantList', notify=selectionChanged)
    def selectedSceneAtoms(self) -> list:
        """Indices into `sceneAtoms` of the selected drawn atoms."""
        selected = set(self._selected)
        return [index for index, drawn in enumerate(self._current_scene().atoms) if (drawn.atom, drawn.image) in selected]

    @Property(str, notify=selectionChanged)
    def selectionText(self) -> str:
        """'C1, C2' for a few atoms, '7 atoms' for more; empty when nothing is selected.

        A copy of an atom in another cell carries its translation: 'Na1, Cl5 [1 0 0]'.
        """
        if len(self._selected) > _SELECTION_LABELS_SHOWN:
            return f'{len(self._selected)} atoms'
        labels = []
        for index, image in self._selected:
            label = self._logic.atoms[index].label
            labels.append(label if image == HOME else f'{label} [{" ".join(map(str, image))}]')
        return ', '.join(labels)

    @Property(str, notify=selectionChanged)
    def selectionMeasurement(self) -> str:
        """For 2, 3 or 4 selected atoms, in the order picked: 'distance = 1.3915 Å',
        'angle = 120.00°' at the middle atom, 'dihedral = −60.00°'; empty otherwise."""
        result = measure([place(self._logic, index, image) for index, image in self._selected])
        if result is None:
            return ''
        name, value = result
        if value is None:
            return f'{name} undefined'
        if name == 'distance':
            return f'distance = {value:.4f} Å'
        value = round(value, 2) + 0.0  # no '−0.00'
        return f'{name} = {value:.2f}°'.replace('-', '−')

    # View settings

    @Property('QVariantList', notify=viewChanged)
    def viewRepeat(self) -> list:
        return list(self._repeat)

    @Property(bool, notify=viewChanged)
    def viewBoundaryAtoms(self) -> bool:
        return self._boundary_atoms

    @Property(str, notify=viewChanged)
    def coordinates(self) -> str:
        """How the tables show positions: 'cartesian'; 'fractional' for a crystal, 'zmatrix'
        for a molecule."""
        return self._coordinates

    # Z-matrix of a molecule (logic/zmatrix.py)

    @Property('QVariantList', notify=zmatrixChanged)
    def zmatrix(self) -> list:
        """Rows in construction order while the tables show the Z-matrix, empty otherwise:
        [{atom, label, element, bondTo, bond, angleTo, angle, dihedralTo, dihedral}]. `atom`
        indexes `atoms`; a reference is the label of the atom the value is measured to, '' where
        chemcoord measures it to the origin or an axis (the first three rows)."""
        zmatrix = self._current_zmatrix()
        if zmatrix is None:
            return []
        atoms = self._logic.atoms
        rows = []
        for row in zmatrix.rows:
            entry = {'atom': row.atom, 'label': atoms[row.atom].label, 'element': atoms[row.atom].element}
            for field, reference, value in zip(ZMATRIX_FIELDS, row.references, row.values):
                decimals = _COORDINATE_DECIMALS if field == 'bond' else _ANGLE_DECIMALS
                entry[f'{field}To'] = '' if reference is None else atoms[reference].label
                entry[field] = round(value, decimals) + 0.0
            rows.append(entry)
        return rows

    @Property(str, notify=zmatrixChanged)
    def zmatrixError(self) -> str:
        """Why there is no Z-matrix to show ('No Z-matrix: the molecule is linear, …'); empty
        when there is one, or when the tables show other coordinates."""
        if self._coordinates != 'zmatrix' or self._current_zmatrix() is not None:
            return ''
        return self._zmatrix_error

    # Input

    @Slot(str)
    def loadStructure(self, path: str) -> None:
        """The file dialog's choice."""
        path = to_local_path(path)
        self.picked_paths.add(Path(path).resolve())
        error = self.load_file(path)
        if error:
            self.loadError.emit(f'"{path}" could not be read.\n\n{error}')

    def load_file(self, path) -> str:
        """Replace the structure with the one in the file. Returns why it could not be read, or ''."""
        try:
            self._logic.load(path)
        except (ValueError, OSError) as error:
            return error.strerror if isinstance(error, OSError) and error.strerror else str(error)
        self._structure_replaced()
        return ''

    def reset(self) -> None:
        """Back to the bundled benzene and the default view settings, as at start-up (for
        PyBackend.reset)."""
        self._logic.load(BENZENE)
        self._boundary_atoms = True  # kept by a load, as a display preference
        self._structure_replaced()

    def _structure_replaced(self) -> None:
        """Another structure: no selection, one cell, its default coordinates."""
        self._selected, self._anchor = [], None
        self._repeat = (1, 1, 1)
        self._coordinates = self._default_coordinates()
        self._construction = None  # of other atoms
        self.viewChanged.emit()
        self._structure_changed()
        self.structureLoaded.emit()

    def apply_optimisation(self, optimisation) -> bool:
        """Move the atoms, and a crystal's cell, to the geometry an optimisation ended at.

        Only if the optimisation started from the structure shown: one loaded or edited while
        the job ran is left alone. The selection and the view settings stay.
        """
        if not self._logic.at_positions(optimisation.initial):
            return False
        try:
            self._logic.move_atoms(optimisation.final, optimisation.final_cell)
        except ValueError:
            return False
        self._structure_changed()
        return True

    # Editing: the user's changes and an optimisation's geometry update the same structure.
    # Text that is not a number, or values that make no cell, change nothing; the fields
    # then show the old value again.

    @Slot(int, int, str)
    def setAtomCoordinate(self, index: int, axis: int, text: str) -> None:
        """Set x, y or z (axis 0, 1, 2) of an atom, in the coordinates the tables show."""
        value = _number(text)
        if value is None or not 0 <= index < self._logic.atom_count or axis not in (0, 1, 2):
            return
        atom = self._logic.atoms[index]
        cell = self._logic.cell
        fractional = self._coordinates == 'fractional' and cell is not None
        position = list(cell.fractional(atom.x, atom.y, atom.z) if fractional else (atom.x, atom.y, atom.z))
        if math.isclose(position[axis], value, abs_tol=_UNCHANGED):
            return
        position[axis] = value
        self._logic.set_position(index, tuple(position), fractional)
        self._structure_changed()

    @Slot(int, float, float, float)
    def setAtomPosition(self, index: int, x: float, y: float, z: float) -> None:
        """Put an atom at Cartesian x, y, z in Å: where the viewer's atom mover dropped it."""
        position = (x, y, z)
        if not 0 <= index < self._logic.atom_count or not all(map(math.isfinite, position)):
            return
        atom = self._logic.atoms[index]
        if all(math.isclose(old, new, abs_tol=_UNCHANGED) for old, new in zip((atom.x, atom.y, atom.z), position)):
            return
        self.set_atom_positions({index: position})

    def set_atom_positions(self, positions: dict, fractional: bool = False) -> None:
        """Put atoms at new positions, {index: (x, y, z)}: Cartesian in Å, or fractional in a
        crystal's cell. One notification for all of them.

        :raises ValueError: for an index out of range, or fractional coordinates of a molecule;
            nothing changes then.
        """
        count = self._logic.atom_count
        if not all(0 <= index < count for index in positions):
            raise ValueError(f'Atom indices run from 0 to {count - 1}.')
        if fractional and not self._logic.periodic:
            raise ValueError('A molecule has no fractional coordinates.')
        for index, position in positions.items():
            self._logic.set_position(index, tuple(position), fractional)
        self._structure_changed()

    @Slot(str, str)
    def setCellParameter(self, name: str, text: str) -> None:
        """Set one of a, b, c (Å), alpha, beta, gamma (°) of a crystal's cell; the others stay."""
        value = _number(text)
        cell = self._logic.cell
        if value is None or cell is None or name not in _CELL_PARAMETERS:
            return
        parameters = dict(zip(_CELL_PARAMETERS, (*cell.lengths, *cell.angles)))
        if math.isclose(parameters[name], value, abs_tol=_UNCHANGED):
            return
        parameters[name] = value
        with contextlib.suppress(ValueError):
            self.set_cell_parameters(parameters)

    def set_cell_parameters(self, parameters: dict) -> None:
        """Give a crystal's cell these a, b, c (Å), alpha, beta, gamma (°); the atoms keep their
        fractional coordinates. :raises ValueError: for a molecule or values that make no cell."""
        self._logic.set_cell_parameters(**parameters)
        self._structure_changed()

    @Slot(int, str, str)
    def setZmatrixValue(self, atom: int, field: str, text: str) -> None:
        """Set the 'bond' (Å), 'angle' or 'dihedral' (°) of an atom in the Z-matrix: the atom
        moves, and with it the atoms placed from it."""
        value = _number(text)
        if value is not None:
            with contextlib.suppress(ValueError):
                self.set_zmatrix_value(atom, field, value)

    def set_zmatrix_value(self, atom: int, field: str, value: float) -> None:
        """As `setZmatrixValue`, for a number.

        :raises ValueError: when the tables show no Z-matrix, for an atom or field it does not
            have, or for a value `ZMatrix.positions_with` refuses; nothing changes then.
        """
        zmatrix = self._current_zmatrix()
        if zmatrix is None:
            raise ValueError(self._zmatrix_error or 'The tables do not show the Z-matrix.')
        if field not in ZMATRIX_FIELDS:
            raise ValueError(f'The field is one of {", ".join(ZMATRIX_FIELDS)}.')
        try:
            current = zmatrix.row(atom).value(field)
        except KeyError:
            raise ValueError(f'Atom {atom} is not in the Z-matrix.') from None
        if math.isclose(current, value, abs_tol=_UNCHANGED):
            return
        self._logic.set_positions(zmatrix.positions_with(atom, field, value))
        self._structure_changed()

    def zmatrix_rows(self) -> list:
        """The Z-matrix rows (`logic.zmatrix.ZRow`) while the tables show it, [] otherwise."""
        zmatrix = self._current_zmatrix()
        return zmatrix.rows if zmatrix is not None else []

    @Slot()
    def addAtom(self) -> None:
        """Add a carbon atom at the origin, Cartesian (0, 0, 0) of a molecule or fractional
        [0, 0, 0] of a crystal, and select it alone, ready for its coordinates."""
        self.add_atom(_NEW_ATOM_ELEMENT, (0.0, 0.0, 0.0), fractional=self._logic.periodic)

    def add_atom(self, element: str, position, fractional: bool = False) -> int:
        """Add an atom after the others, as `logic.Sample.add_atom`, and select it alone.
        Returns its index. :raises ValueError: for an unknown element, or fractional coordinates
        of a molecule; nothing changes then."""
        index = self._logic.add_atom(element, tuple(position), fractional)
        self._selected, self._anchor = [(index, HOME)], index
        self._atom_count_changed()
        return index

    @Slot()
    def removeSelectedAtoms(self) -> None:
        """Remove the selected atoms; refused when they are all the atoms."""
        if self._selected:
            with contextlib.suppress(ValueError):
                self.remove_atoms(self.selectedAtoms)

    def remove_atoms(self, indices) -> None:
        """Remove the atoms at `indices` and clear the selection. :raises ValueError: for an
        index out of range, or if no atom would be left; nothing changes then."""
        self._logic.remove_atoms(indices)
        self._selected, self._anchor = [], None
        self._atom_count_changed()

    def _atom_count_changed(self) -> None:
        """The atom indices changed: the Z-matrix picks new references, and a repeat that
        would now draw too many atoms goes back to one cell."""
        self._construction = None
        if self._logic.atom_count * math.prod(self._repeat) > SCENE_ATOM_LIMIT:
            self._repeat = (1, 1, 1)
            self.viewChanged.emit()
        self._structure_changed()

    def _structure_changed(self) -> None:
        """The atoms or the cell changed: everything shown from them is out of date. The
        selection keeps its atoms, so measurements follow them."""
        self._scene = None
        self._point_group = None
        self._zmatrix_stale = True
        self.sampleChanged.emit()
        self.atomsChanged.emit()
        self.zmatrixChanged.emit()
        self.selectionChanged.emit()
        self.electronicStateChanged.emit()
        self.externalSampleChanged.emit()

    # Selection

    @Slot(int, str)
    def selectAtom(self, index: int, mode: str) -> None:
        """Change the selection by clicking an atom in a table, as in a file list.

        'only' (click): this atom alone. 'toggle' (Ctrl-click): add it, or take it out if
        selected. 'range' (Shift-click): the atoms from the last 'only' or 'toggle' atom to
        this one, in the order of the table rows, replacing the selection. Table rows are the atoms in their
        own cell (image (0, 0, 0)).
        """
        if mode == 'range':
            order = self._table_order()
            start = order.index(self._anchor if self._anchor is not None else index)
            end = order.index(index)
            step = 1 if end >= start else -1
            self._set_selected([(order[row], HOME) for row in range(start, end + step, step)])
        else:
            self._pick((index, HOME), mode)

    @Slot(int, str)
    def selectSceneAtom(self, scene_index: int, mode: str) -> None:
        """The viewer's click on a drawn atom: 'only' or 'toggle', as in `selectAtom`."""
        drawn = self._current_scene().atoms[scene_index]
        self._pick((drawn.atom, drawn.image), mode)

    @Slot()
    def clearSelection(self) -> None:
        self._anchor = None
        self._set_selected([])

    def select_atoms(self, indices) -> None:
        """Select exactly these atoms, in their own cell; none clears the selection.
        :raises ValueError: for an index out of range."""
        count = self._logic.atom_count
        if not all(0 <= index < count for index in indices):
            raise ValueError(f'Atom indices run from 0 to {count - 1}.')
        self._anchor = indices[-1] if indices else None
        self._set_selected([(index, HOME) for index in dict.fromkeys(indices)])

    def _pick(self, entry: tuple[int, Image], mode: str) -> None:
        if mode == 'toggle':
            selected = [picked for picked in self._selected if picked != entry]
            if len(selected) == len(self._selected):
                selected.append(entry)
        else:
            selected = [entry]
        self._anchor = entry[0]
        self._set_selected(selected)

    def _set_selected(self, selected: list) -> None:
        if selected != self._selected:
            self._selected = selected
            self.selectionChanged.emit()

    # Setters

    @Slot(int, bool)
    def setAtomFixed(self, index: int, value: bool) -> None:
        """Fix or free this atom; for a selected atom, every selected atom."""
        selected = self.selectedAtoms
        self.set_atoms_fixed(selected if index in selected else [index], value)

    def set_atoms_fixed(self, indices, value: bool) -> list[int]:
        """Fix or free exactly the atoms at `indices`, whatever is selected. Returns the indices
        that changed. :raises ValueError: for an index out of range; nothing changes then."""
        atoms = self._logic.atoms
        if not all(0 <= index < len(atoms) for index in indices):
            raise ValueError(f'Atom indices run from 0 to {len(atoms) - 1}.')
        changed = [index for index in dict.fromkeys(indices) if atoms[index].fixed != bool(value)]
        for index in changed:
            atoms[index].fixed = bool(value)
        if changed:
            self.atomsChanged.emit()
        return changed

    @Slot(int)
    def setCharge(self, charge: int) -> None:
        """A multiplicity the new electron count does not allow goes to the lowest it allows."""
        try:
            self._logic.set_charge(int(charge))
        except ValueError:
            pass  # the field shows the old charge again
        self.electronicStateChanged.emit()

    @Slot(int)
    def setMultiplicity(self, multiplicity: int) -> None:
        try:
            self.set_electronic_state(self._logic.charge, int(multiplicity))
        except ValueError:
            self.electronicStateChanged.emit()  # the combo shows the old multiplicity again

    def set_electronic_state(self, charge: int, multiplicity: int) -> None:
        """:raises ValueError: for a pair the electron count does not allow; nothing changes then."""
        if (charge, multiplicity) == (self._logic.charge, self._logic.multiplicity):
            return
        self._logic.set_electronic_state(charge, multiplicity)
        self.electronicStateChanged.emit()

    @Slot(int, int, int)
    def setViewRepeat(self, na: int, nb: int, nc: int) -> None:
        """Draw na × nb × nc cells, each 1 to 4; refused when the cells would hold more than
        SCENE_ATOM_LIMIT atoms (the controls then snap back)."""
        repeat = tuple(max(1, min(REPEAT_MAX, int(count))) for count in (na, nb, nc))
        if self._logic.atom_count * repeat[0] * repeat[1] * repeat[2] > SCENE_ATOM_LIMIT or repeat == self._repeat:
            self.viewChanged.emit()
            return
        self._repeat = repeat
        self._rebuild_scene()

    @Slot(bool)
    def setViewBoundaryAtoms(self, value: bool) -> None:
        if bool(value) != self._boundary_atoms:
            self._boundary_atoms = bool(value)
            self._rebuild_scene()

    @Slot(str)
    def setCoordinates(self, value: str) -> None:
        """'cartesian'; 'fractional' for a crystal; 'zmatrix' for a molecule."""
        if value in self.coordinate_choices and value != self._coordinates:
            self._coordinates = value
            self.viewChanged.emit()
            self.zmatrixChanged.emit()

    # Scene

    def _current_scene(self) -> Scene:
        if self._scene is None:
            self._scene = build_scene(self._logic, self._repeat, self._boundary_atoms)
        return self._scene

    def _rebuild_scene(self) -> None:
        """After a view setting changed: new scene; the selection stays, drawn elsewhere."""
        self._scene = None
        self.viewChanged.emit()
        self.sceneChanged.emit()
        self.selectionChanged.emit()

    @property
    def coordinate_choices(self) -> tuple:
        return ('cartesian', 'fractional') if self._logic.periodic else ('cartesian', 'zmatrix')

    def _default_coordinates(self) -> str:
        return 'fractional' if self._logic.periodic else 'cartesian'

    # Z-matrix

    def _current_zmatrix(self) -> Optional[ZMatrix]:
        """The Z-matrix of the current atoms while the tables show it; None otherwise, or when
        there is none (`_zmatrix_error` says why)."""
        if self._coordinates != 'zmatrix':
            return None
        if self._zmatrix_stale:
            self._zmatrix_stale = False
            try:
                self._zmatrix, self._zmatrix_error = ZMatrix(self._logic.atoms, self._construction), ''
                self._construction = self._zmatrix.construction
            except ValueError as error:
                self._zmatrix, self._zmatrix_error = None, str(error)
        return self._zmatrix

    def _table_order(self) -> list[int]:
        """Atom indices in the order of the table rows: construction order for the Z-matrix."""
        zmatrix = self._current_zmatrix()
        return [row.atom for row in zmatrix.rows] if zmatrix is not None else list(range(self._logic.atom_count))


def _rounded(values) -> list:
    return [round(value, _COORDINATE_DECIMALS) for value in values]


def _number(text: str) -> Optional[float]:
    """'1.5', ' -0.25', '−0.25', '1,5' -> the number; None for anything else."""
    try:
        value = float(str(text).strip().replace('−', '-').replace(',', '.'))
    except ValueError:
        return None
    return value if math.isfinite(value) else None
