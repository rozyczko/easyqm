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
ground state started from: the one the bands input was written for. Distances, ticks and
jumps between branches come from `logic.kpath.path_axis`, which the CASTEP parser shares. The
DOS run prints the weight of each k-point, and the curve is drawn from its levels with those
weights.
"""

import re
from typing import Optional

from ..kpath import band_path
from ..kpath import path_axis
from ..results import BandStructure
from ..results import DensityOfStates
from ..results import Frequencies
from ..results import Levels
from ..results import Mode
from ..results import Optimisation
from ..results import Results
from ..results import sampled_band_edges
from ..sample import Atom
from ..sample import Cell
from .parsing import ANGSTROM_PER_BOHR
from .parsing import KM_PER_MOL_PER_IR_UNIT
from .parsing import NUMBER
from .parsing import block
from .parsing import last_float

EH_PER_RY = 0.5

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


def parse(output: str) -> Results:
    runs = _programs(output)
    pw = [text for name, text in runs if name == 'PWSCF']
    ground_state = pw[0] if pw else output
    phonons = ''.join(text for name, text in runs if name in ('PHONON', 'DYNMAT'))
    bands_text, dos_text = _non_scf_runs(pw[1:])

    energies = [float(value) * EH_PER_RY for value in _ENERGY.findall(ground_state)]
    band_structure = _band_structure(bands_text, ground_state) if bands_text else None
    density_of_states = _density_of_states(dos_text) if dos_text else None
    sources = [(_levels(ground_state, _SCF_END), _filled(ground_state))]
    sources += [(part.levels, part.filled) for part in (band_structure, density_of_states) if part is not None]
    valence, conduction = sampled_band_edges(sources)
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


# Band structure and density of states


def _band_structure(output: str, ground_state: str = '') -> Optional[BandStructure]:
    """The bands run's levels along the path. The path's names come from the cell the ground
    state started from, the one the bands input was written for: after a variable-cell
    relaxation the bands run prints the relaxed cell, which can belong to another lattice."""
    channels = _channels(output, _NSCF_END)
    printed = _printed_cell(output)
    if not channels or not channels[0] or printed is None:
        return None
    _, axes = printed
    path = band_path(_cell(_printed_cell(ground_state) or printed))
    kpoints = [k for k, _ in channels[0]]
    # Cartesian in 2π/alat to fractional in the reciprocal vectors: k·a_i, with a_i in alat.
    fractional = [tuple(sum(k[j] * axis[j] for j in range(3)) for axis in axes) for k in kpoints]
    distances, ticks, starts = path_axis(fractional, path, _cell(printed).reciprocal)
    levels = [[energies for _, energies in channel] for channel in channels]
    return BandStructure(distances, levels, ticks, starts, _filled(output), path.lattice, kpoints)


def _printed_cell(output: str) -> Optional[tuple[float, list[tuple[float, float, float]]]]:
    """(alat in Å, the crystal axes in units of alat) as a run first prints them; None if missing."""
    alat = _ALAT.search(output)
    axes = {}
    for match in _AXIS.finditer(output):  # a relaxation prints the axes again at the end
        axes.setdefault(int(match.group(1)) - 1, tuple(float(value) for value in match.groups()[1:]))
    if alat is None or len(axes) != 3:
        return None
    return float(alat.group(1)) * ANGSTROM_PER_BOHR, [axes[i] for i in range(3)]


def _cell(printed: tuple[float, list[tuple[float, float, float]]]) -> Cell:
    scale, axes = printed
    return Cell(tuple(tuple(value * scale for value in axis) for axis in axes))


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
