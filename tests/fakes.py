# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Stand-ins shared by the backend tests: engine adapters that need no engine, and speech that
needs no microphone, model or voice."""

import sys
import threading
from types import SimpleNamespace

from PySide6.QtCore import QObject
from PySide6.QtCore import Signal

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


class FakeSpeaker(QObject):
    """QTextToSpeech's part that `Voice` uses: speaking lasts until `stop`. The states stand in
    for QTextToSpeech.State, which `Voice` tells apart by name."""

    stateChanged = Signal(object)

    def __init__(self):
        super().__init__()
        self.said, self.stops = [], 0

    def say(self, text):
        self.said.append(text)
        self.stateChanged.emit(SimpleNamespace(name='Speaking'))

    def stop(self):
        self.stops += 1
        self.stateChanged.emit(SimpleNamespace(name='Ready'))


class FakeRecogniser:
    """Gives each recording the next scripted text (or raises it, for an exception); waits for
    `gate` first when one is given."""

    def __init__(self, *texts, gate: threading.Event = None):
        self.texts, self.gate, self.calls, self.loaded = list(texts), gate, [], False
        self.folder = 'speech-models'

    def transcribe(self, audio, prompt=''):
        self.calls.append((audio, prompt))
        if self.gate is not None:
            self.gate.wait(5)
        self.loaded = True
        text = self.texts.pop(0)
        if isinstance(text, Exception):
            raise text
        return text


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
