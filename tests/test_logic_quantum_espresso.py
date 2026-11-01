# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Quantum ESPRESSO adapter: detection, the pw.x input, and reading pw.x 7.5 outputs."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from Backends.Py.logic.calculations import Calculations
from Backends.Py.logic.calculations import CalculationType
from Backends.Py.logic.engines import base
from Backends.Py.logic.engines import quantum_espresso
from Backends.Py.logic.engines.quantum_espresso import QuantumEspressoAdapter
from Backends.Py.logic.engines.quantum_espresso import sibling
from Backends.Py.logic.method import RunSettings
from Backends.Py.logic.sample import Sample

DATA = Path(__file__).parent / 'data'
SI_SCF = DATA / 'qe_si_scf.out'  # 8-atom cell, 2 × 2 × 2 k-points
SI_SPIN_SCF = DATA / 'qe_si_spin_scf.out'  # the same, spin-polarised
SI_RELAX = DATA / 'qe_si_relax.out'  # Si1 moved 0.08 Å along x, then relaxed
NACL_PHONONS = DATA / 'qe_nacl_phonons.out'  # primitive cell, phonons at Γ

NACL_SCF = """! EasyQM: NaCl (ClNa) - Single point energy
&control
  calculation = 'scf'
  prefix = 'job'
  outdir = './tmp'
  pseudo_dir = '{pseudo}'
/
&system
  ibrav = 0
  nat = 8
  ntyp = 2
  ecutwfc = 40
  ecutrho = 320
  occupations = 'smearing'
  smearing = 'cold'
  degauss = 0.01
/
&electrons
  conv_thr = 1e-10
  electron_maxstep = 100
/
ATOMIC_SPECIES
  Cl    35.4530  cl_pbe_v1.uspp.F.UPF
  Na    22.9898  Na.paw.pbe.upf
CELL_PARAMETERS angstrom
      5.64020000     0.00000000     0.00000000
      0.00000000     5.64020000     0.00000000
      0.00000000     0.00000000     5.64020000
ATOMIC_POSITIONS angstrom
  Na     0.00000000     0.00000000     0.00000000
  Na     0.00000000     2.82010000     2.82010000
  Na     2.82010000     0.00000000     2.82010000
  Na     2.82010000     2.82010000     0.00000000
  Cl     2.82010000     2.82010000     2.82010000
  Cl     2.82010000     0.00000000     0.00000000
  Cl     0.00000000     2.82010000     0.00000000
  Cl     0.00000000     0.00000000     2.82010000
K_POINTS automatic
  2 2 2  0 0 0
"""


@pytest.fixture
def pseudo(tmp_path) -> Path:
    """A pseudopotential folder for NaCl, with both naming styles and a file that is no UPF."""
    folder = tmp_path / 'pseudo'
    folder.mkdir()
    for name in ('Na.paw.pbe.upf', 'cl_pbe_v1.uspp.F.UPF', 'notes.txt'):
        (folder / name).write_text('', encoding='utf-8')
    cutoffs = {'Na': {'cutoff_wfc': 40, 'cutoff_rho': 320}, 'Cl': {'cutoff_wfc': 35, 'cutoff_rho': 210}}
    (folder / 'cutoffs.json').write_text(json.dumps(cutoffs), encoding='utf-8')
    return folder


@pytest.fixture
def nacl(nacl_cif) -> Sample:
    sample = Sample()
    sample.load(nacl_cif)
    return sample


def _input(pseudo, sample, *steps, **options) -> str:
    adapter = QuantumEspressoAdapter()
    adapter.pseudo_folder = pseudo
    calculations = Calculations()
    for step in steps or (CalculationType.SINGLE_POINT,):
        calculations.set_selected(step, True)
    for name, value in options.items():
        setattr(calculations.geometry_optimisation, name, value)
    return adapter.input_text(sample, calculations, adapter.default_method(), RunSettings())


# Detection


def test_found_with_version_and_the_pseudo_folder_beside_bin(tmp_path, monkeypatch):
    executable = tmp_path / 'QE' / 'bin' / 'pw.exe'
    executable.parent.mkdir(parents=True)
    executable.write_text('', encoding='utf-8')
    (tmp_path / 'QE' / 'pseudo').mkdir()
    monkeypatch.delenv('ESPRESSO_PSEUDO', raising=False)
    banner = '\n     Program PWSCF v.7.5 starts on  1Nov2026 at 17: 6:10 \n'
    monkeypatch.setattr(base.subprocess, 'run', lambda *args, **kwargs: SimpleNamespace(stdout=banner))

    adapter = QuantumEspressoAdapter(str(executable))
    info = adapter.detect()

    assert info.found and info.version == '7.5' and info.path == str(executable)
    assert adapter.pseudo_folder == tmp_path / 'QE' / 'pseudo'
    assert info.detail == f'pseudopotentials in {tmp_path / "QE" / "pseudo"}'


