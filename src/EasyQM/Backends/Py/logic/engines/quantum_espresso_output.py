# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Reads the numbers the Summary page shows from a pw.x output file (checked on QE 7.5).

The file holds one program after the other, each starting with its banner: pw.x for the
ground state, then ph.x and dynmat.x for phonons, then pw.x again for the band structure
(``bands``) and the density of states (``nscf`` with tetrahedra). Each part is read from its
own program's text.

Energies are converted from Ry to Eh, as the Summary page shows every engine in Eh. The
band edges come from the levels of the last SCF, and of the band structure and DOS runs when
there are any: with N electrons per spin channel the lowest N bands (N/2 without spin) are
filled at every k-point, the valence band maximum is the highest filled level and the
conduction band minimum the lowest empty one. A partly filled band, or edges that overlap,
make the crystal a metal on these k-points; it then has a Fermi energy and no gap.

Frequencies come from the mode table of dynmat.x, which follows ph.x in the same file. The
acoustic sum rule makes three modes zero; those are the translations and are left out.

The band structure's k-points are printed in Cartesian units of 2π/alat; their fractional
coordinates name the points of the path, which `logic.kpath` finds again from the cell the
run printed. The DOS run prints the weight of each k-point, and the curve is drawn from its
levels with those weights.
"""

import math
import re
from typing import Optional

from ..kpath import band_path
from ..results import BandStructure
from ..results import DensityOfStates
from ..results import Frequencies
from ..results import Levels
from ..results import Mode
from ..results import Optimisation
from ..results import Results
from ..sample import Atom
from ..sample import Cell
from .parsing import NUMBER
from .parsing import block
from .parsing import last_float

EH_PER_RY = 0.5
ANGSTROM_PER_BOHR = 0.529177210544
KM_PER_MOL_PER_IR_UNIT = 42.2561  # dynmat.x IR activity, (D/Å)²/amu, in km/mol

# The k-point header of an nscf run with tetrahedra: the DOS run.
TETRAHEDRA = re.compile(r'\(tetrahedron method\)')

_PROGRAM = re.compile(r'^\s*Program (\w+) v\.', re.MULTILINE)
_ENERGY = re.compile(rf'^!\s+total energy\s+=\s+({NUMBER}) Ry', re.MULTILINE)
_FERMI = re.compile(rf'the (?:spin up/dw )?Fermi energ(?:y is|ies are)\s+({NUMBER})')
_ELECTRONS = re.compile(rf'number of electrons\s+=\s+({NUMBER})(?:\s+\(up:\s+({NUMBER}), down:\s+({NUMBER})\))?')
_ALAT = re.compile(rf'lattice parameter \(alat\)\s+=\s+({NUMBER})\s+a\.u\.')
_AXIS = re.compile(rf'^\s+a\(([123])\) = \(\s*({NUMBER})\s+({NUMBER})\s+({NUMBER})\s*\)', re.MULTILINE)
_SITE = re.compile(rf'^\s+\d+\s+([A-Z][a-z]?)\S*\s+tau\(\s*\d+\)\s+=\s+\(\s*({NUMBER})\s*({NUMBER})\s*({NUMBER})')
_POSITION = re.compile(rf'^([A-Z][a-z]?)\S*\s+({NUMBER})\s+({NUMBER})\s+({NUMBER})')
_CELL = re.compile(rf'^CELL_PARAMETERS \((angstrom|bohr|alat=\s*{NUMBER})\)')
_VECTOR = re.compile(rf'^\s*({NUMBER})\s+({NUMBER})\s+({NUMBER})\s*$')
_KPOINT = re.compile(r'^\s*k =(.*?)\(\s*\d+ PWs\)\s+bands \(ev\):.*$', re.MULTILINE)
_WEIGHT = re.compile(rf'^\s+k\(\s*\d+\) = \(\s*{NUMBER}\s*{NUMBER}\s*{NUMBER}\), wk =\s*({NUMBER})')
_BANDS_END = re.compile(r'the (?:spin up/dw )?Fermi energ|highest occupied|^!', re.MULTILINE)
_MODE = re.compile(rf'^\s*(\d+)\s+({NUMBER})\s+{NUMBER}(?:\s+({NUMBER}))?')
_SCF_END = 'End of self-consistent calculation'
_NSCF_END = 'End of band structure calculation'
_OPTIMISATION = 'BFGS Geometry Optimization'
_CONVERGED = 'bfgs converged'
_KINK = 0.9998  # cosine between two steps of the path below which it turns at an unnamed point


def parse(output: str) -> Results:
    runs = _programs(output)
    pw = [text for name, text in runs if name == 'PWSCF']
    ground_state = pw[0] if pw else output
    phonons = ''.join(text for name, text in runs if name in ('PHONON', 'DYNMAT'))
    bands_text, dos_text = _non_scf_runs(pw[1:])

    energies = [float(value) * EH_PER_RY for value in _ENERGY.findall(ground_state)]
    band_structure = _band_structure(bands_text) if bands_text else None
    density_of_states = _density_of_states(dos_text) if dos_text else None
    sources = [(_levels(ground_state, _SCF_END), _filled(ground_state))]
    sources += [(part.levels, part.filled) for part in (band_structure, density_of_states) if part is not None]
    valence, conduction = _band_edges(sources)
    fermi = density_of_states.fermi_energy if density_of_states and density_of_states.fermi_energy is not None else None
    return Results(
        final_energy=energies[-1] if energies else None,
        homo=valence,
        lumo=conduction,
        fermi_energy=fermi if fermi is not None else last_float(_FERMI, ground_state),
        optimisation=_optimisation(ground_state, energies),
        frequencies=_frequencies(phonons),
        crystal=True,
        band_structure=band_structure,
        density_of_states=density_of_states,
    )


def _programs(output: str) -> list[tuple[str, str]]:
    """(program name, its text) in order; text before the first banner goes with the first."""
    starts = list(_PROGRAM.finditer(output))
    if not starts:
        return []
    ends = [match.start() for match in starts[1:]] + [len(output)]
    runs = [(match.group(1), output[match.start() : end]) for match, end in zip(starts, ends)]
    return [(runs[0][0], output[: starts[0].start()] + runs[0][1]), *runs[1:]]


def _non_scf_runs(runs: list[str]) -> tuple[str, str]:
    """(band structure run, DOS run) among the pw.x runs after the ground state; '' for each
    missing. The DOS run comes second, and alone it is told by its tetrahedra."""
    runs = [text for text in runs if _NSCF_END in text]
    if len(runs) >= 2:
        return runs[0], runs[1]
    if runs and TETRAHEDRA.search(runs[0]):
        return '', runs[0]
    return (runs[0], '') if runs else ('', '')


# Levels and band edges


def _filled(output: str) -> Optional[list[int]]:
    """Filled bands per spin channel; None without the electron count or when one is partly filled."""
    electrons = _ELECTRONS.search(output)
    if electrons is None:
        return None
    counts = [float(electrons.group(1)) / 2] if electrons.group(2) is None else [float(electrons.group(2)),
                                                                                    float(electrons.group(3))]
    if any(abs(count - round(count)) > 1e-6 for count in counts):
        return None  # a partly filled band
    return [round(count) for count in counts]


def _levels(output: str, end: str) -> Levels:
    """The levels printed after the last `end`: channel -> k-point -> bands (eV)."""
    return [[levels for _, levels in channel] for channel in _channels(output, end)]


def _channels(output: str, end: str) -> list[list[tuple[tuple[float, ...], list[float]]]]:
    """(k in Cartesian units of 2π/alat, levels in eV) per k-point, per spin channel."""
    start = output.rfind(end)
    if start < 0:
        return []
    section = output[start:]
    stop = _BANDS_END.search(section)
    return [_kpoint_levels(text) for text in section[: stop.start() if stop else None].split('SPIN DOWN')]


def _kpoint_levels(text: str) -> list[tuple[tuple[float, ...], list[float]]]:
    """The k-point and the eigenvalues (eV) printed under each 'k = … bands (ev):' line."""
    headers = list(_KPOINT.finditer(text))
    result = []
    for header, after in zip(headers, [match.start() for match in headers[1:]] + [len(text)]):
        k = tuple(float(value) for value in re.findall(r'-?\d+\.\d+', header.group(1)))
        values = []
        for line in text[header.end() : after].splitlines():
            if re.search('[A-Za-z]', line):  # 'occupation numbers' and the like
                break
            values += [float(value) for value in re.findall(r'-?\d+\.\d+', line)]
        result.append((k, values))
    return result


def _band_edges(sources: list[tuple[Levels, Optional[list[int]]]]) -> tuple[Optional[float], Optional[float]]:
    """Valence band maximum and conduction band minimum over every source's levels."""
    valence, conduction = float('-inf'), float('inf')
    for levels, filled in sources:
        if not levels:
            continue
        if filled is None or len(filled) != len(levels):
            return None, None
        for channel, count in zip(levels, filled):
            for energies in channel:
                if count < 1 or len(energies) <= count:
                    return None, None  # no empty band printed
                valence, conduction = max(valence, energies[count - 1]), min(conduction, energies[count])
    if conduction <= valence or valence == float('-inf'):
        return None, None
    return valence, conduction


