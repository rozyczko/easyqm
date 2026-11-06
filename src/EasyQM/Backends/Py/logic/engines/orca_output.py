# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Reads the numbers the Summary page shows from an ORCA output file (checked on ORCA 6.1).

Each value is taken from the last block of its kind, which after an optimisation is the
one at the final geometry. A value whose block is missing stays None, so a failed or
stopped job yields whatever it got to.

Excited states run last, in an ORCA process of their own (`OrcaAdapter.input_files`), whose
output follows the ground-state one in the same file. That job reports the excited state's
energy as its final energy, so the ground-state values come from the output before its
banner and the excitations from the output after it.
"""

import re
from typing import Optional

from ..results import Criterion
from ..results import Excitation
from ..results import ExcitedStates
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
# Where the excited-state calculation starts, and the banner each ORCA process prints first.
EXCITED_STATES_START = re.compile(r'ORCA (?:TD-DFT\S*|CIS) CALCULATION\b|EOM-CCSD CALCULATION\b')
_BANNER = re.compile(r'\* O   R   C   A \*')
# The results header names the method that ran: full TD-HF starts as 'ORCA CIS CALCULATION' too.
_EXCITED_METHOD = re.compile(r'^(TD-DFT/TDA|TD-DFT|CIS|RPA)[- ]EXCITED STATES|(EOM-CCSD) RESULTS', re.MULTILINE)
_ABSORPTION = 'ABSORPTION SPECTRUM VIA TRANSITION ELECTRIC DIPOLE MOMENTS'
_TRANSITION = re.compile(rf'^\s*\d+-\S+\s+->\s+(\d+)-(\d+)\S*\s+({_NUMBER})\s+{_NUMBER}\s+{_NUMBER}\s+({_NUMBER})')
_ROOT = re.compile(rf'^IROOT=\s*(\d+):\s+{_NUMBER} au\s+({_NUMBER}) eV', re.MULTILINE)


def parse(output: str) -> Results:
    start = EXCITED_STATES_START.search(output)
    if start is None:
        ground, excited = output, ''
    else:
        banners = [banner.start() for banner in _BANNER.finditer(output, 0, start.start())]
        split = banners[-1] if banners else 0
        ground, excited = output[:split], output[split:]
    lines = ground.splitlines()
    homo, lumo = _frontier_orbitals(lines)
    return Results(
        final_energy=_last_float(_FINAL_ENERGY, ground),
        homo=homo,
        lumo=lumo,
        dipole=_last_float(_DIPOLE, ground),
        optimisation=_optimisation(ground, lines),
        frequencies=_frequencies(ground, lines),
        excited_states=_excited_states(excited),
    )


def _excited_states(output: str) -> Optional[ExcitedStates]:
    """From the last electric-dipole absorption table (for EOM-CCSD the left-right one), or
    from the EOM roots where an open-shell reference has no transition moments."""
    methods = _EXCITED_METHOD.findall(output)
    if not methods:
        return None
    rows = _block(output.splitlines(), _ABSORPTION, _TRANSITION)
    states = [Excitation(int(state), float(energy), int(multiplicity), float(strength))
              for state, multiplicity, energy, strength in (row.groups() for row in rows)]
    if not states:
        results = output.rfind('EOM-CCSD RESULTS')
        states = [Excitation(int(state), float(energy)) for state, energy in _ROOT.findall(output, max(results, 0))]
    return ExcitedStates(method=''.join(methods[-1]), states=states) if states else None


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
