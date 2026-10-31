# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
from dataclasses import fields
from types import SimpleNamespace

import pytest

from Backends.Py.logic.calculations import Calculations
from Backends.Py.logic.calculations import CalculationType
from Backends.Py.logic.engines import orca
from Backends.Py.logic.engines.orca import OrcaAdapter
from Backends.Py.logic.method import Method
from Backends.Py.logic.method import RunSettings
from Backends.Py.logic.sample import Sample


def test_not_found_without_executable(monkeypatch):
    monkeypatch.setattr(orca.shutil, 'which', lambda name: None)
    info = OrcaAdapter().detect()
    assert not info.found
    assert info.version == '' and info.path == ''


def test_found_with_version_from_folder(tmp_path, monkeypatch):
    executable = tmp_path / 'orca' / '6.0.1' / 'orca'
    executable.parent.mkdir(parents=True)
    executable.write_text('', encoding='utf-8')
    monkeypatch.setattr(orca.shutil, 'which', lambda name: str(executable))

    info = OrcaAdapter().detect()

    assert info.found
    assert info.version == '6.0.1'
    assert info.path == str(executable)


def test_configured_path_wins_and_must_exist(tmp_path, monkeypatch):
    monkeypatch.setattr(orca.shutil, 'which', lambda name: None)
    assert not OrcaAdapter(str(tmp_path / 'missing')).detect().found

    executable = tmp_path / 'orca_6_0_0' / 'orca.exe'
    executable.parent.mkdir()
    executable.write_text('', encoding='utf-8')
    info = OrcaAdapter(str(executable)).detect()
    assert info.found and info.version == '6.0.0'


def test_version_from_banner_when_folder_has_none(tmp_path, monkeypatch):
    executable = tmp_path / 'ORCA' / 'orca.exe'
    executable.parent.mkdir()
    executable.write_text('', encoding='utf-8')
    banner = '   Program Version 6.1.1  -  RELEASE   -\n'
    monkeypatch.setattr(orca.subprocess, 'run', lambda *args, **kwargs: SimpleNamespace(stdout=banner))

    assert OrcaAdapter(str(executable)).detect().version == '6.1.1'


def test_version_probe_failure_leaves_version_empty(tmp_path, monkeypatch):
    executable = tmp_path / 'ORCA' / 'orca.exe'
    executable.parent.mkdir()
    executable.write_text('', encoding='utf-8')

    def fail(*args, **kwargs):
        raise OSError('not a program')

    monkeypatch.setattr(orca.subprocess, 'run', fail)
    info = OrcaAdapter(str(executable)).detect()
    assert info.found and info.version == ''


def test_method_defaults_are_orca_choices():
    capabilities = OrcaAdapter().capabilities()
    method = Method()
    pairs = {
        'family': capabilities.families,
        'functional': capabilities.functionals,
        'dispersion': capabilities.dispersions,
        'basis_set': capabilities.basis_sets,
        'auxiliary_basis': capabilities.auxiliary_bases,
        'reference': capabilities.references,
        'solvation': capabilities.solvations,
        'scf_convergence': capabilities.scf_convergences,
        'integration_grid': capabilities.integration_grids,
    }
    for name, choices in pairs.items():
        assert getattr(method, name) in [value for value, _ in choices], name
    assert {field.name for field in fields(Method)} - set(pairs) == {'scf_max_iterations', 'stability_check'}


# Input generation


def _input(*steps, method=None, configure=None) -> str:
    sample = Sample.benzene()
    calculations = Calculations()
    for step in steps:
        calculations.set_selected(step, True)
    if configure is not None:
        configure(sample, calculations)
    return OrcaAdapter().input_text(sample, calculations, method or Method(), RunSettings(memory_gb=4))


def test_single_point_input():
    text = _input(CalculationType.SINGLE_POINT)
    lines = text.splitlines()

    assert lines[0] == '# EasyQM: benzene (C6H6) - Single point energy'
    assert lines[1] == '! B3LYP D3BJ RKS def2-TZVP def2/J RIJCOSX TightSCF DefGrid2 PrintMOs'
    assert '%maxcore 3072' in lines
    assert '%scf\n  MaxIter 125\nend' in text
    assert '* xyz 0 1' in lines
    assert lines[-1] == '*'
    assert lines[-2].split() == ['H', '-2.14250000', '1.23700000', '0.00000000']
    assert '$new_job' not in text and '%geom' not in text and '%freq' not in text


def test_optimisation_and_frequencies_in_one_job():
    def configure(sample, calculations):
        sample.atoms[0].fixed = True
        sample.atoms[6].fixed = True

    text = _input(CalculationType.GEOMETRY_OPTIMISATION, CalculationType.VIBRATIONAL_FREQUENCIES, configure=configure)

    assert text.splitlines()[1].endswith('DefGrid2 TightOpt Freq')
    assert '%geom\n  MaxIter 100\n  Constraints\n    {C 0 C}\n    {C 6 C}\n  end\nend' in text
    assert '%freq\n  Temp 298.15\n  Pressure 1\nend' in text
    assert 'PrintMOs' not in text and '$new_job' not in text


def test_single_point_at_input_geometry_is_a_separate_first_job():
    def configure(sample, calculations):
        calculations.single_point.geometry = 'input'

    text = _input(CalculationType.SINGLE_POINT, CalculationType.GEOMETRY_OPTIMISATION, configure=configure)
    first, second = text.split('\n$new_job\n')

    assert first.splitlines()[0] == '# EasyQM: benzene (C6H6) - Single point energy, Geometry optimisation'
    assert first.splitlines()[1].endswith('DefGrid2 PrintMOs')
    assert second.splitlines()[0].endswith('DefGrid2 TightOpt')
    assert first.count('* xyz 0 1') == second.count('* xyz 0 1') == 1


def test_raman_switches_to_numerical_frequencies():
    def configure(sample, calculations):
        calculations.vibrational_frequencies.raman = True

    text = _input(CalculationType.VIBRATIONAL_FREQUENCIES, configure=configure)

    assert text.splitlines()[1].endswith(' NumFreq')
    assert '%elprop\n  Polar 1\nend' in text


def test_hartree_fock_and_other_method_keywords():
    method = Method(
        family='HF',
        reference='UKS',
        auxiliary_basis='none',
        solvation='CPCM(water)',
        scf_convergence='verytight',
        integration_grid='DefGrid3',
        stability_check=True,
    )
    text = _input(CalculationType.SINGLE_POINT, method=method)

    assert text.splitlines()[1] == '! HF UHF def2-TZVP NoRI CPCM(water) VeryTightSCF DefGrid3 PrintMOs'
    assert '  STABPerform true' in text


def test_input_needs_a_calculation():
    with pytest.raises(ValueError):
        _input()


def test_success_is_the_normal_termination_line():
    adapter = OrcaAdapter()
    assert adapter.succeeded('...\n                             ****ORCA TERMINATED NORMALLY****\n')
    assert not adapter.succeeded('ORCA finished by error termination in SCF')