def test_espresso_pseudo_wins_and_a_missing_program_is_not_found(tmp_path, monkeypatch):
    monkeypatch.setattr(quantum_espresso.shutil, 'which', lambda name: None)
    assert not QuantumEspressoAdapter().detect().found

    executable = tmp_path / 'pw.x'
    executable.write_text('', encoding='utf-8')
    monkeypatch.setenv('ESPRESSO_PSEUDO', str(tmp_path))
    monkeypatch.setattr(base.subprocess, 'run', lambda *args, **kwargs: SimpleNamespace(stdout=''))
    adapter = QuantumEspressoAdapter(str(executable))
    assert adapter.detect().version == '' and adapter.pseudo_folder == tmp_path


def test_default_method_is_among_the_choices():
    adapter = QuantumEspressoAdapter()
    method, capabilities = adapter.default_method(), adapter.capabilities()
    for name, choices in (
        ('family', capabilities.families),
        ('functional', capabilities.functionals),
        ('dispersion', capabilities.dispersions),
        ('basis_set', capabilities.basis_sets),
        ('reference', capabilities.references),
        ('scf_convergence', capabilities.scf_convergences),
        ('occupations', capabilities.occupations),
    ):
        assert getattr(method, name) in [value for value, _ in choices], name


# Input


def test_single_point_input(pseudo, nacl):
    assert _input(pseudo, nacl) == NACL_SCF.format(pseudo=pseudo.as_posix())


def test_optimisation_input(pseudo, nacl):
    nacl.atoms[0].fixed = True
    text = _input(pseudo, nacl, CalculationType.GEOMETRY_OPTIMISATION, convergence='tight')

    assert "calculation = 'relax'" in text
    assert 'etot_conv_thr = 1e-05\n  forc_conv_thr = 0.0001\n  nstep = 100\n' in text
    assert 'nosym = .true.' in text  # fixed atoms break the symmetry
    assert '&ions\n/\n' in text and '&cell' not in text
    assert '  Na     0.00000000     0.00000000     0.00000000  0 0 0\n  Na     0.00000000' in text

    nacl.atoms[0].fixed = False
    text = _input(pseudo, nacl, CalculationType.GEOMETRY_OPTIMISATION, optimise='positions_and_cell')
    assert "calculation = 'vc-relax'" in text and "&cell\n  cell_dofree = 'all'\n/\n" in text
    assert 'nosym' not in text


def test_charge_spin_and_dispersion(pseudo, nacl):
    adapter = QuantumEspressoAdapter()
    adapter.pseudo_folder = pseudo
    calculations = Calculations()
    calculations.set_selected(CalculationType.SINGLE_POINT, True)
    method = adapter.default_method()
    method.reference, method.dispersion, method.scf_convergence = 'UKS', 'D3BJ', 'loose'
    nacl.charge, nacl.multiplicity = 1, 2
    method.kpoints.grid = (4, 4, 1)

    text = adapter.input_text(nacl, calculations, method, RunSettings())

    assert 'tot_charge = 1\n  nspin = 2\n  tot_magnetization = 1\n' in text
    assert "vdw_corr = 'dft-d3'\n  dftd3_version = 4\n" in text
    assert 'conv_thr = 1e-06' in text and text.endswith('K_POINTS automatic\n  4 4 1  0 0 0\n')


