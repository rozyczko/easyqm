# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Assistant panel speech: push-to-talk recognised on this computer, and answers read aloud.
The assistant settings turn each on; both are off at first.

While the talk button or Ctrl+Space is held, the default microphone records. On release the
recording is recognised on a worker thread (`logic.speech.Recogniser`), and the text comes back
as `transcribed`, for the panel to put into the input box. Nothing is recorded otherwise, and
no recording is kept. Answers are read with the system's voices (Qt TextToSpeech).

Qt Multimedia and Qt TextToSpeech are imported on first use: where their system libraries are
missing, the application still starts, and only speech says why it cannot work.
"""

import threading
from pathlib import Path

from PySide6.QtCore import Property
from PySide6.QtCore import QObject
from PySide6.QtCore import QStandardPaths
from PySide6.QtCore import Signal
from PySide6.QtCore import Slot

from .assistant_settings import AssistantSettings
from .logic.engines.orca import CAPABILITIES as ORCA_CAPABILITIES
from .logic.engines.quantum_espresso import CAPABILITIES as QE_CAPABILITIES
from .logic.speech import SPEECH_MODEL_MB
from .logic.speech import Recogniser
from .logic.speech import recogniser_available
from .logic.speech import speech_text
from .logic.speech import vocabulary_prompt
from .logic.speech import whisper_audio

MIN_SECONDS = 0.3  # a shorter recording is a click, not speech
_FORMATS = {'UInt8': 'uint8', 'Int16': 'int16', 'Int32': 'int32', 'Float': 'float'}  # QAudioFormat's names
_BYTES = {'uint8': 1, 'int16': 2, 'int32': 4, 'float': 4}


def model_folder() -> Path:
    """Where the speech model is downloaded to: beside other applications' data, not in a project."""
    data = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericDataLocation)
    return Path(data) / 'EasyQM' / 'speech-models'


class _Bridge(QObject):
    """The worker thread's result, delivered on the main thread."""

    done = Signal(int, object)  # (generation, the text or the exception)


