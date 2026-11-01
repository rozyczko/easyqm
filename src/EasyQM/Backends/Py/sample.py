# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Sample page backend part: the QML-facing proxy of `logic.sample.Sample`."""

from typing import Optional

from PySide6.QtCore import Property
from PySide6.QtCore import QObject
from PySide6.QtCore import Signal
from PySide6.QtCore import Slot

from .helpers import to_local_path
from .logic.geometry import measure
from .logic.sample import Sample as SampleLogic
from .logic.scene import HOME
from .logic.scene import Image
from .logic.scene import Scene
from .logic.scene import build_scene
from .logic.scene import place

_COORDINATE_DECIMALS = 4
_SELECTION_LABELS_SHOWN = 4
_REPEAT_MAX = 4
# Above this the viewer, one 3D model per atom, gets slow (PERIODIC-DESIGN.md, section 4).
SCENE_ATOM_LIMIT = 2000


class Sample(QObject):
    # The structure was replaced: every property may have changed.
    sampleChanged = Signal()
    # Per-atom data changed (PoC1: the fixed flag only).
    atomsChanged = Signal()
    # The selected atoms, shared by the viewer and the atom tables.
    selectionChanged = Signal()
    # What the viewer draws: the structure, the view settings or an atom's flags changed.
    sceneChanged = Signal()
    # Display settings: repeat, boundary atoms, coordinates in the tables.
    viewChanged = Signal()
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

    @Property(int, notify=sampleChanged)
    def charge(self) -> int:
        return self._logic.charge

    @Property(int, notify=sampleChanged)
    def multiplicity(self) -> int:
        return self._logic.multiplicity

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
        """'cartesian' or 'fractional': how the tables show positions."""
        return self._coordinates

    # Input

    @Slot(str)
    def loadStructure(self, path: str) -> None:
        path = to_local_path(path)
        try:
            self._logic.load(path)
        except (ValueError, OSError) as error:
            reason = error.strerror if isinstance(error, OSError) and error.strerror else error
            self.loadError.emit(f'"{path}" could not be read.\n\n{reason}')
            return
        self._selected, self._anchor = [], None
        self._repeat = (1, 1, 1)
        self._coordinates = self._default_coordinates()
        self._scene = None
        self.sampleChanged.emit()
        self.atomsChanged.emit()
        self.viewChanged.emit()
        self.selectionChanged.emit()
        self.externalSampleChanged.emit()

    # Selection

    @Slot(int, str)
    def selectAtom(self, index: int, mode: str) -> None:
        """Change the selection by clicking an atom in a table, as in a file list.

        'only' (click): this atom alone. 'toggle' (Ctrl-click): add it, or take it out if
        selected. 'range' (Shift-click): the atoms from the last 'only' or 'toggle' atom to
        this one, in index order, replacing the selection. Table rows are the atoms in their
        own cell (image (0, 0, 0)).
        """
        if mode == 'range':
            anchor = self._anchor if self._anchor is not None else index
            step = 1 if index >= anchor else -1
            self._set_selected([(i, HOME) for i in range(anchor, index + step, step)])
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
        indices = selected if index in selected else [index]
        atoms = [self._logic.atoms[i] for i in indices if self._logic.atoms[i].fixed != bool(value)]
        if not atoms:
            return
        for atom in atoms:
            atom.fixed = bool(value)
        self.atomsChanged.emit()

    @Slot(int, int, int)
    def setViewRepeat(self, na: int, nb: int, nc: int) -> None:
        """Draw na × nb × nc cells, each 1 to 4; refused when the cells would hold more than
        SCENE_ATOM_LIMIT atoms (the controls then snap back)."""
        repeat = tuple(max(1, min(_REPEAT_MAX, int(count))) for count in (na, nb, nc))
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
        if value in ('cartesian', 'fractional') and value != self._coordinates:
            self._coordinates = value
            self.viewChanged.emit()

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

    def _default_coordinates(self) -> str:
        return 'fractional' if self._logic.periodic else 'cartesian'


def _rounded(values) -> list:
    return [round(value, _COORDINATE_DECIMALS) for value in values]
