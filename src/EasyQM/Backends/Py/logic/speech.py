# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Speech for the assistant panel, Qt-free: recognising what the user says, and an answer as
text to read aloud.

Speech is recognised on this computer with faster-whisper (the optional `voice` extra); the
recording never leaves it, and the transcript goes to the model like typed text. Whisper is
primed with the terms the engines offer, so that 'def2-TZVP' comes out as written.
"""

import importlib.util
import os
import re
import threading
from pathlib import Path
from typing import Optional

import numpy as np

# English-only and small: about 140 MB, a second or two per sentence on a laptop CPU.
SPEECH_MODEL = 'base.en'
SPEECH_MODEL_MB = 140
WHISPER_RATE = 16000  # Hz, the sample rate Whisper takes
# Terms of the application's own that no choice list holds.
_TERMS = ('EasyQM', 'ORCA', 'Quantum ESPRESSO', 'basis set', 'Hartree-Fock', 'DFT', 'TD-DFT', 'TDA', 'EOM-CCSD',
          'roots', 'SCF', 'HOMO', 'LUMO', 'Z-matrix', 'k-points', 'singlet', 'doublet', 'triplet', 'multiplicity')
_SCALE = {'uint8': 128.0, 'int16': 32768.0, 'int32': 2147483648.0, 'float': 1.0}
_DTYPE = {'uint8': np.uint8, 'int16': np.int16, 'int32': np.int32, 'float': np.float32}


def recogniser_available() -> bool:
    return importlib.util.find_spec('faster_whisper') is not None


def vocabulary_prompt(capabilities) -> str:
    """The terms Whisper should expect, from the engines' choice lists (`Capabilities`). Whisper
    reads it as the conversation so far, so it spells these terms as they are listed."""
    labels = [label for caps in capabilities
              for choices in (caps.functionals, caps.dispersions, caps.basis_sets)
              for value, label in choices if value != 'none']
    return 'Quantum chemistry in ' + ', '.join(dict.fromkeys((*_TERMS, *labels))) + '.'


def whisper_audio(data: bytes, rate: int, channels: int, sample_format: str) -> np.ndarray:
    """Recorded PCM (as the microphone gives it) as Whisper takes it: mono float32 at 16 kHz."""
    samples = np.frombuffer(data[:len(data) - len(data) % np.dtype(_DTYPE[sample_format]).itemsize],
                            dtype=_DTYPE[sample_format]).astype(np.float32)
    if sample_format == 'uint8':
        samples -= 128.0
    samples /= _SCALE[sample_format]
    samples = samples[:len(samples) - len(samples) % channels].reshape(-1, channels).mean(axis=1)
    if rate != WHISPER_RATE and len(samples):
        times = np.arange(round(len(samples) * WHISPER_RATE / rate)) * (rate / WHISPER_RATE)
        samples = np.interp(times, np.arange(len(samples)), samples).astype(np.float32)
    return samples


class Recogniser:
    """faster-whisper, loaded on first use: the first use downloads the model into `folder`."""

    def __init__(self, folder: Path, model: str = SPEECH_MODEL):
        self.folder, self._name = Path(folder), model
        self._model = None
        self._lock = threading.Lock()  # one recognition at a time, one download

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def transcribe(self, audio: np.ndarray, prompt: str = '') -> str:
        with self._lock:
            if self._model is None:
                # Without symlink rights (Windows) the download copies files, which is fine: no warning.
                os.environ.setdefault('HF_HUB_DISABLE_SYMLINKS_WARNING', '1')
                from faster_whisper import WhisperModel

                self.folder.mkdir(parents=True, exist_ok=True)
                self._model = WhisperModel(self._name, device='cpu', compute_type='int8',
                                           download_root=str(self.folder))
            # The voice-activity filter drops the silence around the words, where Whisper invents text.
            segments, _ = self._model.transcribe(audio, language='en', initial_prompt=prompt or None,
                                                 vad_filter=True)
            return ' '.join(segment.text.strip() for segment in segments).strip()


# Reading an answer aloud

_FENCE = re.compile(r'```.*?(?:```|$)', re.DOTALL)
_LINK = re.compile(r'\[([^\]]*)\]\([^)]*\)')
_MARKS = re.compile(r'\*\*|__|`|~~|(?<!\w)[*_](?=\S)|(?<=\S)[*_](?!\w)')
_LIST = re.compile(r'^\s*(?:#{1,6}\s+|>\s*|[-*+]\s+|\d+[.)]\s+)')
_MINUS = re.compile(r'[−–](?=\d)')  # a typographic minus before a number
# Units as words: a speech engine spells 'Eh' or 'cm-1' out letter by letter.
_UNITS = (
    (re.compile(r'(?<=\d) ?Eh\b'), ' hartree'),
    (re.compile(r'(?<=\d) ?eV\b'), ' electronvolts'),
    (re.compile(r'(?<=\d) ?kcal/mol\b'), ' kilocalories per mole'),
    (re.compile(r'(?<=\d) ?cm(?:-1|⁻¹|\^-1)'), ' per centimetre'),
    (re.compile(r'(?<=\d) ?nm\b'), ' nanometres'),
    (re.compile(r'(?<=\d) ?Å'), ' ångström'),
)


def speech_text(markdown: str) -> Optional[str]:
    """An answer as plain sentences to read aloud: code and tables are left to the panel, the
    Markdown marks go, units are written out. None when nothing is left to say."""
    rows = _FENCE.sub('\n(The code is shown in the panel.)\n', markdown).splitlines()
    lines, i = [], 0
    while i < len(rows):
        line = rows[i]
        i += 1
        # A table: rows in pipes, or a header row over a delimiter row ('--- | ---') without them.
        if line.lstrip().startswith('|') or ('|' in line and i < len(rows) and _delimiter_row(rows[i])):
            lines.append('(The table is shown in the panel.)')
            while i < len(rows) and '|' in rows[i]:
                i += 1
            continue
        # single_point is said 'single point', not 'single underscore point'
        line = _MARKS.sub('', _LINK.sub(r'\1', _LIST.sub('', line))).replace('_', ' ').strip()
        if line:
            lines.append(line if line[-1] in '.!?:;)' else line + '.')
    spoken = _MINUS.sub('-', ' '.join(lines))
    for pattern, words in _UNITS:
        spoken = pattern.sub(words, spoken)
    return spoken or None


def _delimiter_row(line: str) -> bool:
    """The row under a Markdown table's header: dashes, colons and pipes only."""
    return '|' in line and '-' in line and not line.strip(' \t|:-')
