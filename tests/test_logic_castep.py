# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""The CASTEP adapter: detection, the input of every workflow, and judging its runs.

The output side, read from real CASTEP 26.11 runs, is in test_logic_castep_output.py.
"""

import itertools
import re
from types import SimpleNamespace

import pytest

from Backends.Py.logic.calculations import Calculations
from Backends.Py.logic.calculations import CalculationType
from Backends.Py.logic.engines import base
from Backends.Py.logic.engines import castep
from Backends.Py.logic.engines.castep import CastepAdapter
from Backends.Py.logic.method import RunSettings
from Backends.Py.logic.runner import Step
from Backends.Py.logic.sample import Atom
from Backends.Py.logic.sample import Cell
from Backends.Py.logic.sample import Sample

CRYSTAL_CALCULATIONS = (
    CalculationType.SINGLE_POINT,
    CalculationType.GEOMETRY_OPTIMISATION,
    CalculationType.VIBRATIONAL_FREQUENCIES,
    CalculationType.BAND_STRUCTURE,
    CalculationType.DENSITY_OF_STATES,
)
VERSION_TEXT = """ CASTEP version: 26.11

 Compiled for mingw_x86_64_gfortran10 on Thu, 26 Nov 2026 10:46:42 +0100
 Comms   : serial
"""
HELP_TEXT = """Help information on PARAMETERS keywords:

              XC_FUNCTIONAL   *! exchange-correlation functional !*
