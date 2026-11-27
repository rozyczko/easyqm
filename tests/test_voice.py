# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Speech for the assistant panel: the recording as Whisper takes it, the recogniser's priming,
answers as text to read aloud, and the Voice part with a fake recogniser and speaker. No test
needs a microphone, the speech model or a system voice."""

import threading
import time

import numpy as np
import pytest
from PySide6.QtCore import QSettings

import Backends.Py.voice as voice_module
from Backends.Py.assistant_settings import AssistantSettings
from Backends.Py.logic.engines.orca import CAPABILITIES as ORCA
from Backends.Py.logic.engines.quantum_espresso import CAPABILITIES as QE
from Backends.Py.logic.speech import speech_text
from Backends.Py.logic.speech import vocabulary_prompt
from Backends.Py.logic.speech import whisper_audio
from Backends.Py.voice import Voice
from fakes import FakeRecogniser
from fakes import FakeSpeaker
from fakes import emissions

SECOND = np.zeros(16000, dtype=np.int16).tobytes()  # one second of silence, mono, 16 kHz


def _wait(condition, application, seconds: float = 5) -> None:
    end = time.monotonic() + seconds
    while not condition():
        assert time.monotonic() < end, 'timed out'
        application.processEvents()
        time.sleep(0.01)


# Qt-free


def test_the_recogniser_is_primed_with_the_engines_terms():
    prompt = vocabulary_prompt((ORCA, QE))
    for term in ('B3LYP', 'def2-TZVP', 'cc-pVDZ', 'D3(BJ)', 'EOM-CCSD', 'HOMO', 'basis set'):
        assert term in prompt
    assert 'None' not in prompt
    assert len(prompt) < 600  # Whisper keeps only the last 224 tokens of a prompt


def test_a_recording_becomes_what_whisper_takes():
    # Stereo 16-bit at 48 kHz, half a second: the channels are averaged and the rate converted.
    stereo = np.tile(np.array([16384, 0], dtype=np.int16), 24000).tobytes()
    audio = whisper_audio(stereo, 48000, 2, 'int16')
    assert audio.dtype == np.float32 and len(audio) == 8000
    assert np.allclose(audio, 0.25)

    # A laptop's microphone array: 4 channels of 32-bit float at 48 kHz.
    array = np.tile(np.array([0.4, 0.2, 0.2, 0.0], dtype=np.float32), 4800).tobytes()
    assert np.allclose(whisper_audio(array, 48000, 4, 'float'), 0.2) and len(whisper_audio(array, 48000, 4, 'float')) == 1600

    unsigned = np.full(1600, 192, dtype=np.uint8).tobytes()  # 8-bit is unsigned around 128
    assert np.allclose(whisper_audio(unsigned, 16000, 1, 'uint8'), 0.5)
    assert len(whisper_audio(b'\x00\x00\x00', 16000, 1, 'int16')) == 1  # a torn sample is dropped


def test_an_answer_is_read_as_plain_sentences():
    answer = ('## Result\n'
              'The **final energy** is −76.3218 Eh; the gap is 9.14 eV (see [the tab](summary)).\n\n'
              '- Basis: `def2-TZVP`, after the `single_point` step\n'
              '- Lowest excitation at 164.5 nm\n\n'
              '| State | E |\n|---|---|\n| 1 | 7.5 |\n\n'
              '```\n! B3LYP def2-TZVP\n```\n'
              'Strongest band at 1650 cm-1')
    assert speech_text(answer) == (
        'Result. The final energy is -76.3218 hartree; the gap is 9.14 electronvolts (see the tab). '
        'Basis: def2-TZVP, after the single point step. Lowest excitation at 164.5 nanometres. '
        '(The table is shown in the panel.) (The code is shown in the panel.) Strongest band at 1650 per centimetre.')
    assert speech_text('') is None and speech_text('**  **') is None


def test_a_table_without_outer_pipes_is_left_to_the_panel():
    answer = 'The gaps:\n\nEnergy | Value\n:--- | ---:\nGap | 1 eV\nVBM | 6 eV\n\nSo it is a or b | c.'
    assert speech_text(answer) == 'The gaps: (The table is shown in the panel.) So it is a or b | c.'


# The Voice part


@pytest.fixture
def settings(tmp_path):
    settings = AssistantSettings(QSettings(str(tmp_path / 'settings.ini'), QSettings.Format.IniFormat))
    settings.setSpeechInput(True)
    return settings


def test_speech_becomes_text_for_the_input_box(settings, qcore_application):
    recogniser = FakeRecogniser('Use def2-SVP')
    voice = Voice(settings, recogniser=recogniser)
    texts, states = emissions(voice.transcribed), emissions(voice.stateChanged)

    voice.recognise(SECOND, 16000, 1, 'int16')
    assert voice.transcribing and 'downloaded' in voice.message  # the model loads on first use
    _wait(lambda: not voice.transcribing, qcore_application)

    assert texts == [('Use def2-SVP',)] and voice.message == '' and states
    audio, prompt = recogniser.calls[0]
    assert len(audio) == 16000 and 'def2-TZVP' in prompt


def test_a_click_silence_or_failure_gives_no_text(settings, qcore_application):
    voice = Voice(settings, recogniser=FakeRecogniser('', RuntimeError('model file damaged')))
    texts = emissions(voice.transcribed)

    voice.recognise(SECOND[:3200], 16000, 1, 'int16')  # 0.1 s: a click on the button
    assert not voice.transcribing and voice.message.startswith('Hold the button')

    voice.recognise(SECOND, 16000, 1, 'int16')
    _wait(lambda: not voice.transcribing, qcore_application)
    assert voice.message.startswith('Nothing was recognised')

    voice.recognise(SECOND, 16000, 1, 'int16')
    _wait(lambda: not voice.transcribing, qcore_application)
    assert voice.message == 'Speech recognition failed: model file damaged' and texts == []


def test_a_cancelled_recognition_gives_no_text(settings, qcore_application):
    gate = threading.Event()
    voice = Voice(settings, recogniser=FakeRecogniser('too late', gate=gate))
    texts = emissions(voice.transcribed)

    voice.recognise(SECOND, 16000, 1, 'int16')
    voice.cancel()
    assert not voice.transcribing
    gate.set()
    deadline = time.monotonic() + 0.3
    while time.monotonic() < deadline:  # the worker's late answer arrives, and is dropped
        qcore_application.processEvents()
    assert texts == []


def test_turning_speech_input_off_drops_a_recognition_in_progress(settings, qcore_application):
    gate = threading.Event()
    voice = Voice(settings, recogniser=FakeRecogniser('said before the opt-out', gate=gate))
    texts = emissions(voice.transcribed)

    voice.recognise(SECOND, 16000, 1, 'int16')
    settings.setSpeechInput(False)
    assert not voice.transcribing and not voice.inputEnabled
    gate.set()
    deadline = time.monotonic() + 0.3
    while time.monotonic() < deadline:
        qcore_application.processEvents()
    assert texts == []


def test_turning_reading_aloud_off_stops_the_answer(settings, qcore_application):
    speaker = FakeSpeaker()
    voice = Voice(settings, recogniser=FakeRecogniser(), speaker=speaker)
    settings.setReadAloud(True)
    voice.speak('A long answer.')
    settings.setReadAloud(False)
    assert speaker.stops == 1 and not voice.speaking


def test_speech_input_is_off_until_turned_on(tmp_path, qcore_application, monkeypatch):
    settings = AssistantSettings(QSettings(str(tmp_path / 'settings.ini'), QSettings.Format.IniFormat))
    voice = Voice(settings, recogniser=FakeRecogniser())
    states = emissions(voice.stateChanged)
    assert not voice.inputEnabled
    voice.startListening()
    assert not voice.listening and voice.message == ''

    settings.setSpeechInput(True)
    assert voice.inputEnabled and states
    monkeypatch.setattr(voice_module, 'recogniser_available', lambda: False)
    voice.startListening()  # before any microphone is opened
    assert not voice.listening and 'pip install "EasyQM[voice]"' in voice.message


def test_answers_are_read_aloud_only_when_turned_on(settings, qcore_application):
    speaker = FakeSpeaker()
    voice = Voice(settings, recogniser=FakeRecogniser(), speaker=speaker)
    voice.speak('**Done.**')
    assert speaker.said == []

    settings.setReadAloud(True)
    voice.speak('**Done.**')
    assert speaker.said == ['Done.'] and voice.speaking
    voice.stopSpeaking()
    assert speaker.stops == 1 and not voice.speaking
    voice.stopSpeaking()  # nothing to stop
    assert speaker.stops == 1
