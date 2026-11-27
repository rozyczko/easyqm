# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Engine adapter interface: everything the application knows about a quantum-chemistry code.

GENERAL_DESIGN.md, section 4, rule 1. An adapter detects its executable, lists the choices
it offers, turns the sample, calculations and method into an input file, builds the command
line, judges from the output whether the job succeeded, and reads the results from it.
Launching the process is the runner's job (`logic/runner.py`), so all engines look the same
to it.

Every hook below the abstract methods has a default that fits an engine writing one log to
standard output (ORCA, pw.x), so an adapter overrides only what its engine does differently.
"""

import re
import subprocess
import tempfile
from abc import ABC
from abc import abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..calculations import CalculationType
from ..method import Method
from ..method import RunSettings
from ..runner import NO_WINDOW
from ..runner import Step
from ..runner import process_environment

Choices = tuple[tuple[str, str], ...]  # (value, label) pairs, in display order

_BANNER_TIMEOUT = 20  # s


@dataclass(frozen=True)
class EngineInfo:
    """Result of probing the machine for the engine."""

    found: bool
    version: str = ''
    path: str = ''
    detail: str = ''  # e.g. 'MPI (OpenMPI 4.1)'; not filled in PoC1


@dataclass(frozen=True)
class Capabilities:
    """Every choice list the Method sidebar offers for this engine. An empty list hides its row."""

    families: Choices
    functionals: Choices
    dispersions: Choices
    basis_sets: Choices
    auxiliary_bases: Choices
    references: Choices
    solvations: Choices
    scf_convergences: Choices
    integration_grids: Choices
    stability_check: bool = True
    occupations: Choices = ()


@dataclass(frozen=True)
class EngineOption:
    """A choice only this engine has, shown in the Method page's Engine-specific group. Its
    value is `Method.engine_options[name]`; a missing key means `default`."""

    name: str
    label: str
    choices: Choices
    default: str
    tooltip: str = ''


class EngineAdapter(ABC):
    name: str
    # 'molecule' and/or 'crystal'
    systems: tuple[str, ...] = ('molecule',)
    # Program names looked up on PATH, in order.
    programs: tuple[str, ...] = ()
    # Files of one job inside its run folder. The engine's standard output is the output file.
    input_file_name = 'job.inp'
    output_file_name = 'job.out'

    # A user-configured executable, tried before PATH.
    executable: Optional[str] = None
    # Output text that shows a step has started; the first step of a workflow needs none.
    step_markers: dict[CalculationType, re.Pattern] = {}
    # Output text that shows the current step failed, although its program or the next goes on.
    failure_marker: Optional[re.Pattern] = None
    # Whether the input reads the memory run setting (the assistant refuses settings an engine ignores).
    uses_memory = False
    # Whether the engine computes Raman activities.
    raman = True

    @abstractmethod
    def detect(self) -> EngineInfo: ...

    @abstractmethod
    def capabilities(self) -> Capabilities: ...

    def default_method(self) -> Method:
        """The method a new project starts with; its values are among `capabilities()`."""
        return Method()

    def engine_options(self, elements: list[str]) -> tuple[EngineOption, ...]:
        """The options only this engine has, for a sample of these elements."""
        return ()

    def option_warning(self, name: str, value: str, calculations, method) -> str:
        """What the user should know after setting an engine option to `value`, or ''."""
        return ''

    def frequencies_note(self, calculations, method) -> str:
        """One line on how the frequencies will be computed with this method, or ''."""
        return ''

    def system_problem(self, periodic: bool) -> str:
        """Why this engine cannot run the sample, or '' if it can."""
        if ('crystal' if periodic else 'molecule') in self.systems:
            return ''
        runs = ' and '.join(f'{system}s' for system in self.systems)
        return f'{self.name} runs {runs} only; this sample is {"periodic" if periodic else "a molecule"}.'

    def input_text(self, sample, calculations, method, settings) -> str:
        """The input file for the selected workflow, as one text."""
        raise NotImplementedError(f'{self.name}: input generation is not implemented.')

    def input_files(self, sample, calculations, method, settings) -> dict[str, str]:
        """Every input file of the workflow, by file name; the first is the main one."""
        return {self.input_file_name: self.input_text(sample, calculations, method, settings)}

    def command(self, executable: str, input_path: Path) -> list[str]:
        """Program and arguments; the runner starts it in the run folder."""
        return [executable, input_path.name]

    def commands(self, executable: str, input_names: list[str]) -> list[list[str]]:
        """The programs of the workflow, run one after the other on the files of `input_files`."""
        return [self.command(executable, Path(input_names[0]))]

    def steps(self, executable: str, input_names: list[str]) -> list[Step]:
        """The steps the runner takes; by default each command, its log on standard output."""
        return [Step(command) for command in self.commands(executable, input_names)]

    def environment(self, settings: RunSettings) -> dict[str, str]:
        """Variables the engine's processes get on top of the application's; PATH goes in front."""
        return {}

    def step_succeeded(self, text: str) -> bool:
        """Whether the text of a step that exited with code 0 shows it ended well."""
        return True

    def failure_reason(self, output: str) -> str:
        """Why the job whose output this is failed, in one sentence for the user, or ''."""
        return ''

    def current_step(self, output: str, steps: list[CalculationType]) -> int:
        """Index in `steps` of the last step whose start shows in `output` before any failure,
        0 before any."""
        if self.failure_marker is not None:
            output = self.failure_marker.split(output, maxsplit=1)[0]
        markers = self.step_markers
        return max((i for i, step in enumerate(steps) if step in markers and markers[step].search(output)), default=0)

    def succeeded(self, output: str) -> bool:
        """Whether the output shows a normal end of the job."""
        raise NotImplementedError(f'{self.name}: output checking is not implemented.')

    def parse(self, output: str):
        """The results found in the output, as a `logic.results.Results`."""
        raise NotImplementedError(f'{self.name}: output parsing is not implemented.')

    def read_results(self, folder: Optional[Path], output: str):
        """The results of a job from its output and the files in its run folder (None when
        the job got no folder); by default from the output alone."""
        return self.parse(output)


@dataclass(frozen=True)
class Probe:
    """What a program printed to standard output, and its exit code; None if it did not end."""

    text: str
    code: Optional[int]


def probe(command: list[str], environment: Optional[dict[str, str]] = None) -> Probe:
    """Start a program in an empty folder and wait for it, with `environment` on top of the
    application's. A program that cannot be started or does not end in time gives code None."""
    with tempfile.TemporaryDirectory(prefix='easyqm-') as folder:
        try:
            result = subprocess.run(
                command,
                cwd=folder,
                env=process_environment(environment) if environment else None,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                errors='replace',
                timeout=_BANNER_TIMEOUT,
                creationflags=NO_WINDOW,
            )
        except (OSError, subprocess.SubprocessError):
            return Probe('', None)
    return Probe(result.stdout or '', result.returncode)


def banner(command: list[str]) -> str:
    """What a program prints when started in an empty folder, e.g. with a missing input file.

    Engines print their version in a banner before they complain, which is quicker and more
    reliable than a version option most of them lack.
    """
    return probe(command).text