def test_fixed_occupations_for_insulators(pseudo, nacl):
    # Valence charges in both UPF header styles: v2 attribute, v1 line.
    (pseudo / 'Na.paw.pbe.upf').write_text('<PP_HEADER z_valence="9.000000000000e0"/>', encoding='utf-8')
    (pseudo / 'cl_pbe_v1.uspp.F.UPF').write_text('   7.00000000000      Z valence\n', encoding='utf-8')
    adapter = QuantumEspressoAdapter()
    adapter.pseudo_folder = pseudo
    calculations = Calculations()
    calculations.set_selected(CalculationType.VIBRATIONAL_FREQUENCIES, True)
    method = adapter.default_method()
    method.occupations = 'fixed'

    files = adapter.input_files(nacl, calculations, method, RunSettings())

    # 4 × 9 + 4 × 7 = 64 electrons fill 32 bands; 4 empty ones show the gap
    assert "occupations = 'fixed'\n  nbnd = 36\n/" in files['job.in'] and 'smearing' not in files['job.in']
    assert 'epsil = .true.' in files['ph.in']

    method.occupations = 'smearing'
    assert 'epsil' not in adapter.input_files(nacl, calculations, method, RunSettings())['ph.in']


def test_input_problems(pseudo, nacl, tmp_path):
    molecule = Sample()
    with pytest.raises(ValueError, match='Quantum ESPRESSO runs crystals only; this sample is a molecule.'):
        _input(pseudo, molecule)
    with pytest.raises(ValueError, match='No pseudopotential folder'):
        _input(None, nacl)

    (pseudo / 'Na.us.pbe.upf').write_text('', encoding='utf-8')
    with pytest.raises(ValueError, match=r'Several pseudopotentials for Na in .*: Na\.paw\.pbe\.upf, Na\.us\.pbe\.upf'):
        _input(pseudo, nacl)
    (pseudo / 'Na.us.pbe.upf').unlink()
    (pseudo / 'cl_pbe_v1.uspp.F.UPF').unlink()
    with pytest.raises(ValueError, match='No pseudopotential for Cl'):
        _input(pseudo, nacl)
    (pseudo / 'Cl.upf').write_text('', encoding='utf-8')
    (pseudo / 'cutoffs.json').write_text('{"Na": {"cutoff_wfc": 40, "cutoff_rho": 320}}', encoding='utf-8')
    with pytest.raises(ValueError, match='has no cutoffs for Cl'):
        _input(pseudo, nacl)
    (pseudo / 'cutoffs.json').unlink()
    with pytest.raises(ValueError, match='recommended cutoffs could not be read'):
        _input(pseudo, nacl)


def test_frequencies_add_ph_and_dynmat_beside_pw(pseudo, nacl, tmp_path):
    adapter = QuantumEspressoAdapter()
    adapter.pseudo_folder = pseudo
    calculations = Calculations()
    calculations.set_selected(CalculationType.VIBRATIONAL_FREQUENCIES, True)

    files = adapter.input_files(nacl, calculations, adapter.default_method(), RunSettings())

    assert list(files) == ['job.in', 'ph.in', 'dynmat.in']
    assert "calculation = 'scf'" in files['job.in']
    assert "fildyn = 'job.dyn'" in files['ph.in'] and files['ph.in'].endswith('0.0 0.0 0.0\n')
    assert "asr = 'crystal'" in files['dynmat.in']

    bin_folder = tmp_path / 'bin'
    bin_folder.mkdir()
    pw = bin_folder / 'pw.exe'
    with pytest.raises(ValueError, match=r'ph\.exe was not found next to pw\.exe'):
        adapter.commands(str(pw), list(files))
    for name in ('ph.exe', 'dynmat.exe'):
        (bin_folder / name).write_text('', encoding='utf-8')
    assert adapter.commands(str(pw), list(files)) == [
        [str(pw), '-i', 'job.in'],
        [str(bin_folder / 'ph.exe'), '-i', 'ph.in'],
        [str(bin_folder / 'dynmat.exe'), '-i', 'dynmat.in'],
    ]

    calculations.vibrational_frequencies.raman = True
    with pytest.raises(ValueError, match='untick Raman'):
        adapter.input_files(nacl, calculations, adapter.default_method(), RunSettings())


def test_programs_beside_pw_on_windows_and_linux():
    assert sibling('F:/QE/bin/pw.exe', 'ph') == str(Path('F:/QE/bin/ph.exe'))
    assert sibling('/opt/qe/bin/pw.x', 'dynmat') == str(Path('/opt/qe/bin/dynmat.x'))
    assert sibling('/opt/qe/bin/pw', 'ph') == str(Path('/opt/qe/bin/ph'))


