# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""ORCA output parsing and the engine-agnostic results."""

from pathlib import Path

import pytest

from Backends.Py.logic.engines.orca import CAPABILITIES
from Backends.Py.logic.engines.orca import OrcaAdapter
from Backends.Py.logic.method import Method
from Backends.Py.logic.method import describe
from Backends.Py.logic.results import Results
from Backends.Py.logic.results import bonds_and_angles

DATA = Path(__file__).parent / 'data'
WATER = DATA / 'orca_water_opt_freq.out'


@pytest.fixture(scope='module')
def results() -> Results:
    return OrcaAdapter().parse(WATER.read_text(encoding='utf-8'))


def test_energies_orbitals_and_dipole_come_from_the_last_blocks(results):
    assert results.final_energy == -76.3011
    assert results.homo == -8.7076 and results.lumo == 1.6327
    assert results.gap == pytest.approx(10.3403)
    assert results.dipole == 2.0


def test_optimisation(results):
    optimisation = results.optimisation
    assert optimisation.converged and optimisation.cycles == 2
    assert optimisation.energies == [-76.3, -76.301, -76.3011]
    assert optimisation.energy_change == pytest.approx(-0.0011)
    assert [atom.element for atom in optimisation.initial] == ['O', 'H', 'H']
    assert optimisation.initial[0].z == 0.117 and optimisation.final[0].z == 0.12
    assert [criterion.name for criterion in optimisation.criteria] == [
        'Energy change',
        'RMS gradient',
        'MAX gradient',
        'RMS step',
        'MAX step',
    ]
    assert all(criterion.met for criterion in optimisation.criteria)  # the last cycle's table
    assert optimisation.criteria[0].value == -5e-7 and optimisation.criteria[0].tolerance == 1e-6


def test_frequencies(results):
    frequencies = results.frequencies
    assert [mode.number for mode in frequencies.modes] == [6, 7, 8]
    assert [mode.frequency for mode in frequencies.modes] == [-50.0, 1600.0, 3800.0]
    assert frequencies.imaginary_count == 1
    assert frequencies.modes[1].ir_intensity == 60.0 and frequencies.modes[2].raman_activity == 90.0
    assert frequencies.has_raman
    assert frequencies.zero_point_energy == 0.021 and frequencies.gibbs_free_energy == -76.29
    assert frequencies.temperature == 298.15 and frequencies.pressure == 1.0


def test_single_point_output_has_no_optimisation_or_frequencies():
    text = WATER.read_text(encoding='utf-8')
    single_point = text[text.index('---------------------------------\nCARTESIAN') : text.index('FINAL SINGLE POINT ENERGY')]
    single_point += 'FINAL SINGLE POINT ENERGY       -76.300000000000\n'

    results = OrcaAdapter().parse(single_point)

    assert results.final_energy == -76.3 and results.homo == -8.1634
    assert results.optimisation is None and results.frequencies is None and results.dipole is None


def _excitations(name: str, before: str = ''):
    results = OrcaAdapter().parse(before + (DATA / name).read_text(encoding='utf-8'))
    states = results.excited_states.states
    return results, [(s.state, s.multiplicity, s.energy, s.oscillator_strength) for s in states]


def test_excited_states_after_an_optimisation_leave_the_ground_state_values():
    # The second ORCA process reports the excited state's energy as its final energy.
    results, states = _excitations('orca_water_tda_after_opt.out', WATER.read_text(encoding='utf-8'))
    assert results.final_energy == -76.3011 and results.optimisation is not None
    assert results.excited_states.method == 'TD-DFT/TDA'
    assert states == [(1, 1, 7.535326, 0.017248907), (2, 1, 9.429345, 0.0), (3, 1, 9.935074, 0.088207375)]
    assert results.excited_states.states[0].wavelength == pytest.approx(164.5, abs=0.1)


def test_singlets_and_triplets_come_from_the_electric_dipole_table():
    results, states = _excitations('orca_water_tddft_triplets.out')
    assert results.excited_states.method == 'TD-DFT' and results.final_energy is None
    assert len(states) == 8 and [s[1] for s in states[:3]] == [3, 1, 3]
    assert states[1] == (1, 1, 7.588669, 0.018511223)  # not the velocity table's 0.1046


def test_eom_ccsd_strengths_are_the_left_right_ones():
    results, states = _excitations('orca_water_eom.out')
    assert results.excited_states.method == 'EOM-CCSD'
    assert states[0] == (1, 1, 8.194226, 0.021131778) and len(states) == 3


def test_open_shell_eom_ccsd_has_energies_only():
    results, states = _excitations('orca_oh_uhf_eom.out')
    assert states == [(1, None, 0.007, None), (2, None, 4.29, None), (3, None, 8.164, None)]  # not the guess roots


def test_empty_output():
    assert OrcaAdapter().parse('').empty
    assert OrcaAdapter().parse('ORCA finished by error termination in GUESS').empty


def test_bonds_and_angles_of_water(results):
    bonds, angles = bonds_and_angles(results.optimisation.initial, results.optimisation.final)

    assert [bond.label for bond in bonds] == ['O1–H2', 'O1–H3']
    assert bonds[0].initial == pytest.approx(0.95670, abs=1e-5)
    assert bonds[0].final == pytest.approx(0.96213, abs=1e-5)
    assert [angle.label for angle in angles] == ['H2–O1–H3']
    assert angles[0].initial == pytest.approx(104.607, abs=1e-3)
    assert angles[0].final == pytest.approx(104.354, abs=1e-3)


def test_method_description():
    assert describe(Method(), CAPABILITIES) == 'B3LYP-D3(BJ)/def2-TZVP'
    assert describe(Method(functional='wB97X-D3', dispersion='none'), CAPABILITIES) == 'ωB97X-D3/def2-TZVP'
    assert describe(Method(family='HF', basis_set='def2-SVP'), CAPABILITIES) == 'HF/def2-SVP'
