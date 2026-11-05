# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Stand-ins shared by the backend tests: engine adapters that need no engine."""

import sys

from Backends.Py.logic.engines.base import Capabilities
from Backends.Py.logic.engines.base import EngineAdapter
from Backends.Py.logic.engines.base import EngineInfo
from Backends.Py.logic.engines.orca import CAPABILITIES
from Backends.Py.logic.engines.quantum_espresso import CAPABILITIES as QE_CAPABILITIES
from Backends.Py.logic.engines.quantum_espresso import QuantumEspressoAdapter


def emissions(signal) -> list:
    calls = []
    signal.connect(lambda *args: calls.append(args))
    return calls


class FakeAdapter(EngineAdapter):
    name = 'ORCA'

    def __init__(self):
        self.info = EngineInfo(found=False)

    def detect(self) -> EngineInfo:
        return self.info

    def capabilities(self) -> Capabilities:
        return CAPABILITIES


class FakeCrystalAdapter(FakeAdapter):
    name = 'Quantum ESPRESSO'
    systems = ('crystal',)
    programs = ('pw.x', 'pw')

    def capabilities(self) -> Capabilities:
        return QE_CAPABILITIES

    def default_method(self):
        return QuantumEspressoAdapter().default_method()


class ScriptAdapter(FakeAdapter):
    """Runs the input file as a Python script in place of an engine."""

    def input_text(self, sample, calculations, method, settings) -> str:
        if not calculations.workflow():
            raise ValueError('No calculation is selected.')
        return self.script

    def command(self, executable, input_path):
        return [sys.executable, input_path.name]

    def succeeded(self, output: str) -> bool:
        return 'DONE' in output
