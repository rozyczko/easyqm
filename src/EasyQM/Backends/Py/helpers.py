# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Small helpers shared by the backend proxies."""

from typing import Iterable

from PySide6.QtCore import QUrl


def choices(pairs: Iterable[tuple[str, str]]) -> list[dict]:
    """(value, label) pairs as the list of dicts a QML ComboBox takes as its model."""
    return [{'value': value, 'label': label} for value, label in pairs]


def apply(target, attribute: str, value, *signals) -> bool:
    """Set `target.attribute` and emit the signals, only if the value differs. Returns whether it did."""
    if getattr(target, attribute) == value:
        return False
    setattr(target, attribute, value)
    for signal in signals:
        signal.emit()
    return True


def to_local_path(path: str) -> str:
    """A QML file dialog hands over a file:// URL; a plain path is passed through."""
    url = QUrl(path)
    return url.toLocalFile() if url.isLocalFile() else path
