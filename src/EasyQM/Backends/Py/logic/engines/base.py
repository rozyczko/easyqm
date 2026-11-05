# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Engine adapter interface: everything the application knows about a quantum-chemistry code.

GENERAL_DESIGN.md, section 4, rule 1. An adapter detects its executable, lists the choices
it offers, turns the sample, calculations and method into an input file, builds the command
line, judges from the output whether the job succeeded, and reads the results from it.
Launching the process is the runner's job (`logic/runner.py`), so all engines look the same
to it.
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
from ..runner import NO_WINDOW

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

    @abstractmethod
    def detect(self) -> EngineInfo: ...

    @abstractmethod
    def capabilities(self) -> Capabilities: ...

    def default_method(self) -> Method:
        """The method a new project starts with; its values are among `capabilities()`."""
        return Method()

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


def banner(command: list[str]) -> str:
    """What a program prints when started in an empty folder, e.g. with a missing input file.

    Engines print their version in a banner before they complain, which is quicker and more
    reliable than a version option most of them lack.
    """
    with tempfile.TemporaryDirectory(prefix='easyqm-') as folder:
        try:
            result = subprocess.run(
                command,
                cwd=folder,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                errors='replace',
                timeout=_BANNER_TIMEOUT,
                creationflags=NO_WINDOW,
            )
        except (OSError, subprocess.SubprocessError):
            return ''
    return result.stdout or ''
