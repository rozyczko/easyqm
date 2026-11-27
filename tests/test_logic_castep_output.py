# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Reading CASTEP runs. The fixtures in data/castep are real CASTEP 26.11 runs of the inputs the
adapter writes, made through the runner (so job.out has its header lines); the logs are trimmed
to the lines the reader uses, which reads them as it reads the full logs.

- si: Si, fixed occupations, Optimisation (held by symmetry), Frequencies (Automatic: NCP19,
  DFPT), Band structure, Density of states.
- nacl: conventional NaCl listed Cl, Na, Cl, Na…, the second Na fixed and the third moved off its
  site; Optimisation, loose, 3 steps.
- nacl_ir: primitive NaCl, fixed occupations, Frequencies by DFPT with IR intensities.
- spin: Si, spin-polarised with multiplicity 3 under smearing, Density of states.
- unrelaxed: displaced Si, D3, Frequencies without Optimisation: CASTEP refuses the phonon run.
- vc: displaced Si, Positions and cell, then Band structure.
"""

import shutil
from pathlib import Path

import pytest

from Backends.Py.logic.engines.castep import CastepAdapter
from Backends.Py.logic.geometry import distance
from Backends.Py.logic.sample import Sample

DATA = Path(__file__).parent / 'data' / 'castep'
EV_PER_HARTREE = 27.211386245988


def results(case: str, folder: Path = None):
    folder = folder or DATA / case
    return CastepAdapter().read_results(folder, (folder / 'job.out').read_text(encoding='utf-8'))


def output(case: str) -> str:
    return (DATA / case / 'job.out').read_text(encoding='utf-8')


def test_silicon_workflow():
    si = results('si')

    assert CastepAdapter().succeeded(output('si'))
    assert si.final_energy == pytest.approx(-16.198916, abs=1e-6)
    assert si.fermi_energy is None  # fixed occupations: the .bands Fermi line does not make it a metal
    # Held by symmetry: converged with no steps, at the input geometry.
    optimisation = si.optimisation
    assert (optimisation.converged, optimisation.cycles, optimisation.final_cell) == (True, 0, None)
    assert optimisation.final == optimisation.initial and len(optimisation.initial) == 2
    # DFPT: three optical modes with IR intensities, zero for a crystal without a dipole.
    assert [round(mode.frequency, 1) for mode in si.frequencies.modes] == [551.7] * 3
    assert si.frequencies.has_ir and all(mode.ir_intensity == 0 for mode in si.frequencies.modes)
    bands = si.band_structure
    assert bands.lattice == 'Face-centred cubic (primitive cell)' and bands.filled == [4]
    assert [name for _, name in bands.ticks] == ['Γ', 'X', 'W', 'K', 'Γ', 'L', 'U', 'W', 'L', 'K|U', 'X']
    assert bands.starts == [0, 98] and len(bands.distances) == 105
    # Å⁻¹: Γ–X is 2π/a = 1.157 for a = 5.43 Å, and the whole path 6.42 × 2π/a.
    assert bands.ticks[1] == (pytest.approx(1.1571, abs=1e-4), 'X')
    assert bands.distances[-1] == pytest.approx(7.4278, abs=1e-3)
    dos = si.density_of_states
    assert len(dos.levels) == 1 and sum(dos.weights) == pytest.approx(2.0) and dos.filled == [4]
    assert (si.homo, si.lumo) == (pytest.approx(1.6155, abs=1e-4), pytest.approx(2.2283, abs=1e-4))


def test_interleaved_atoms_come_back_in_the_sample_order():
    optimisation = results('nacl').optimisation

    assert [atom.element for atom in optimisation.initial] == ['Cl', 'Na', 'Cl', 'Na', 'Cl', 'Na', 'Cl', 'Na']
    assert [atom.element for atom in optimisation.final] == [atom.element for atom in optimisation.initial]
    assert distance(optimisation.initial[3], optimisation.final[3]) < 1e-6  # the fixed Na
    assert optimisation.initial[5].z == pytest.approx(2.9328) and optimisation.final[5].z == pytest.approx(2.843, abs=1e-3)
    assert all(distance(a, b) < 0.1 for a, b in zip(optimisation.initial, optimisation.final))  # no jump by a lattice vector
    assert optimisation.converged and optimisation.cycles == 4 and optimisation.final_cell is None
    # The cell is fixed, so CASTEP judges no stress.
    assert [criterion.name for criterion in optimisation.criteria] == [
        'Energy change (eV/atom)', 'Max. force (eV/Å)', 'Max. displacement (Å)']
    assert optimisation.criteria[1].tolerance == 0.1 and all(criterion.met for criterion in optimisation.criteria)


def test_the_optimised_geometry_applies_to_the_sample_it_started_from():
    optimisation = results('nacl').optimisation
    sample = Sample()
    sample.cell = Sample().cell
    sample.atoms = [atom for atom in optimisation.initial]
    assert sample.at_positions(optimisation.initial)


def test_energies_of_an_optimisation_are_its_enthalpies():
    vc = results('vc')
    trace = vc.optimisation.energies
    assert len(trace) == 10 and vc.final_energy == trace[-1]
    assert vc.optimisation.criteria[-1].name == 'Max. stress (GPa)'
    assert trace[-1] == pytest.approx(-340.154897 / EV_PER_HARTREE, abs=1e-8)  # 'LBFGS: Final Enthalpy', in eV


def test_a_cell_optimisation_gives_the_new_cell_and_the_bands_keep_the_input_path():
    vc = results('vc')
    assert vc.optimisation.final_cell is not None
    assert vc.optimisation.final_cell.vectors[0][0] == pytest.approx(0.0432, abs=1e-3)
    assert vc.band_structure.lattice == 'Face-centred cubic (primitive cell)'
    assert vc.fermi_energy is not None  # smearing


def test_ir_intensities_of_a_polar_crystal():
    modes = results('nacl_ir').frequencies.modes
    assert [round(mode.frequency, 1) for mode in modes] == [184.5] * 3  # TO; the LO table is not read
    assert modes[0].ir_intensity == pytest.approx(2.4134 * 42.2561, abs=0.01)


def test_spin_held_under_smearing():
    spin = results('spin')
    dos = spin.density_of_states
    assert len(dos.levels) == 2 and dos.filled == [5, 3]
    assert sum(dos.weights) == pytest.approx(1.0)  # one per channel, as pw.x prints them
    assert spin.fermi_energy is None and dos.fermi_energy is None  # each channel has its own Fermi level


def test_a_refused_phonon_run_fails_with_its_reason_and_keeps_the_ground_state():
    adapter = CastepAdapter()
    text = output('unrelaxed')
    assert not adapter.succeeded(text)
    assert adapter.failure_reason(text) == ('Frequencies need an optimised geometry: the largest force is 1.02 eV/Å. '
                                            'Tick Optimisation.')
    unrelaxed = results('unrelaxed')
    assert unrelaxed.final_energy is not None and unrelaxed.frequencies is None


def test_without_a_folder_only_the_logs_are_read():
    si = CastepAdapter().parse(output('si'))
    assert si.final_energy == pytest.approx(-16.198916, abs=1e-6) and si.frequencies is not None
    assert si.band_structure is None and si.density_of_states is None
    assert si.optimisation.initial == [] and si.optimisation.final == []


def test_a_file_cut_short_leaves_out_its_result_only(tmp_path):
    folder = tmp_path / 'si'
    shutil.copytree(DATA / 'si', folder)
    dos = folder / 'job-dos.bands'
    dos.write_text(''.join(dos.read_text(encoding='utf-8').splitlines(keepends=True)[:-3]), encoding='utf-8')
    (folder / 'job-bands.bands').unlink()

    si = results('si', folder)

    assert si.density_of_states is None and si.band_structure is None
    assert si.frequencies is not None and si.homo is not None  # from the ground state's levels


def test_an_optimisation_without_its_geom_file_stays_at_the_input(tmp_path):
    folder = tmp_path / 'nacl'
    shutil.copytree(DATA / 'nacl', folder)
    (folder / 'job.geom').unlink()
    optimisation = results('nacl', folder).optimisation
    assert optimisation.final == optimisation.initial and optimisation.cycles == 4