# Band structure and density of states


def _band_structure(output: str) -> Optional[BandStructure]:
    channels = _channels(output, _NSCF_END)
    alat = _ALAT.search(output)
    axes = {int(match.group(1)) - 1: tuple(float(value) for value in match.groups()[1:]) for match in _AXIS.finditer(output)}
    if not channels or not channels[0] or alat is None or len(axes) != 3:
        return None
    scale = float(alat.group(1)) * ANGSTROM_PER_BOHR  # Å
    axes = [axes[i] for i in range(3)]
    path = band_path(Cell(tuple(tuple(value * scale for value in axis) for axis in axes)))
    kpoints = [k for k, _ in channels[0]]
    names = [path.label(tuple(sum(k[j] * axis[j] for j in range(3)) for axis in axes)) for k in kpoints]

    distances, ticks, starts = [0.0], [], [0]
    if names[0]:
        ticks.append((0.0, names[0]))
    for i in range(1, len(kpoints)):
        step = [a - b for a, b in zip(kpoints[i], kpoints[i - 1])]
        if names[i] and names[i - 1]:  # two named points in a row: a jump between branches
            distances.append(distances[-1])
            starts.append(i)
            ticks[-1] = (distances[-1], f'{ticks[-1][1]}|{names[i]}')
            continue
        distances.append(distances[-1] + math.sqrt(sum(x * x for x in step)) * 2 * math.pi / scale)
        if names[i] or (i + 1 < len(kpoints) and _turns(step, kpoints[i + 1], kpoints[i])):
            ticks.append((distances[-1], names[i]))
    levels = [[energies for _, energies in channel] for channel in channels]
    return BandStructure(distances, levels, ticks, starts, _filled(output), path.lattice, kpoints)


