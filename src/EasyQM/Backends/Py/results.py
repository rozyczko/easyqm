# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Summary page backend part: the results of the last job, formatted for the Results tab.

Only what the output contains is offered: a stat tile, the optimisation, frequencies or
excited-states card appears when its numbers were found, whatever was ticked.
"""

import math
from typing import Optional

from PySide6.QtCore import Property
from PySide6.QtCore import QObject
from PySide6.QtCore import Signal
from PySide6.QtCore import Slot

from .logic.results import HARTREE_TO_KCAL_PER_MOL
from .logic.results import Results as ResultsLogic
from .logic.results import bonds_and_angles
from .logic.sample import MULTIPLICITY_NAMES

# Keeps a number and its unit on one line in the narrow tiles.
_KCAL_PER_MOL = '\u00a0kcal/\u2060mol'  # no-break space, word joiner

DOS_BROADENING = 0.1  # eV, the Gaussian width the DOS is drawn with until changed
DOS_BROADENING_LIMITS = (0.01, 1.0)
DOS_POINTS = 600  # energies the DOS curve is drawn at, at least
DOS_STEP = 0.5  # broadenings between two of them at most: a narrow peak falls between wider steps
DOS_MAX_POINTS = 10000  # for the plot; past this the step grows again
# The window the bands and DOS are drawn in, relative to the reference energy: deep core-like
# levels are left out below; above, it reaches the highest level computed at any k-point.
ENERGY_BELOW = 20.0  # eV
ENERGY_ABOVE = 10.0  # without bands or DOS
_WINDOW_MARGIN = 0.5

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

    dosBroadeningChanged = Signal()
    dosChanged = Signal()  # new results or a new broadening

    def __init__(self, parent=None):
        super().__init__(parent)
        self._results = ResultsLogic()
        self._method_label = ''
        self._placeholder = _NO_JOB
        self._broadening = DOS_BROADENING

    # Relay targets (plain Python)

    def clear(self, method_label: str) -> None:
        """A job started: forget the old results and remember how this one is computed."""
        self._results = ResultsLogic()
        self._method_label = method_label
        self._placeholder = _RUNNING
        self.resultsChanged.emit()
        self.dosChanged.emit()

    def reset(self) -> None:
        """No job has run: the start-up placeholder (for PyBackend.reset)."""
        self._results = ResultsLogic()
        self._method_label = ''
        self._placeholder = _NO_JOB
        self.resultsChanged.emit()
        self.dosChanged.emit()

    def set_results(self, results: ResultsLogic) -> None:
        self._results = results
        self._placeholder = _NOTHING_FOUND if results.empty else ''
        self.resultsChanged.emit()
        self.dosChanged.emit()

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
            # From the k-points of the job only, so a band edge between them is missed.
            detail = f'VBM {_number(results.homo, ".2f")} · CBM {_number(results.lumo, ".2f")} · {self._sampled()}'
            character = self._gap_character()
            if character:
                detail += f' · {character}'
            tiles.append(_tile('Band gap (eV)', f'{results.gap:.2f}', detail))
        elif results.fermi_energy is not None:
            tiles.append(_tile('Fermi energy (eV)', _number(results.fermi_energy, '.2f'), f'metallic {self._sampled()}'))
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
        if results.excited_states is not None:
            lowest = min(results.excited_states.states, key=lambda state: state.energy)
            detail = [results.excited_states.method]
            if lowest.wavelength is not None:
                detail.append(f'{lowest.wavelength:.0f} nm')
            if lowest.oscillator_strength is not None:
                detail.append(f'f = {_strength(lowest.oscillator_strength)}')
            tiles.append(_tile('Lowest excitation (eV)', f'{lowest.energy:.3f}', ' · '.join(detail)))
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

    # Excited states card

    @Property(bool, notify=resultsChanged)
    def hasExcitedStates(self) -> bool:
        return self._results.excited_states is not None

    @Property(str, notify=resultsChanged)
    def excitedStatesMethod(self) -> str:
        excited = self._results.excited_states
        return excited.method if excited is not None else ''

    @Property(bool, notify=resultsChanged)
    def hasOscillatorStrengths(self) -> bool:
        """Open-shell EOM-CCSD comes without them."""
        excited = self._results.excited_states
        return excited is not None and any(state.oscillator_strength is not None for state in excited.states)

    @Property('QVariantList', notify=resultsChanged)
    def excitations(self) -> list:
        """One row per state, in the engine's order; `key` tells apart a singlet and a triplet
        of the same number."""
        excited = self._results.excited_states
        if excited is None:
            return []
        return [
            {
                'key': index,
                'state': state.state,
                'spin': MULTIPLICITY_NAMES[state.multiplicity - 1] if state.multiplicity else '–',
                'energy': state.energy,
                'energyText': f'{state.energy:.3f}',
                'wavelength': _value(state.wavelength),
                'wavelengthText': '–' if state.wavelength is None else f'{state.wavelength:.1f}',
                'strength': _nonnegative(_value(state.oscillator_strength)),
                'strengthText': '–' if state.oscillator_strength is None else _strength(state.oscillator_strength),
            }
            for index, state in enumerate(excited.states)
        ]

    # Band structure and density of states card

    @Property(bool, notify=resultsChanged)
    def hasBandStructure(self) -> bool:
        return self._results.band_structure is not None

    @Property(bool, notify=resultsChanged)
    def hasDensityOfStates(self) -> bool:
        return self._results.density_of_states is not None

    @Property(str, notify=resultsChanged)
    def energyReference(self) -> str:
        """What the energies of the card are measured from: 'VBM', 'E_F', or '' (absolute)."""
        results = self._results
        return 'VBM' if results.gap is not None else 'E_F' if results.fermi_energy is not None else ''

    @Property('QVariantMap', notify=resultsChanged)
    def energyWindow(self) -> dict:
        """{min, max} in eV from the reference: the energies both plots show."""
        low, high = self._window()
        return {'min': low, 'max': high}

    @Property('QVariantMap', notify=resultsChanged)
    def bandStructure(self) -> dict:
        """{lattice, distances (Å⁻¹), starts, ticks: [{x, label}], levels}: `levels[channel][k]`
        the bands at k-point k in eV from the reference, as many at every k-point; a branch of
        the path runs from each start to the next."""
        bands = self._results.band_structure
        if bands is None:
            return {}
        reference = self._reference()
        count = min(len(energies) for channel in bands.levels for energies in channel)
        return {
            'lattice': bands.lattice,
            'distances': bands.distances,
            'starts': bands.starts,
            'ticks': [{'x': x, 'label': label} for x, label in bands.ticks],
            'levels': [[[energy - reference for energy in energies[:count]] for energies in channel]
                       for channel in bands.levels],
        }

    @Property(str, notify=resultsChanged)
    def bandGapText(self) -> str:
        """The gap along the path, for the card: 'Indirect gap 0.61 eV: VBM at Γ, CBM on Γ–X'."""
        bands = self._results.band_structure
        if bands is None:
            return ''
        edges = bands.edges()
        if edges is None:
            return 'Metallic along the path: bands cross the Fermi energy.' if bands.filled is None else ''
        valence, conduction = edges
        gap = conduction.energy - valence.energy
        direct = bands.direct_point(edges)
        if direct is not None:
            return f'Direct gap of {gap:.2f} eV at {_place(bands, direct)}.'
        return (f'Indirect gap of {gap:.2f} eV along the path: VBM at {_place(bands, valence.k)}, '
                f'CBM at {_place(bands, conduction.k)}.')

    @Property(float, notify=dosBroadeningChanged)
    def dosBroadening(self) -> float:
        return self._broadening

    @Slot(float)
    def setDosBroadening(self, value: float) -> None:
        low, high = DOS_BROADENING_LIMITS
        value = min(max(float(value), low), high)
        if value != self._broadening:
            self._broadening = value
            self.dosBroadeningChanged.emit()
            self.dosChanged.emit()

    @Property(int, notify=resultsChanged)
    def dosKpoints(self) -> int:
        dos = self._results.density_of_states
        return len(dos.weights) if dos is not None else 0

    @Property('QVariantMap', notify=dosChanged)
    def densityOfStates(self) -> dict:
        """{energies, values, max}: states per eV per cell over the energy window, from the
        reference; recomputed when the broadening changes."""
        dos = self._results.density_of_states
        if dos is None:
            return {}
        low, high = self._window()
        reference = self._reference()
        # At least DOS_POINTS, and close enough that the narrowest Gaussian keeps its shape.
        points = max(DOS_POINTS, min(DOS_MAX_POINTS, math.ceil((high - low) / (self._broadening * DOS_STEP)) + 1))
        step = (high - low) / (points - 1)
        energies = [low + i * step for i in range(points)]
        values = dos.curve([energy + reference for energy in energies], self._broadening)
        return {'energies': energies, 'values': values, 'max': max(values, default=0.0)}

    def _reference(self) -> float:
        results = self._results
        if results.gap is not None:
            return results.homo
        return results.fermi_energy if results.fermi_energy is not None else 0.0

    def _window(self) -> tuple[float, float]:
        """From the lowest computed level (at most ENERGY_BELOW under the reference) to the highest
        level of the band structure at any k-point, or of the DOS grid without a band structure."""
        results = self._results
        levels = [part.levels for part in (results.band_structure, results.density_of_states) if part is not None]
        if not levels:
            return -ENERGY_BELOW, ENERGY_ABOVE
        reference = self._reference()
        lowest = min(min(energies) for channels in levels for channel in channels for energies in channel)
        top = max(max(energies) for channel in levels[0] for energies in channel)
        low = max(lowest - reference - _WINDOW_MARGIN, -ENERGY_BELOW)
        return low, max(top - reference, low + 1.0)

    def _sampled(self) -> str:
        results = self._results
        if results.band_structure is not None or results.density_of_states is not None:
            return 'on the path and k-point grids'
        return 'on the k-point grid'

    def _gap_character(self) -> str:
        """'direct' or 'indirect' along the path, when the path holds both band edges."""
        results, bands = self._results, self._results.band_structure
        edges = bands.edges() if bands is not None else None
        if edges is None or (edges[0].energy, edges[1].energy) != (results.homo, results.lumo):
            return ''
        return 'direct' if bands.direct_point(edges) is not None else 'indirect'


def _place(bands, k: int) -> str:
    where = bands.location(k)
    return where if '–' not in where else f'a point on {where}'


def _strength(value: float) -> str:
    """An oscillator strength; non-Hermitian methods give tiny negative ones for dark states."""
    return f'{_nonnegative(value):.4f}'


def _nonnegative(value: float) -> float:
    return max(value, 0.0) + 0.0  # + 0.0: max(-0.0, 0.0) is -0.0


def _value(number: Optional[float]) -> float:
    return 0.0 if number is None else number


def _text(number: Optional[float]) -> str:
    return '–' if number is None else f'{number:.2f}'
