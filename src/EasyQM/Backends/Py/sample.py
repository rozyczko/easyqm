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

_COORDINATE_DECIMALS = 4
_SELECTION_LABELS_SHOWN = 4


class Sample(QObject):
    # The structure was replaced: every property may have changed.
    sampleChanged = Signal()
    # Per-atom data changed (PoC1: the fixed flag only).
    atomsChanged = Signal()
    # The selected atoms, shared by the viewer and the atom tables.
    selectionChanged = Signal()
    loadError = Signal(str)

    # For the other backend parts.
    externalSampleChanged = Signal()

    def __init__(self, logic: Optional[SampleLogic] = None, parent=None):
        super().__init__(parent)
        # The bundled benzene until a structure is loaded from a file.
        self._logic = logic if logic is not None else SampleLogic.benzene()
        self._selected: list[int] = []  # atom indices, in the order they were picked
        self._anchor: Optional[int] = None  # where a range selection starts

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

    @Property(int, notify=sampleChanged)
    def charge(self) -> int:
        return self._logic.charge

    @Property(int, notify=sampleChanged)
    def multiplicity(self) -> int:
        return self._logic.multiplicity

    @Property('QVariantList', notify=sampleChanged)
    def bonds(self) -> list:
        return [list(pair) for pair in self._logic.bonds()]

    @Property('QVariantList', notify=atomsChanged)
    def atoms(self) -> list:
        return [
            {
                'label': atom.label,
                'element': atom.element,
                'x': round(atom.x, _COORDINATE_DECIMALS),
                'y': round(atom.y, _COORDINATE_DECIMALS),
                'z': round(atom.z, _COORDINATE_DECIMALS),
                'fixed': atom.fixed,
            }
            for atom in self._logic.atoms
        ]

    @Property(int, notify=atomsChanged)
    def fixedCount(self) -> int:
        return self._logic.fixed_count

    @Property('QVariantList', notify=selectionChanged)
    def selectedAtoms(self) -> list:
        return list(self._selected)

    @Property(str, notify=selectionChanged)
    def selectionText(self) -> str:
        """'C1, C2' for a few atoms, '7 atoms' for more; empty when nothing is selected."""
        if len(self._selected) > _SELECTION_LABELS_SHOWN:
            return f'{len(self._selected)} atoms'
        return ', '.join(self._logic.atoms[index].label for index in self._selected)

    @Property(str, notify=selectionChanged)
    def selectionMeasurement(self) -> str:
        """For 2, 3 or 4 selected atoms, in the order picked: 'distance = 1.3915 Å',
        'angle = 120.00°' at the middle atom, 'dihedral = −60.00°'; empty otherwise."""
        result = measure([self._logic.atoms[index] for index in self._selected])
        if result is None:
            return ''
        name, value = result
        if value is None:
            return f'{name} undefined'
        if name == 'distance':
            return f'distance = {value:.4f}\u00a0Å'
        value = round(value, 2) + 0.0  # no '−0.00'
        return f'{name} = {value:.2f}°'.replace('-', '\u2212')

    # Input

    @Slot(str)
    def loadXyz(self, path: str) -> None:
        path = to_local_path(path)
        try:
            self._logic.load_xyz(path)
        except (ValueError, OSError) as error:
            reason = error.strerror if isinstance(error, OSError) and error.strerror else error
            self.loadError.emit(f'"{path}" could not be read.\n\n{reason}')
            return
        self._selected, self._anchor = [], None
        self.sampleChanged.emit()
        self.atomsChanged.emit()
        self.selectionChanged.emit()
        self.externalSampleChanged.emit()

    # Selection

    @Slot(int, str)
    def selectAtom(self, index: int, mode: str) -> None:
        """Change the selection by clicking an atom, as in a file list.

        'only' (click): this atom alone. 'toggle' (Ctrl-click): add it, or take it out if
        selected. 'range' (Shift-click): the atoms from the last 'only' or 'toggle' atom to
        this one, in index order, replacing the selection.
        """
        if mode == 'range':
            anchor = self._anchor if self._anchor is not None else index
            step = 1 if index >= anchor else -1
            selected = list(range(anchor, index + step, step))
        elif mode == 'toggle':
            selected = [i for i in self._selected if i != index]
            if len(selected) == len(self._selected):
                selected.append(index)
            self._anchor = index
        else:
            selected = [index]
            self._anchor = index
        if selected != self._selected:
            self._selected = selected
            self.selectionChanged.emit()

    @Slot()
    def clearSelection(self) -> None:
        self._anchor = None
        if self._selected:
            self._selected = []
            self.selectionChanged.emit()

    # Setters

    @Slot(int, bool)
    def setAtomFixed(self, index: int, value: bool) -> None:
        """Fix or free this atom; for a selected atom, every selected atom."""
        indices = self._selected if index in self._selected else [index]
        atoms = [self._logic.atoms[i] for i in indices if self._logic.atoms[i].fixed != bool(value)]
        if not atoms:
            return
        for atom in atoms:
            atom.fixed = bool(value)
        self.atomsChanged.emit()
