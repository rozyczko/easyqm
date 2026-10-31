# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Sample page backend part: the QML-facing proxy of `logic.sample.Sample`."""

from typing import Optional

from PySide6.QtCore import Property
from PySide6.QtCore import QObject
from PySide6.QtCore import Signal
from PySide6.QtCore import Slot

from .logic.sample import Sample as SampleLogic

_COORDINATE_DECIMALS = 4


class Sample(QObject):
    # The structure was replaced: every property may have changed.
    sampleChanged = Signal()
    # Per-atom data changed (PoC1: the fixed flag only).
    atomsChanged = Signal()

    # For the other backend parts.
    externalSampleChanged = Signal()

    def __init__(self, logic: Optional[SampleLogic] = None, parent=None):
        super().__init__(parent)
        # PoC1 starts with the bundled benzene; loading structures comes with ASE.
        self._logic = logic if logic is not None else SampleLogic.benzene()

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

    # Setters

    @Slot(int, bool)
    def setAtomFixed(self, index: int, value: bool) -> None:
        atom = self._logic.atoms[index]
        if atom.fixed == bool(value):
            return
        atom.fixed = bool(value)
        self.atomsChanged.emit()
