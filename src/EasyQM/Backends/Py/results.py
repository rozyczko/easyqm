# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Summary page backend part: the results of the last job, formatted for the Results tab.

Only what the output contains is offered: a stat tile, the optimisation card or the
frequencies card appears when its numbers were found, whatever was ticked.
"""

from typing import Optional

from PySide6.QtCore import Property
from PySide6.QtCore import QObject
from PySide6.QtCore import Signal

from .logic.results import HARTREE_TO_KCAL_PER_MOL
from .logic.results import Results as ResultsLogic
from .logic.results import bonds_and_angles

# Keeps a number and its unit on one line in the narrow tiles.
_KCAL_PER_MOL = '\u00a0kcal/\u2060mol'  # no-break space, word joiner

_NO_JOB = 'No results yet. Run the workflow on the Method page.'
_RUNNING = 'The results appear here when the job has ended.'
_NOTHING_FOUND = 'The output of the last job holds no results.'


def _number(value: float, spec: str) -> str:
    """Formatted with a typographic minus sign."""
    return format(value, spec).replace('-', '−')


def _tile(title: str, value: str, detail: str = '', tone: str = '') -> dict:
    # tone: '' for plain, 'good', 'bad' or 'warning' for a coloured value
    return {'title': title, 'value': value, 'detail': detail, 'tone': tone}


class Results(QObject):
    resultsChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._results = ResultsLogic()
        self._method_label = ''
        self._placeholder = _NO_JOB

    # Relay targets (plain Python)

    def clear(self, method_label: str) -> None:
        """A job started: forget the old results and remember how this one is computed."""
        self._results = ResultsLogic()
        self._method_label = method_label
        self._placeholder = _RUNNING
        self.resultsChanged.emit()

    def reset(self) -> None:
        """No job has run: the start-up placeholder (for PyBackend.reset)."""
        self._results = ResultsLogic()
        self._method_label = ''
        self._placeholder = _NO_JOB
        self.resultsChanged.emit()

    def set_results(self, results: ResultsLogic) -> None:
        self._results = results
        self._placeholder = _NOTHING_FOUND if results.empty else ''
        self.resultsChanged.emit()

    # Overview

    @Property(bool, notify=resultsChanged)
    def available(self) -> bool:
        return not self._results.empty

    @Property(str, notify=resultsChanged)
    def placeholder(self) -> str:
        return self._placeholder

    @Property('QVariantList', notify=resultsChanged)
    def tiles(self) -> list:
        results = self._results
        optimisation, frequencies = results.optimisation, results.frequencies
        tiles = []
        if results.final_energy is not None:
            tiles.append(_tile('Final energy (Eh)', _number(results.final_energy, '.6f'), self._method_label))
        if optimisation is not None:
            detail = f'{optimisation.cycles} steps'
            if optimisation.energy_change is not None:
                change = optimisation.energy_change * HARTREE_TO_KCAL_PER_MOL
                detail += f' · ΔE = {_number(change, "+.2f")}{_KCAL_PER_MOL}'
            converged = optimisation.converged
            tiles.append(
                _tile('Optimisation', 'Converged' if converged else 'Not converged', detail, 'good' if converged else 'bad')
            )
        if frequencies is not None:
            count = frequencies.imaginary_count
            detail = 'true minimum' if count == 0 else 'not a minimum'
            if frequencies.zero_point_energy is not None:
                detail += f' · ZPE {frequencies.zero_point_energy * HARTREE_TO_KCAL_PER_MOL:.1f}{_KCAL_PER_MOL}'
            tiles.append(_tile('Imaginary modes', str(count), detail, '' if count == 0 else 'warning'))
        if results.gap is not None and not results.crystal:
            detail = f'HOMO {_number(results.homo, ".2f")} · LUMO {_number(results.lumo, ".2f")}'
            tiles.append(_tile('HOMO–LUMO gap (eV)', f'{results.gap:.2f}', detail))
        elif results.gap is not None:
            # From the SCF k-points only, so a band edge between them is missed.
            detail = f'VBM {_number(results.homo, ".2f")} · CBM {_number(results.lumo, ".2f")} · on the k-point grid'
            tiles.append(_tile('Band gap (eV)', f'{results.gap:.2f}', detail))
        elif results.fermi_energy is not None:
            tiles.append(_tile('Fermi energy (eV)', _number(results.fermi_energy, '.2f'), 'metallic on the k-point grid'))
        if results.dipole is not None:
            where = 'at the final geometry' if optimisation is not None else 'at the input geometry'
            tiles.append(_tile('Dipole moment (D)', f'{results.dipole:.3f}', where))
        if frequencies is not None and frequencies.gibbs_free_energy is not None:
            conditions = []
            if frequencies.temperature is not None:
                conditions.append(f'{frequencies.temperature:g} K')
            if frequencies.pressure is not None:
                conditions.append(f'{frequencies.pressure:g} atm')
            tiles.append(_tile('Gibbs free energy (Eh)', _number(frequencies.gibbs_free_energy, '.6f'), ', '.join(conditions)))
        return tiles

    # Geometry optimisation card

    @Property(bool, notify=resultsChanged)
    def hasOptimisation(self) -> bool:
        return self._results.optimisation is not None

    @Property('QVariantList', notify=resultsChanged)
    def geometryRows(self) -> list:
        """Bonds and angles side by side, as in the mock-up: row i holds bond i and angle i."""
        optimisation = self._results.optimisation
        if optimisation is None or len(optimisation.initial) != len(optimisation.final):
            return []
        bonds, angles = bonds_and_angles(optimisation.initial, optimisation.final)
        rows = []
        for index in range(max(len(bonds), len(angles))):
            bond = bonds[index] if index < len(bonds) else None
            angle = angles[index] if index < len(angles) else None
            rows.append(
                {
                    'bond': bond.label if bond else '',
                    'bondInitial': f'{bond.initial:.4f}' if bond else '',
                    'bondFinal': f'{bond.final:.4f}' if bond else '',
                    'bondChange': _number(bond.final - bond.initial, '+.4f') if bond else '',
                    'angle': angle.label if angle else '',
                    'angleFinal': f'{angle.final:.2f}' if angle else '',
                }
            )
        return rows

    @Property('QVariantList', notify=resultsChanged)
    def convergenceRows(self) -> list:
        optimisation = self._results.optimisation
        if optimisation is None:
            return []
        return [
            {
                'criterion': criterion.name,
                'value': _number(criterion.value, '.2e'),
                'tolerance': f'{criterion.tolerance:.1e}',
                'met': criterion.met,
            }
            for criterion in optimisation.criteria
        ]

    # Vibrational frequencies card

    @Property(bool, notify=resultsChanged)
    def hasFrequencies(self) -> bool:
        return self._results.frequencies is not None

    @Property(bool, notify=resultsChanged)
    def hasIr(self) -> bool:
        frequencies = self._results.frequencies
        return frequencies is not None and frequencies.has_ir

    @Property(bool, notify=resultsChanged)
    def hasRaman(self) -> bool:
        frequencies = self._results.frequencies
        return frequencies is not None and frequencies.has_raman

    @Property('QVariantList', notify=resultsChanged)
    def modes(self) -> list:
        frequencies = self._results.frequencies
        if frequencies is None:
            return []
        return [
            {
                'number': mode.number,
                'frequency': mode.frequency,
                'frequencyText': _number(mode.frequency, '.2f'),
                'imaginary': mode.frequency < 0,
                'irIntensity': _value(mode.ir_intensity),
                'irText': _text(mode.ir_intensity),
                'ramanActivity': _value(mode.raman_activity),
                'ramanText': _text(mode.raman_activity),
            }
            for mode in frequencies.modes
        ]


def _value(number: Optional[float]) -> float:
    return 0.0 if number is None else number


def _text(number: Optional[float]) -> str:
    return '–' if number is None else f'{number:.2f}'
