# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Engine adapter interface: everything the application knows about a quantum-chemistry code.

GENERAL_DESIGN.md, section 4, rule 1. An adapter detects its executable, lists the choices
it offers, turns the sample, calculations and method into an input file, builds the command
line, and judges from the output whether the job succeeded. Launching the process is the
runner's job (`logic/runner.py`), so all engines look the same to it.
"""

from abc import ABC
from abc import abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

Choices = tuple[tuple[str, str], ...]  # (value, label) pairs, in display order


@dataclass(frozen=True)
class EngineInfo:
    """Result of probing the machine for the engine."""

    found: bool
    version: str = ''
    path: str = ''
    detail: str = ''  # e.g. 'MPI (OpenMPI 4.1)'; not filled in PoC1


@dataclass(frozen=True)
class Capabilities:
    """Every choice list the Method sidebar offers for this engine."""

    families: Choices
    functionals: Choices
    dispersions: Choices
    basis_sets: Choices
    auxiliary_bases: Choices
    references: Choices
    solvations: Choices
    scf_convergences: Choices
    integration_grids: Choices


class EngineAdapter(ABC):
    name: str
    # Files of one job inside its run folder. The engine's standard output is the output file.
    input_file_name = 'job.inp'
    output_file_name = 'job.out'

    # A user-configured executable, tried before PATH.
    executable: Optional[str] = None

    @abstractmethod
    def detect(self) -> EngineInfo: ...

    @abstractmethod
    def capabilities(self) -> Capabilities: ...

    def input_text(self, sample, calculations, method, settings) -> str:
        """The input file for the selected workflow, as one text."""
        raise NotImplementedError(f'{self.name}: input generation is not implemented.')

    def command(self, executable: str, input_path: Path) -> list[str]:
        """Program and arguments; the runner starts it in the run folder."""
        return [executable, input_path.name]

    def succeeded(self, output: str) -> bool:
        """Whether the output shows a normal end of the job."""
        raise NotImplementedError(f'{self.name}: output checking is not implemented.')