def _turns(step, following, current) -> bool:
    after = [a - b for a, b in zip(following, current)]
    lengths = math.sqrt(sum(x * x for x in step)) * math.sqrt(sum(x * x for x in after))
    return lengths > 0 and sum(a * b for a, b in zip(step, after)) / lengths < _KINK


def _density_of_states(output: str) -> Optional[DensityOfStates]:
    levels = _levels(output, _NSCF_END)
    weights = [float(match.group(1)) for match in block(output.splitlines(), r'cart\. coord\. in units 2pi/alat', _WEIGHT)]
    if not levels or not levels[0] or not weights:
        return None
    return DensityOfStates(levels, weights, last_float(_FERMI, output), _filled(output))


# Phonons


def _ir(value: Optional[str]) -> Optional[float]:
    return None if value is None else float(value) * KM_PER_MOL_PER_IR_UNIT


def _frequencies(output: str) -> Optional[Frequencies]:
    rows = block(output.splitlines(), r'^# mode', _MODE)
    if not rows:
        return None
    modes = [Mode(int(match.group(1)), float(match.group(2)), _ir(match.group(3))) for match in rows]
    acoustic = sorted(modes, key=lambda mode: abs(mode.frequency))[:3]
    return Frequencies(modes=[mode for mode in modes if mode not in acoustic])


# Geometry optimisation


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
        final_cell=_final_cell(lines),
    )


def _final_cell(lines: list[str]) -> Optional[Cell]:
    """The cell of the last vc-relax step; a relax at fixed cell prints none."""
    headers = [match for line in lines if (match := _CELL.match(line))]
    if not headers:
        return None
    unit = headers[-1].group(1)
    if unit == 'angstrom':
        scale = 1.0
    elif unit == 'bohr':
        scale = ANGSTROM_PER_BOHR
    else:
        scale = float(unit.split('=')[1]) * ANGSTROM_PER_BOHR
    rows = block(lines, _CELL.pattern, _VECTOR)
    if len(rows) != 3:
        return None  # stopped while printing it
    return Cell(tuple(tuple(float(value) * scale for value in row.groups()) for row in rows))


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