def test_command_and_success():
    adapter = QuantumEspressoAdapter()
    assert adapter.command('F:/QE/bin/pw.exe', Path('runs/001/job.in')) == ['F:/QE/bin/pw.exe', '-i', 'job.in']
    assert adapter.commands('F:/QE/bin/pw.exe', ['job.in']) == [['F:/QE/bin/pw.exe', '-i', 'job.in']]
    assert adapter.succeeded(SI_SCF.read_text(encoding='utf-8'))
    assert not adapter.succeeded('     convergence NOT achieved after 100 iterations: stopping\n   JOB DONE.\n')


def test_current_step_follows_the_output():
    adapter = QuantumEspressoAdapter()
    opt, sp, freq = (
        CalculationType.GEOMETRY_OPTIMISATION,
        CalculationType.SINGLE_POINT,
        CalculationType.VIBRATIONAL_FREQUENCIES,
    )
    relax = SI_RELAX.read_text(encoding='utf-8')
    first_scf = relax[: relax.index('BFGS Geometry Optimization')]
    assert adapter.current_step(first_scf, [sp, opt]) == 0
    assert adapter.current_step(relax, [sp, opt]) == 1
    assert adapter.current_step(first_scf, [opt, sp]) == 0
    assert adapter.current_step(relax, [opt, sp]) == 1
    phonons = NACL_PHONONS.read_text(encoding='utf-8')
    assert adapter.current_step(phonons[: phonons.index('Program PHONON')], [sp, freq]) == 0
    assert adapter.current_step(phonons, [sp, freq]) == 1
    # pw.x ends normally after an SCF that did not converge, and ph.x then fails on its files.
    unconverged = '     convergence NOT achieved after   1 iterations: stopping\n   JOB DONE.\n     Program PHONON v.7.5\n'
    assert adapter.current_step(unconverged, [sp, freq]) == 0


# Output


def test_reads_a_single_point():
    results = QuantumEspressoAdapter().parse(SI_SCF.read_text(encoding='utf-8'))

    assert results.final_energy == pytest.approx(-91.29525313 / 2)
    assert (results.homo, results.lumo, results.fermi_energy) == (6.2527, 6.9439, 6.6820)
    assert results.optimisation is None and results.frequencies is None


def test_reads_band_edges_per_spin_channel():
    results = QuantumEspressoAdapter().parse(SI_SPIN_SCF.read_text(encoding='utf-8'))
    assert (results.homo, results.lumo, results.fermi_energy) == (6.2528, 6.9439, 6.6820)


def test_a_partly_filled_band_is_a_metal():
    output = SI_SCF.read_text(encoding='utf-8').replace('electrons       =        32.00', 'electrons = 31.00')
    results = QuantumEspressoAdapter().parse(output)
    assert results.gap is None and results.fermi_energy == 6.6820


def test_reads_a_relaxation():
    results = QuantumEspressoAdapter().parse(SI_RELAX.read_text(encoding='utf-8'))
    optimisation = results.optimisation

    assert optimisation.converged and optimisation.cycles == 5
    assert optimisation.energies[0] == pytest.approx(-91.28899275 / 2)
    assert optimisation.energies[-1] == results.final_energy == pytest.approx(-91.29525112 / 2)
    assert len(optimisation.initial) == len(optimisation.final) == 8
    assert optimisation.initial[0].label == 'Si1' and optimisation.initial[0].x == pytest.approx(0.75886, abs=1e-4)
    assert (optimisation.final[0].x, optimisation.final[0].y) == (0.7046100345, 0.6788625)


def test_reads_gamma_phonons_after_the_ground_state():
    # Primitive NaCl, fixed occupations: pw.x, ph.x with Born charges, dynmat.x in one file.
    results = QuantumEspressoAdapter().parse(NACL_PHONONS.read_text(encoding='utf-8'))

    assert results.gap == pytest.approx(5.1038) and results.fermi_energy is None and results.crystal
    modes = results.frequencies.modes  # the three acoustic modes are left out
    assert [(mode.number, mode.frequency) for mode in modes] == [(4, 168.6), (5, 168.6), (6, 168.6)]
    assert modes[0].ir_intensity == pytest.approx(2.0578 * 42.2561)
    assert results.frequencies.has_ir and results.frequencies.imaginary_count == 0


def test_reads_nothing_from_an_empty_or_cut_output():
    assert QuantumEspressoAdapter().parse('').empty
    cut = SI_RELAX.read_text(encoding='utf-8').split('ATOMIC_POSITIONS (angstrom)')[0]
    results = QuantumEspressoAdapter().parse(cut)
    assert results.optimisation is None and results.final_energy == pytest.approx(-91.28899275 / 2)
