# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Assistant settings: the API key and the options of the assistant settings dialog
(LLM_INTEG_DESIGN.md, section 4).

The key lives in this session only, unless the user asks to remember it: then in the OS
credential store when one works (probed, not assumed from `import keyring`), otherwise in the
settings file as plain text, which the dialog says. Without a key here the SDK uses
ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN or an `ant auth login` profile. The key is never a
QML property and never logged.
"""

import contextlib
import os
import sys
import threading
from pathlib import Path
from typing import Callable
from typing import Optional

from PySide6.QtCore import Property
from PySide6.QtCore import QObject
from PySide6.QtCore import QSettings
from PySide6.QtCore import Signal
from PySide6.QtCore import Slot

from .logic.claude_backend import DEFAULT_MODEL
from .logic.claude_backend import EFFORT_CHOICES
from .logic.claude_backend import MODEL_CHOICES
from .logic.claude_backend import describe_error
from .logic.claude_backend import make_client
from .logic.claude_backend import sdk_available

KEYRING_SERVICE = 'EasyQM'
KEYRING_USER = 'anthropic-api-key'
APPROVAL_MODES = (
    ('default', 'Ask before runs, replacing the structure and saving'),
    ('every', 'Ask before every change'),
    ('never', 'Never ask'),
)
_GROUP = 'assistant'


def cli_profile_file() -> Path:
    """The CLI profile the SDK would read, found as anthropic 1.17 finds it without importing it:
    `<config folder>/configs/<profile>.json`, the profile named by ANTHROPIC_PROFILE, the folder's
    `active_config` file or 'default'."""
    if os.environ.get('ANTHROPIC_CONFIG_DIR'):
        folder = Path(os.environ['ANTHROPIC_CONFIG_DIR'])
    elif sys.platform == 'win32':
        folder = Path(os.environ.get('APPDATA') or Path.home() / 'AppData' / 'Roaming') / 'Anthropic'
    else:
        folder = Path.home() / '.config' / 'anthropic'
    name = os.environ.get('ANTHROPIC_PROFILE', '')
    if not name:
        with contextlib.suppress(OSError):
            name = (folder / 'active_config').read_text(encoding='utf-8').strip()
    return folder / 'configs' / f'{name or "default"}.json'


class AssistantSettings(QObject):
    changed = Signal()
    verified = Signal(str)  # the result of `verify`, from a worker thread

    def __init__(self, settings: Optional[QSettings] = None, keyring=None, parent=None):
        super().__init__(parent)
        self._settings = settings if settings is not None else QSettings('EasyScience', 'EasyQM')
        self._keyring = keyring  # the keyring module, or a stand-in; imported on first use otherwise
        self._secure: Optional[bool] = None  # whether the credential store works, once probed
        self.client_factory: Callable = make_client
        self._key = self._stored_key()

    # Plain Python, for the assistant

    def client(self):
        """An Anthropic client for the current credential."""
        return self.client_factory(self._key)

    # Options

    @Property(str, notify=changed)
    def model(self) -> str:
        return self._value('model', DEFAULT_MODEL) or DEFAULT_MODEL

    @Slot(str)
    def setModel(self, value: str) -> None:
        self._set('model', value.strip() or DEFAULT_MODEL)

    @Property('QStringList', constant=True)
    def modelChoices(self) -> list:
        return list(MODEL_CHOICES)

    @Property(str, notify=changed)
    def effort(self) -> str:
        value = self._value('effort', 'medium')
        return value if value in EFFORT_CHOICES else 'medium'

    @Slot(str)
    def setEffort(self, value: str) -> None:
        if value in EFFORT_CHOICES:
            self._set('effort', value)

    @Property('QStringList', constant=True)
    def effortChoices(self) -> list:
        return list(EFFORT_CHOICES)

    @Property(str, notify=changed)
    def approvalMode(self) -> str:
        value = self._value('approval_mode', 'default')
        return value if value in dict(APPROVAL_MODES) else 'default'

    @Slot(str)
    def setApprovalMode(self, value: str) -> None:
        if value in dict(APPROVAL_MODES):
            self._set('approval_mode', value)

    @Property('QVariantList', constant=True)
    def approvalModeChoices(self) -> list:
        return [{'value': value, 'label': label} for value, label in APPROVAL_MODES]

    @Property(bool, notify=changed)
    def sendOutput(self) -> bool:
        return self._flag('send_output', True)

    @Slot(bool)
    def setSendOutput(self, value: bool) -> None:
        self._set('send_output', bool(value))

    @Property(bool, notify=changed)
    def sendResults(self) -> bool:
        return self._flag('send_results', True)

    @Slot(bool)
    def setSendResults(self, value: bool) -> None:
        self._set('send_results', bool(value))

    @Property(bool, notify=changed)
    def offline(self) -> bool:
        return self._flag('offline', False)

    @Slot(bool)
    def setOffline(self, value: bool) -> None:
        self._set('offline', bool(value))

    # Credential

    @Property(bool, notify=changed)
    def hasKey(self) -> bool:
        """Whether a key was entered here (this session or remembered)."""
        return bool(self._key)

    @Property(str, notify=changed)
    def keySource(self) -> str:
        """Where the credential a request would use comes from."""
        if self._key:
            return 'assistant settings'
        if os.environ.get('ANTHROPIC_API_KEY') or os.environ.get('ANTHROPIC_AUTH_TOKEN'):
            return 'environment variable'
        if cli_profile_file().is_file():
            return 'Anthropic CLI profile'
        return ''

    @Property(str, notify=changed)
    def keyStorage(self) -> str:
        """'session', 'keyring' or 'settings' for a key entered here; '' without one."""
        return (self._value('key_storage', '') or 'session') if self._key else ''

    @Property(bool, notify=changed)
    def secureStoreAvailable(self) -> bool:
        """Whether the credential store works; False until `checkSecureStore` or a remembered key
        tried it, so that starting the application writes nothing to it."""
        return bool(self._secure)

    @Slot()
    def checkSecureStore(self) -> None:
        """Try the credential store, once: when the settings dialog opens."""
        if self._secure is None:
            self._probe()
            self.changed.emit()

    @Property(bool, notify=changed)
    def sdkAvailable(self) -> bool:
        return sdk_available()

    @Property(bool, notify=changed)
    def configured(self) -> bool:
        """Whether a turn would go to the model: the SDK is installed, not offline, a credential resolves."""
        return sdk_available() and not self.offline and bool(self.keySource)

    @Slot(str, bool)
    def setKey(self, key: str, remember: bool) -> None:
        self._forget_stored()
        self._key = key.strip()
        if self._key and remember:
            if self._probe():
                self._keyring_module().set_password(KEYRING_SERVICE, KEYRING_USER, self._key)
                self._settings.setValue(f'{_GROUP}/key_storage', 'keyring')
            else:
                self._settings.setValue(f'{_GROUP}/api_key', self._key)
                self._settings.setValue(f'{_GROUP}/key_storage', 'settings')
        self.changed.emit()

    @Slot()
    def clearKey(self) -> None:
        self.setKey('', False)

    @Slot()
    def verify(self) -> None:
        """Check the credential and the model on a short-lived thread; the answer comes as `verified`."""
        if not sdk_available():
            self.verified.emit('The anthropic package is not installed: pip install EasyQM[llm].')
            return
        model, key, factory = self.model, self._key, self.client_factory

        def check() -> None:
            try:
                factory(key).models.retrieve(model)
                self.verified.emit(f'OK: {model} is available with this credential.')
            except Exception as error:
                self.verified.emit(describe_error(error))

        threading.Thread(target=check, daemon=True).start()

    # Storage

    def _value(self, name: str, default):
        return self._settings.value(f'{_GROUP}/{name}', default)

    def _flag(self, name: str, default: bool) -> bool:
        value = self._value(name, default)
        return value if isinstance(value, bool) else str(value).lower() in ('true', '1')

    def _set(self, name: str, value) -> None:
        self._settings.setValue(f'{_GROUP}/{name}', value)
        self.changed.emit()

    def _keyring_module(self):
        if self._keyring is None:
            try:
                import keyring
            except ImportError:
                return None
            self._keyring = keyring
        return self._keyring

    def _probe(self) -> bool:
        """Whether the credential store takes, gives back and deletes a value."""
        if self._secure is None:
            module, self._secure = self._keyring_module(), False
            if module is not None:
                try:
                    module.set_password(KEYRING_SERVICE, 'probe', 'ok')
                    self._secure = module.get_password(KEYRING_SERVICE, 'probe') == 'ok'
                    module.delete_password(KEYRING_SERVICE, 'probe')
                except Exception:
                    self._secure = False
        return self._secure

    def _stored_key(self) -> str:
        storage = self._value('key_storage', '')
        if storage == 'settings':
            return self._value('api_key', '') or ''
        if storage == 'keyring' and self._keyring_module() is not None:
            try:
                return self._keyring_module().get_password(KEYRING_SERVICE, KEYRING_USER) or ''
            except Exception:
                return ''
        return ''

    def _forget_stored(self) -> None:
        if self._value('key_storage', '') == 'keyring' and self._keyring_module() is not None:
            with contextlib.suppress(Exception):  # nothing stored there any more
                self._keyring_module().delete_password(KEYRING_SERVICE, KEYRING_USER)
        self._settings.remove(f'{_GROUP}/api_key')
        self._settings.remove(f'{_GROUP}/key_storage')