Allowed values: LDA, LDA_PZ, PW91, PBE, PBESOL, RPBE, WC, BLYP, ZERO, HF, PBE0, HSE06, RSCAN, R2SCAN.
Also allowed are values of the form LIBXC_<libxc-id> which specify functionals supplied by libxc.
"""


def silicon() -> Sample:
    sample = Sample()
    sample.name = 'Si'
    sample.cell = Cell(((0, 2.715, 2.715), (2.715, 0, 2.715), (2.715, 2.715, 0)))
    sample.atoms = [Atom('Si1', 'Si', 0, 0, 0), Atom('Si2', 'Si', 1.3575, 1.3575, 1.3575)]
    return sample


def rock_salt() -> Sample:
    """Conventional NaCl with Cl and Na interleaved, as a hand-made file may list them."""
    sample = Sample()
    sample.name = 'NaCl'
    sample.cell = Cell(((5.64, 0, 0), (0, 5.64, 0), (0, 0, 5.64)))
    sites = [('Cl', .5, 0, 0), ('Na', 0, 0, 0), ('Cl', 0, .5, 0), ('Na', .5, .5, 0)]
    sample.atoms = [Atom(f'{e}{i + 1}', e, *sample.cell.cartesian(x, y, z)) for i, (e, x, y, z) in enumerate(sites)]
    return sample


def selection(*selected, **options) -> Calculations:
    calculations = Calculations()
    calculations.periodic = True
    for calculation in selected:
        calculations.set_selected(calculation, True)
    for name, value in options.items():
        group, field = name.split('__')
        setattr(getattr(calculations, group), field, value)
    return calculations


def method(**values):
    method = CastepAdapter().default_method()
    for name, value in values.items():
        setattr(method, name, value)
    return method


def files(sample=None, calculations=None, **values) -> dict[str, str]:
    calculations = calculations or selection(CalculationType.SINGLE_POINT)
    return CastepAdapter().input_files(sample or silicon(), calculations, method(**values), RunSettings())


def lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines()]


# Detection


def _fake_run(monkeypatch, version, code=0, help_text=HELP_TEXT):
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs.get('env')))
        if command[1] == '--version':
            if isinstance(version, Exception):
                raise version
            return SimpleNamespace(stdout=version, returncode=code)
        return SimpleNamespace(stdout=help_text, returncode=0)

    monkeypatch.setattr(base.subprocess, 'run', run)
    return calls


def test_detects_the_version_and_the_functionals_the_build_accepts(tmp_path, monkeypatch):
    executable = tmp_path / 'castep.serial.exe'
    executable.touch()
    calls = _fake_run(monkeypatch, VERSION_TEXT)
    adapter = CastepAdapter(str(executable))

    info = adapter.detect()

    assert (info.found, info.version, info.detail) == (True, '26.11', 'serial')
    assert calls[0][1]['OMP_NUM_THREADS'] == '1'  # the probe gets the engine's environment
    assert [value for value, _ in adapter.capabilities().functionals] == ['LDA', 'PBE', 'PBESOL', 'RPBE', 'WC', 'PW91',
                                                                          'BLYP', 'RSCAN']
    _fake_run(monkeypatch, VERSION_TEXT, help_text=HELP_TEXT.replace('RSCAN, ', '').replace('WC, ', ''))
    adapter.detect()
    assert 'RSCAN' not in dict(adapter.capabilities().functionals) and 'WC' not in dict(adapter.capabilities().functionals)
    _fake_run(monkeypatch, VERSION_TEXT, help_text='')  # no list: the curated one, whole
    adapter.detect()
    assert adapter.capabilities() == castep.CAPABILITIES


@pytest.mark.parametrize('version, code, detail', [
    ('', 0xC0000135, 'castep.serial.exe does not start (0xC0000135: a DLL it needs was not found)'),
    (OSError('cannot run'), None, 'castep.serial.exe could not be run'),
])
def test_an_executable_that_does_not_start_is_not_found_and_says_why(tmp_path, monkeypatch, version, code, detail):
    executable = tmp_path / 'castep.serial.exe'
    executable.touch()
    _fake_run(monkeypatch, version, code)
    monkeypatch.setattr(castep.sys, 'platform', 'win32')

    info = CastepAdapter(str(executable)).detect()

    assert not info.found and info.detail == detail and info.path == str(executable)


def test_exit_codes_are_shown_as_the_platform_does():
    assert castep.start_problem('castep', None) == 'castep could not be run'
    if castep.sys.platform == 'win32':
        assert castep.start_problem('castep.exe', -1073741819) == 'castep.exe does not start (exit code 0xC0000005)'
    else:
        assert castep.start_problem('castep', 127) == 'castep does not start (exit code 127)'


def test_missing_executable():
    assert not CastepAdapter('/no/such/castep').detect().found


# Workflows


@pytest.mark.parametrize('count', range(0, 6))
def test_every_selection_runs_the_ground_state_first_then_one_run_per_child(count):
    for selected in itertools.combinations(CRYSTAL_CALCULATIONS, count):
        calculations = selection(*selected)
        if not selected:
            with pytest.raises(ValueError, match='No calculation'):
                files(calculations=calculations)
            continue
        written = files(calculations=calculations)
        seeds = ['job', *(seed for calculation, seed in castep.CHILD_SEEDS.items() if calculation in selected)]
        assert list(written) == [f'{seed}.{suffix}' for seed in seeds for suffix in ('cell', 'param')]
        task = re.search(r'^task : (\S+)', written['job.param'], re.MULTILINE).group(1)
        assert task == ('geometryoptimization' if CalculationType.GEOMETRY_OPTIMISATION in selected else 'singlepoint')
        for seed in seeds[1:]:
            assert 'continuation : job.check' in lines(written[f'{seed}.param'])
        assert 'continuation' not in written['job.param']
        steps = CastepAdapter().steps('castep.exe', list(written))
        assert [step.command for step in steps] == [['castep.exe', seed] for seed in seeds]
        assert steps[0] == Step(['castep.exe', 'job'], 'Ground state', 'job.castep', 'job.*.err')


def test_every_run_has_the_whole_method():
    written = files(calculations=selection(*CRYSTAL_CALCULATIONS), dispersion='TS', occupations='fixed',
                    scf_convergence='normal', engine_options={'basis_precision': 'MEDIUM'})
    shared = ['xc_functional : PBE', 'basis_precision : MEDIUM', 'elec_energy_tol : 1e-06', 'max_scf_cycles : 100',
              'fix_occupancy : true', 'nextra_bands : 4', 'spin_polarized : false', 'sedc_apply : true',
              'sedc_scheme : TS']
    for name, text in written.items():
        if name.endswith('.param'):
            assert set(shared) <= set(lines(text)), name
        else:
            assert 'kpoint_mp_grid : 4 4 4' in lines(text) and 'symmetry_generate' in lines(text), name


def test_single_point_cell():
    assert files()['job.cell'] == """! EasyQM: Si (Si) - Ground state

