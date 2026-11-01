# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Reads the numbers the Summary page shows from an ORCA output file (checked on ORCA 6.1).

Each value is taken from the last block of its kind, which after an optimisation is the
one at the final geometry. A value whose block is missing stays None, so a failed or
stopped job yields whatever it got to.
"""

import re
from typing import Optional

from ..results import Criterion
from ..results import Frequencies
from ..results import Mode
from ..results import Optimisation
from ..results import Results
from ..sample import Atom
from .parsing import NUMBER as _NUMBER
from .parsing import block as _block
from .parsing import last_float as _last_float

_FINAL_ENERGY = re.compile(rf'FINAL SINGLE POINT ENERGY\s+({_NUMBER})')
_OPT_CYCLE = re.compile(r'GEOMETRY OPTIMIZATION CYCLE\s+(\d+)')
_OPT_CONVERGED = 'THE OPTIMIZATION HAS CONVERGED'
_CRITERION = re.compile(
    rf'^\s*(Energy change|RMS gradient|MAX gradient|RMS step|MAX step)\s+({_NUMBER})\s+({_NUMBER})\s+(YES|NO)\s*$'
)
_COORDINATE = re.compile(rf'^\s*([A-Z][a-z]?)\s+({_NUMBER})\s+({_NUMBER})\s+({_NUMBER})\s*$')
_ORBITAL = re.compile(rf'^\s*\d+\s+({_NUMBER})\s+({_NUMBER})\s+({_NUMBER})\s*$')
_DIPOLE = re.compile(rf'Magnitude \(Debye\)\s*:\s*({_NUMBER})')
_FREQUENCY = re.compile(rf'^\s*(\d+):\s+({_NUMBER}) cm\*\*-1')
_FIRST_VIBRATION = re.compile(r'The first frequency considered to be a vibration is (\d+)')
_SPECTRUM_ROW = re.compile(rf'^\s*(\d+):\s+({_NUMBER})\s+({_NUMBER})\s+({_NUMBER})')
_ZPE = re.compile(rf'Zero point energy\s+\.\.\.\s+({_NUMBER}) Eh')
_GIBBS = re.compile(rf'Final Gibbs free energy\s+\.\.\.\s+({_NUMBER}) Eh')
_TEMPERATURE = re.compile(rf'^Temperature\s+\.\.\.\s+({_NUMBER}) K', re.MULTILINE)
_PRESSURE = re.compile(rf'^Pressure\s+\.\.\.\s+({_NUMBER}) atm', re.MULTILINE)


def parse(output: str) -> Results:
    lines = output.splitlines()
    homo, lumo = _frontier_orbitals(lines)
    return Results(
        final_energy=_last_float(_FINAL_ENERGY, output),
        homo=homo,
        lumo=lumo,
        dipole=_last_float(_DIPOLE, output),
        optimisation=_optimisation(output, lines),
        frequencies=_frequencies(output, lines),
    )


def _atoms(lines: list[str], index: int) -> list[Atom]:
    """The coordinate block starting at line `index` (its 'CARTESIAN COORDINATES' title)."""
    atoms = []
    for line in lines[index + 2 :]:  # title and underline
        match = _COORDINATE.match(line)
        if not match:
            break
        element, x, y, z = match.groups()
        atoms.append(Atom(f'{element}{len(atoms) + 1}', element, float(x), float(y), float(z)))
    return atoms


def _frontier_orbitals(lines: list[str]) -> tuple[Optional[float], Optional[float]]:
    # For an unrestricted reference this is the first (spin-up) table.
    homo = lumo = None
    for match in _block(lines, r'^ORBITAL ENERGIES\s*$', _ORBITAL):
        occupation, energy = float(match.group(1)), float(match.group(3))
        if occupation > 0:
            homo = energy
        else:
            lumo = energy
            break
    return homo, lumo


def _optimisation(output: str, lines: list[str]) -> Optional[Optimisation]:
    cycles = [int(number) for number in _OPT_CYCLE.findall(output)]
    if not cycles:
        return None
    first_cycle = next(i for i, line in enumerate(lines) if _OPT_CYCLE.search(line))
    blocks = [i for i, line in enumerate(lines) if line.strip() == 'CARTESIAN COORDINATES (ANGSTROEM)']
    initial_blocks = [i for i in blocks if i > first_cycle]
    if not initial_blocks:
        return None
    energies = [float(value) for value in _FINAL_ENERGY.findall('\n'.join(lines[first_cycle:]))]
    criteria = [
        Criterion(match.group(1), float(match.group(2)), float(match.group(3)), match.group(4) == 'YES')
        for match in _block(lines, r'\|Geometry convergence\|', _CRITERION, first_cycle)
    ]
    return Optimisation(
        converged=_OPT_CONVERGED in output,
        cycles=max(cycles),
        energies=energies,
        initial=_atoms(lines, initial_blocks[0]),
        final=_atoms(lines, blocks[-1]),
        criteria=criteria,
    )


def _frequencies(output: str, lines: list[str]) -> Optional[Frequencies]:
    rows = _block(lines, r'^VIBRATIONAL FREQUENCIES\s*$', _FREQUENCY)
    if not rows:
        return None
    first = _FIRST_VIBRATION.search(output)
    first_vibration = int(first.group(1)) if first else 6
    ir = {int(m.group(1)): float(m.group(4)) for m in _block(lines, r'^IR SPECTRUM\s*$', _SPECTRUM_ROW)}
    raman = {int(m.group(1)): float(m.group(3)) for m in _block(lines, r'^RAMAN SPECTRUM\s*$', _SPECTRUM_ROW)}
    modes = [
        Mode(number, float(m.group(2)), ir.get(number), raman.get(number))
        for m in rows
        if (number := int(m.group(1))) >= first_vibration
    ]
    return Frequencies(
        modes=modes,
        zero_point_energy=_last_float(_ZPE, output),
        gibbs_free_energy=_last_float(_GIBBS, output),
        temperature=_last_float(_TEMPERATURE, output),
        pressure=_last_float(_PRESSURE, output),
    )
