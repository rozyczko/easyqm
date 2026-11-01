# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Reads the numbers the Summary page shows from a pw.x output file (checked on QE 7.5).

Energies are converted from Ry to Eh, as the Summary page shows every engine in Eh. The
band edges come from the eigenvalues of the last SCF: with N electrons per spin channel
the lowest N bands (N/2 without spin) are filled at every k-point, the valence band
maximum is the highest filled level and the conduction band minimum the lowest empty one.
A partly filled band, or edges that overlap, make the crystal a metal on this k-point grid;
it then has a Fermi energy and no gap.

Frequencies come from the mode table of dynmat.x, which follows ph.x in the same file. The
acoustic sum rule makes three modes zero; those are the translations and are left out.
"""

import re
from typing import Optional

from ..results import Frequencies
from ..results import Mode
from ..results import Optimisation
from ..results import Results
from ..sample import Atom
from .parsing import NUMBER
from .parsing import block
from .parsing import last_float

EH_PER_RY = 0.5
ANGSTROM_PER_BOHR = 0.529177210544
KM_PER_MOL_PER_IR_UNIT = 42.2561  # dynmat.x IR activity, (D/Å)²/amu, in km/mol

_ENERGY = re.compile(rf'^!\s+total energy\s+=\s+({NUMBER}) Ry', re.MULTILINE)
_FERMI = re.compile(rf'the (?:spin up/dw )?Fermi energ(?:y is|ies are)\s+({NUMBER})')
_ELECTRONS = re.compile(rf'number of electrons\s+=\s+({NUMBER})(?:\s+\(up:\s+({NUMBER}), down:\s+({NUMBER})\))?')
_ALAT = re.compile(rf'lattice parameter \(alat\)\s+=\s+({NUMBER})\s+a\.u\.')
_SITE = re.compile(rf'^\s+\d+\s+([A-Z][a-z]?)\S*\s+tau\(\s*\d+\)\s+=\s+\(\s*({NUMBER})\s*({NUMBER})\s*({NUMBER})')
_POSITION = re.compile(rf'^([A-Z][a-z]?)\S*\s+({NUMBER})\s+({NUMBER})\s+({NUMBER})')
_KPOINT = re.compile(r'^.*bands \(ev\):.*$', re.MULTILINE)
_BANDS_END = re.compile(r'the (?:spin up/dw )?Fermi energ|highest occupied|^!', re.MULTILINE)
_MODE = re.compile(rf'^\s*(\d+)\s+({NUMBER})\s+{NUMBER}(?:\s+({NUMBER}))?')
_PHONON_START = 'Program PHONON'
_OPTIMISATION = 'BFGS Geometry Optimization'
_CONVERGED = 'bfgs converged'


def parse(output: str) -> Results:
    # ph.x prints SCF sections of its own; the ground state is pw.x's part.
    ground_state, _, phonons = output.partition(_PHONON_START)
    energies = [float(value) * EH_PER_RY for value in _ENERGY.findall(ground_state)]
    valence, conduction = _band_edges(ground_state)
    return Results(
        final_energy=energies[-1] if energies else None,
        homo=valence,
        lumo=conduction,
        fermi_energy=last_float(_FERMI, ground_state),
        optimisation=_optimisation(ground_state, energies),
        frequencies=_frequencies(phonons),
        crystal=True,
    )


def _ir(value: Optional[str]) -> Optional[float]:
    return None if value is None else float(value) * KM_PER_MOL_PER_IR_UNIT


def _frequencies(output: str) -> Optional[Frequencies]:
    rows = block(output.splitlines(), r'^# mode', _MODE)
    if not rows:
        return None
    modes = [Mode(int(match.group(1)), float(match.group(2)), _ir(match.group(3))) for match in rows]
    acoustic = sorted(modes, key=lambda mode: abs(mode.frequency))[:3]
    return Frequencies(modes=[mode for mode in modes if mode not in acoustic])


def _band_edges(output: str) -> tuple[Optional[float], Optional[float]]:
    electrons = _ELECTRONS.search(output)
    start = output.rfind('End of self-consistent calculation')
    if electrons is None or start < 0:
        return None, None
    section = output[start:]
    end = _BANDS_END.search(section)
    channels = section[: end.start() if end else None].split('SPIN DOWN')
    if electrons.group(2) is None:
        filled = [float(electrons.group(1)) / 2]
    else:
        filled = [float(electrons.group(2)), float(electrons.group(3))]
    if len(channels) != len(filled):
        return None, None
    valence, conduction = float('-inf'), float('inf')
    for text, count in zip(channels, filled):
        bands = round(count)
        if abs(count - bands) > 1e-6 or bands < 1:
            return None, None  # a partly filled band
        for levels in _kpoint_levels(text):
            if len(levels) <= bands:
                return None, None  # no empty band printed
            valence, conduction = max(valence, levels[bands - 1]), min(conduction, levels[bands])
    if conduction <= valence or valence == float('-inf'):
        return None, None
    return valence, conduction


def _kpoint_levels(text: str) -> list[list[float]]:
    """The eigenvalues (eV) printed under each 'k = … bands (ev):' line."""
    levels = []
    for chunk in _KPOINT.split(text)[1:]:
        values = []
        for line in chunk.splitlines():
            if re.search('[A-Za-z]', line):  # 'occupation numbers' and the like
                break
            values += [float(value) for value in re.findall(r'-?\d+\.\d+', line)]
        levels.append(values)
    return levels


def _optimisation(output: str, energies: list[float]) -> Optional[Optimisation]:
    if _OPTIMISATION not in output:
        return None
    lines = output.splitlines()
    final = [_atom(match, index) for index, match in enumerate(block(lines, r'^ATOMIC_POSITIONS \(angstrom\)', _POSITION))]
    if not final:
        return None  # stopped before the first step
    return Optimisation(
        converged=_CONVERGED in output,
        cycles=len(energies),
        energies=energies,
        initial=_initial_atoms(output, lines),
        final=final,
    )


def _initial_atoms(output: str, lines: list[str]) -> list[Atom]:
    """The input positions, printed once at the start in units of the lattice parameter."""
    alat = _ALAT.search(output)
    first = next((i for i, line in enumerate(lines) if 'positions (alat units)' in line), None)
    if alat is None or first is None:
        return []
    scale = float(alat.group(1)) * ANGSTROM_PER_BOHR
    atoms = []
    for line in lines[first + 1 :]:
        match = _SITE.match(line)
        if not match:
            break
        element, x, y, z = match.groups()
        atoms.append(Atom(f'{element}{len(atoms) + 1}', element, float(x) * scale, float(y) * scale, float(z) * scale))
    return atoms


def _atom(match: re.Match, index: int) -> Atom:
    element, x, y, z = match.groups()
    return Atom(f'{element}{index + 1}', element, float(x), float(y), float(z))