%BLOCK LATTICE_CART
  ang
      0.00000000     2.71500000     2.71500000
      2.71500000     0.00000000     2.71500000
      2.71500000     2.71500000     0.00000000
%ENDBLOCK LATTICE_CART

%BLOCK POSITIONS_FRAC
  Si     0.00000000     0.00000000     0.00000000
  Si     0.25000000     0.25000000     0.25000000
%ENDBLOCK POSITIONS_FRAC

kpoint_mp_grid : 4 4 4
symmetry_generate
%BLOCK SPECIES_POT
  C19
%ENDBLOCK SPECIES_POT
"""


def test_optimisation_names_a_fixed_atom_as_castep_does_and_drops_symmetry():
    sample = rock_salt()
    sample.atoms[3].fixed = True  # the second Na
    calculations = selection(CalculationType.GEOMETRY_OPTIMISATION, CalculationType.BAND_STRUCTURE,
                             geometry_optimisation__max_steps=50)
    written = files(sample, calculations)

    job = lines(written['job.cell'])
    assert job[job.index('%BLOCK IONIC_CONSTRAINTS') + 1:job.index('%ENDBLOCK IONIC_CONSTRAINTS')] == [
        '1 Na    2  1 0 0', '2 Na    2  0 1 0', '3 Na    2  0 0 1']
    assert 'fix_all_cell : true' in job and 'symmetry_generate' not in job
    # The positions stay in the sample's order; the child takes the constraints from the checkpoint.
    assert [line.split()[0] for line in job[job.index('%BLOCK POSITIONS_FRAC') + 1:][:4]] == ['Cl', 'Na', 'Cl', 'Na']
    assert 'IONIC_CONSTRAINTS' not in written['job-bands.cell']
    assert lines(written['job.param'])[1:9] == [
        'task : geometryoptimization', 'geom_method : LBFGS', 'geom_max_iter : 50', 'geom_energy_tol : 5e-06',
        'geom_force_tol : 0.01', 'geom_disp_tol : 0.0005', 'geom_stress_tol : 0.05', '']


def test_cell_optimisation_lets_the_cell_move():
    calculations = selection(CalculationType.GEOMETRY_OPTIMISATION, geometry_optimisation__optimise='positions_and_cell',
                             geometry_optimisation__convergence='normal')
    written = files(calculations=calculations)
    assert 'fix_all_cell' not in written['job.cell']
    assert 'geom_stress_tol : 0.1' in lines(written['job.param'])


def test_band_path_and_dos_grid():
    calculations = selection(CalculationType.BAND_STRUCTURE, CalculationType.DENSITY_OF_STATES,
                             band_structure__points=40, band_structure__empty_bands=6, density_of_states__grid_factor=3)
    written = files(calculations=calculations)

    block = lines(written['job-bands.cell'])
    rows = block[block.index('%BLOCK SPECTRAL_KPOINT_LIST') + 1:block.index('%ENDBLOCK SPECTRAL_KPOINT_LIST')]
    weights = [float(row.split()[3]) for row in rows]
    assert abs(sum(weights) - 1) < 1e-12  # CASTEP refuses a sum off by 5e-8
    names = [row.split('!')[1].strip() for row in rows if '!' in row]
    assert names[:5] == ['Γ', 'X', 'W', 'K', 'Γ'] and names[-2:] == ['U', 'X']  # the jump K|U: two named rows
    assert rows[0].split()[:3] == ['0.00000000', '0.00000000', '0.00000000']
    assert lines(written['job-bands.param'])[1:5] == ['task : spectral', 'spectral_task : bandstructure',
                                                      'spectral_nextra_bands : 6', 'write_checkpoint : none']
    assert 'spectral_kpoint_mp_grid : 12 12 12' in lines(written['job-dos.cell'])
    assert 'spectral_task : dos' in lines(written['job-dos.param'])


def test_spin_and_charge():
    sample = silicon()
    sample.charge, sample.multiplicity = 1, 2
    param = lines(files(sample, reference='UKS')['job.param'])
    assert {'spin_polarized : true', 'spin : 1', 'spin_fix : -1', 'charge : 1', 'fix_occupancy : false'} <= set(param)
    # Fixed occupations hold the spin anyway.
    assert 'spin_fix : -1' not in files(sample, reference='UKS', occupations='fixed')['job.param']


@pytest.mark.parametrize('calculations, values, message', [
    (selection(CalculationType.VIBRATIONAL_FREQUENCIES, vibrational_frequencies__raman=True), {}, 'Raman'),
    (selection(CalculationType.SINGLE_POINT), {'scf_max_iterations': 2}, 'at least 3 SCF iterations'),
    (selection(CalculationType.GEOMETRY_OPTIMISATION, geometry_optimisation__max_steps=1), {}, 'at least 2 optimisation'),
])
def test_inputs_castep_would_reject_are_refused_before_a_run(calculations, values, message):
    with pytest.raises(ValueError, match=message):
        files(calculations=calculations, **values)


def test_nothing_to_optimise_and_molecules_are_refused():
    sample = silicon()
    for atom in sample.atoms:
        atom.fixed = True
    with pytest.raises(ValueError, match='every atom is fixed'):
        files(sample, selection(CalculationType.GEOMETRY_OPTIMISATION))
    files(sample, selection(CalculationType.GEOMETRY_OPTIMISATION, geometry_optimisation__optimise='positions_and_cell'))
    with pytest.raises(ValueError, match='crystals only'):
        files(Sample.benzene())


# Frequencies: the method and the library


FREQUENCIES = selection(CalculationType.VIBRATIONAL_FREQUENCIES)


@pytest.mark.parametrize('values, task, note', [
    ({'occupations': 'fixed'}, 'phonon+efield', 'Analytical (DFPT) with IR intensities; pseudopotentials NCP19.'),
    ({'occupations': 'fixed', 'dispersion': 'TS'}, 'phonon+efield', 'Analytical (DFPT) with IR intensities; '
                                                                    'pseudopotentials NCP19.'),
    ({'occupations': 'fixed', 'dispersion': 'G06'}, 'phonon+efield', None),
    ({}, 'phonon', 'Finite displacement, no IR intensities: smearing is on.'),
    ({'occupations': 'fixed', 'dispersion': 'D3'}, 'phonon',
     'Finite displacement, no IR intensities: D3 has no analytical second derivatives in CASTEP.'),
    ({'occupations': 'fixed', 'dispersion': 'MBD*'}, 'phonon', None),
    ({'occupations': 'fixed', 'functional': 'RSCAN'}, 'phonon',
     'Finite displacement, no IR intensities: rSCAN has no analytical second derivatives in CASTEP.'),
    ({'occupations': 'fixed', 'reference': 'UKS'}, 'phonon',
     'Finite displacement, no IR intensities: the reference is spin-polarised.'),
    ({'occupations': 'fixed', 'engine_options': {'pseudopotentials': 'C19'}}, 'phonon',
     'Finite displacement, no IR intensities: C19 is not norm-conserving.'),
    ({'occupations': 'fixed', 'engine_options': {'pseudopotentials': 'NCP19'}}, 'phonon+efield', None),
])
def test_the_whole_method_decides_how_frequencies_are_computed(values, task, note):
    sample = silicon()
    sample.multiplicity = 3 if values.get('reference') == 'UKS' else 1
    written = files(sample, FREQUENCIES, **values)
    param = lines(written['job-phonon.param'])
    assert f'task : {task}' in param
    assert ('phonon_method : dfpt' if task == 'phonon+efield' else 'phonon_method : finitedisplacement') in param
    assert 'geom_force_tol : 0.05' in param  # CASTEP's own limit for the forces of a phonon run
    automatic = 'engine_options' not in values
    if automatic:  # Automatic takes NCP19 only when it makes the frequencies analytical
        library = 'NCP19' if task == 'phonon+efield' else 'C19'
        assert lines(written['job.cell'])[lines(written['job.cell']).index('%BLOCK SPECIES_POT') + 1] == library
    if note:
        assert CastepAdapter().frequencies_note(FREQUENCIES, method(**values)) == note


def test_numerical_frequencies_and_no_frequencies():
    numerical = selection(CalculationType.VIBRATIONAL_FREQUENCIES, vibrational_frequencies__type='numerical')
    written = files(calculations=numerical, occupations='fixed')
    assert 'task : phonon' in lines(written['job-phonon.param']) and 'C19' in lines(written['job.cell'])
    assert CastepAdapter().frequencies_note(numerical, method()) == ('Finite displacement, no IR intensities: the type '
                                                                     'is Numerical.')
    assert CastepAdapter().frequencies_note(selection(CalculationType.SINGLE_POINT), method()) == ''


def test_the_optimisation_force_limit_reaches_the_phonon_run():
    calculations = selection(CalculationType.GEOMETRY_OPTIMISATION, CalculationType.VIBRATIONAL_FREQUENCIES,
                             geometry_optimisation__convergence='verytight')
    assert 'geom_force_tol : 0.005' in lines(files(calculations=calculations)['job-phonon.param'])


def test_a_library_without_ir_is_warned_about_with_the_way_out_only_when_there_is_one():
    adapter = CastepAdapter()
    fixed = method(occupations='fixed')
    assert adapter.option_warning('pseudopotentials', 'C19', FREQUENCIES, fixed) == (
        'With C19 the frequencies are computed by finite displacement and have no IR intensities. '
        'NCP19 or Automatic gives both.')
    assert adapter.option_warning('pseudopotentials', 'HARD', FREQUENCIES, method()) == (
        'With HARD the frequencies are computed by finite displacement and have no IR intensities.')
    for name, value, calculations in (('pseudopotentials', 'NCP19', FREQUENCIES),
                                      ('pseudopotentials', 'automatic', FREQUENCIES),
                                      ('pseudopotentials', 'C19', selection(CalculationType.SINGLE_POINT)),
                                      ('basis_precision', 'COARSE', FREQUENCIES)):
        assert adapter.option_warning(name, value, calculations, fixed) == ''


# Engine options and folders of potential files


def _folder(path, *names):
    path.mkdir(parents=True)
    for name in names:
        (path / name).write_text(f'{name} potential\n', encoding='utf-8')
    return path


def test_engine_options_list_the_folders_that_cover_the_sample(tmp_path, monkeypatch):
    root = _folder(tmp_path / 'pspot', 'Na_00.usp', 'Cl_00.usp', 'readme.txt')
    _folder(root / 'pbe', 'na.pbe.recpot', 'cl.pbe.recpot', 'C_00.usp')
    _folder(root / 'twice', 'Na_a.usp', 'Na_b.usp', 'Cl_a.usp')  # two for Na: ambiguous
    _folder(root / 'calcium', 'Ca_00.usp', 'Cl_00.usp')  # C is not Ca, nor Cl
    monkeypatch.setenv('PSPOT_DIR', str(root))

    options = {option.name: option for option in CastepAdapter().engine_options(['Cl', 'Na'])}

    folders = [value for value, _ in options['pseudopotentials'].choices][6:]
    assert folders == [str(root), str(root / 'pbe')]
    assert options['pseudopotentials'].default == 'automatic' and options['basis_precision'].default == 'FINE'
    # C_00.usp is carbon's only file there, not chlorine's; calcium/ has no carbon.
    assert [value for value, _ in CastepAdapter().engine_options(['C', 'Cl'])[0].choices][6:] == [str(root / 'pbe')]
    assert [value for value, _ in CastepAdapter().engine_options([])[0].choices][6:] == []


def test_files_of_a_folder_are_copied_into_the_run_and_named_per_species(tmp_path):
    folder = _folder(tmp_path / 'pbe', 'na.pbe.recpot', 'cl.pbe.recpot')
    written = files(rock_salt(), engine_options={'pseudopotentials': str(folder)})

    cell = lines(written['job.cell'])
    assert cell[cell.index('%BLOCK SPECIES_POT') + 1:cell.index('%ENDBLOCK SPECIES_POT')] == [
        'Cl cl.pbe.recpot', 'Na na.pbe.recpot']
    assert written['na.pbe.recpot'] == 'na.pbe.recpot potential\n'
    with pytest.raises(ValueError, match='exactly one pseudopotential'):
        files(silicon(), engine_options={'pseudopotentials': str(folder)})


# Running and judging the runs


def test_environment_follows_the_cores_setting():
    assert CastepAdapter().environment(RunSettings(cores=2)) == {'OMP_NUM_THREADS': '2', 'OPENBLAS_NUM_THREADS': '2'}


def test_every_run_must_end_with_its_own_footer():
    adapter = CastepAdapter()
    good = '==> job: Ground state\n...\nTotal time = 5 s\n'
    failed = '==> job-dos: Density of states\nError in parameters_restore: corrupted GENERAL block\n'
    assert adapter.succeeded(good) and adapter.step_succeeded(good)
    assert not adapter.succeeded(good + failed) and not adapter.step_succeeded(failed)
    assert not adapter.succeeded('Total time = 5 s\n')  # a header per run
    assert adapter.failure_reason(good) == ''


@pytest.mark.parametrize('text, reason', [
    ('Error in parameters_restore: corrupted GENERAL block\nCurrent trace stack:\n',
     'Error in parameters_restore: corrupted GENERAL block'),
    ('Error: Can not currently compute second derivatives with this SEDC scheme.\nCurrent trace stack:\n',
     'Can not currently compute second derivatives with this SEDC scheme.'),
    (' ?        Maximum force |F|max     = 0.1209     eV/A            ?\n'
     'ERROR: Phonon run aborted because of unoptimised geometry. See job-phonon.castep for more details\n',
     'Frequencies need an optimised geometry: the largest force is 0.121 eV/Å. Tick Optimisation.'),
    ('\nCould not start castep.exe: [WinError 2] The system cannot find the file\n',
     'Could not start castep.exe: [WinError 2] The system cannot find the file'),
    ('  SCF loop      Energy\n', 'the run ended before its closing Total time line'),
])
def test_the_reason_comes_from_the_failed_run_only(text, reason):
    # The completed run before it left an .err file of its own, which must not be the reason.
    output = ('==> job: Ground state\nTotal time = 5 s\n\nError in phonon_LO_analysis: overlap between different irreps?\n'
              f'==> job-phonon: Vibrational frequencies\n{text}')
    assert CastepAdapter().failure_reason(output) == reason


def test_step_markers_follow_the_runs():
    adapter = CastepAdapter()
    steps = [CalculationType.GEOMETRY_OPTIMISATION, CalculationType.SINGLE_POINT, CalculationType.BAND_STRUCTURE,
             CalculationType.DENSITY_OF_STATES]
    output = '==> job: Ground state\n LBFGS: finished iteration     0 with enthalpy= -1.0E+002 eV\n'
    assert adapter.current_step(output, steps) == 0
    output += ' LBFGS: Final Configuration:\n'
    assert adapter.current_step(output, steps) == 1
    output += 'Total time = 1 s\n==> job-bands: Band structure\n'
    assert adapter.current_step(output, steps) == 2
    input_first = [CalculationType.SINGLE_POINT, CalculationType.GEOMETRY_OPTIMISATION]
    assert adapter.current_step(' LBFGS: finished iteration     0 with', input_first) == 1