class Voice(QObject):
    stateChanged = Signal()
    transcribed = Signal(str)  # recognised speech, for the input box

    def __init__(self, settings: AssistantSettings, recogniser=None, speaker=None, parent=None):
        super().__init__(parent)
        self._settings = settings
        settings.changed.connect(self._settings_changed)
        self._recogniser = recogniser if recogniser is not None else Recogniser(model_folder())
        self._prompt = vocabulary_prompt((ORCA_CAPABILITIES, QE_CAPABILITIES))
        self._speaker = None  # a QTextToSpeech, made on first use
        if speaker is not None:
            self._use_speaker(speaker)
        self._source = None  # the QAudioSource while listening
        self._input = None  # the QIODevice the source writes to
        self._format = (0, 0, '')  # sample rate, channels, sample format of the recording
        self._audio = bytearray()
        self._listening = self._transcribing = self._speaking = False
        self._message = ''
        self._generation = 0  # raised by cancel: a recognition still running is then dropped
        self._bridge = _Bridge(self)
        self._bridge.done.connect(self._on_done)

    # State for the panel

    @Property(bool, notify=stateChanged)
    def inputEnabled(self) -> bool:
        """Whether the panel shows the talk button."""
        return self._settings.speechInput

    @Property(bool, constant=True)
    def recognitionAvailable(self) -> bool:
        return recogniser_available()

    @Property(str, constant=True)
    def modelFolder(self) -> str:
        return str(self._recogniser.folder)

    @Property(int, constant=True)
    def modelMegabytes(self) -> int:
        return SPEECH_MODEL_MB

    @Property(bool, notify=stateChanged)
    def listening(self) -> bool:
        return self._listening

    @Property(bool, notify=stateChanged)
    def transcribing(self) -> bool:
        return self._transcribing

    @Property(bool, notify=stateChanged)
    def speaking(self) -> bool:
        return self._speaking

    @Property(str, notify=stateChanged)
    def message(self) -> str:
        """Why nothing was transcribed, or that the model is loading; '' otherwise."""
        return self._message

    # Push-to-talk

    @Slot()
    def startListening(self) -> None:
        if self._listening or self._transcribing or not self._settings.speechInput:
            return
        self.stopSpeaking()  # the user talks over the answer
        if not recogniser_available():
            self._set_message('Speech recognition needs the voice extra: pip install "EasyQM[voice]".')
            return
        try:
            from PySide6.QtMultimedia import QAudioSource
            from PySide6.QtMultimedia import QMediaDevices
        except ImportError as error:
            self._set_message(f'Audio input is not available here: {error}')
            return
        device = QMediaDevices.defaultAudioInput()
        if device.isNull():
            self._set_message('No microphone was found.')
            return
        audio_format = device.preferredFormat()
        sample_format = _FORMATS.get(audio_format.sampleFormat().name)
        if sample_format is None:
            self._set_message(f'The microphone {device.description()} gives a sample format this cannot read.')
            return
        self._source = QAudioSource(device, audio_format, self)
        self._input = self._source.start()
        if self._input is None:
            self._close_source()
            self._set_message(f'The microphone {device.description()} could not be opened.')
            return
        self._input.readyRead.connect(self._read)
        self._format = (audio_format.sampleRate(), audio_format.channelCount(), sample_format)
        self._audio.clear()
        self._listening, self._message = True, ''
        self.stateChanged.emit()

    @Slot()
    def stopListening(self) -> None:
        """Release: recognise what was recorded."""
        if not self._listening:
            return
        self._read()
        self._close_source()
        self._listening = False
        data, self._audio = bytes(self._audio), bytearray()
        self.recognise(data, *self._format)

    def recognise(self, data: bytes, rate: int, channels: int, sample_format: str) -> None:
        """Recognise a recording on a worker thread; the text comes as `transcribed`."""
        if len(data) < MIN_SECONDS * rate * channels * _BYTES[sample_format]:
            self._set_message('Hold the button, or Ctrl+Space, while you speak.')
            return
        self._transcribing = True
        self._message = '' if self._recogniser.loaded else (
            f'Loading the speech model; the first time, it is downloaded (about {SPEECH_MODEL_MB} MB).')
        self.stateChanged.emit()
        generation, recogniser, prompt = self._generation, self._recogniser, self._prompt

        def work() -> None:
            try:
                result = recogniser.transcribe(whisper_audio(data, rate, channels, sample_format), prompt)
            except Exception as error:  # reported in the panel; the thread must always answer
                result = error
            self._bridge.done.emit(generation, result)

        threading.Thread(target=work, name='speech-recognition', daemon=True).start()

    @Slot()
    def cancel(self) -> None:
        """Stop listening or recognising: nothing is transcribed."""
        self._generation += 1
        if self._listening or self._transcribing:
            self._close_source()
            self._audio.clear()
            self._listening = self._transcribing = False
            self.stateChanged.emit()

    def _read(self) -> None:
        if self._input is not None:
            self._audio += self._input.readAll().data()

    def _close_source(self) -> None:
        if self._source is not None:
            self._source.stop()
            self._source.deleteLater()
        self._source = self._input = None

    def _on_done(self, generation: int, result) -> None:
        if generation != self._generation:
            return  # cancelled meanwhile
        self._transcribing = False
        if isinstance(result, Exception):
            self._message = f'Speech recognition failed: {result}'
        else:
            self._message = '' if result else 'Nothing was recognised. Try again, closer to the microphone.'
        self.stateChanged.emit()
        if isinstance(result, str) and result:
            self.transcribed.emit(result)

    # Reading aloud

    def speak(self, text: str) -> None:
        """Read an answer aloud, as plain sentences, when the settings say so."""
        spoken = speech_text(text) if self._settings.readAloud else None
        if not spoken:
            return
        if self._speaker is None:
            try:
                from PySide6.QtTextToSpeech import QTextToSpeech
            except ImportError as error:
                self._set_message(f'Reading aloud is not available here: {error}')
                return
            self._use_speaker(QTextToSpeech(self))
        self._speaker.say(spoken)

    @Slot()
    def stopSpeaking(self) -> None:
        if self._speaker is not None and self._speaking:
            self._speaker.stop()

    def _use_speaker(self, speaker) -> None:
        self._speaker = speaker
        speaker.stateChanged.connect(self._speaker_state)

    def _speaker_state(self, state) -> None:
        speaking = state.name == 'Speaking'  # a QTextToSpeech.State
        if speaking != self._speaking:
            self._speaking = speaking
            self.stateChanged.emit()

    def _set_message(self, message: str) -> None:
        self._message = message
        self.stateChanged.emit()

    def _settings_changed(self) -> None:
        """Turning speech input off drops a recording or recognition in progress, and turning
        reading aloud off stops the answer being read."""
        if not self._settings.speechInput:
            self.cancel()
        if not self._settings.readAloud:
            self.stopSpeaking()
        self.stateChanged.emit()
