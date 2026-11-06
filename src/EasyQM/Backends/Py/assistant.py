# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Assistant backend part: the chat behind the assistant panel (LLM_INTEG_DESIGN.md, sections 7–9).

The controller owns the conversation sent to the model (`_history`), the items the panel shows
(`messages`) and the approval card. A turn with the model runs on a worker thread
(`logic.claude_backend.Turn`); its tool calls come back here, to the main thread, where the
workspace checks them and runs them, after the user's approval when their effect needs one.
Every worker event carries the turn id, so events of a cancelled or cleared turn change nothing.
Without a configured model the offline stub answers. The first question of a session waits until
the user agrees to what is shared with the model.
"""

import json
import threading
from concurrent.futures import Future
from typing import Optional

from PySide6.QtCore import Property
from PySide6.QtCore import QCoreApplication
from PySide6.QtCore import QObject
from PySide6.QtCore import QTimer
from PySide6.QtCore import Signal
from PySide6.QtCore import Slot

from .assistant_settings import AssistantSettings
from .logic.assistant import StubAssistant
from .logic.claude_backend import USAGE_KEYS
from .logic.claude_backend import Turn
from .workspace import TOOLS
from .workspace import Action
from .workspace import Outcome
from .workspace import Workspace
from .workspace import data_text
from .workspace import facts_text

# How long the stub pretends to think.
STUB_DELAY_MS = 700
APPROVAL_TIMEOUT_MS = 5 * 60 * 1000
SESSION_TOKEN_LIMIT = 2_000_000  # input, cached, cache-written and output tokens together
SHUTDOWN_WAIT_S = 10
_CONFIRM = {'start': 'Run', 'replace': 'Replace', 'persist': 'Save', 'stop': 'Stop'}


class _Bridge(QObject):
    """Signals the worker thread emits; they are delivered on the main thread."""

    text = Signal(int, str)
    tool = Signal(int, object)  # (call id, tool name, input, Future)
    snapshot = Signal(int, object)  # (Future,) for the current snapshot text
    done = Signal(int, object)  # (generation, TurnResult)


class Assistant(QObject):
    messagesChanged = Signal()
    busyChanged = Signal()
    statusChanged = Signal()
    streamingTextChanged = Signal()
    approvalChanged = Signal()
    pageChanged = Signal()
    modelChanged = Signal()
    usageChanged = Signal()
    # Switch the visible page (the panel sets the app bar tab); the workspace's show_page tool.
    navigateRequested = Signal(str)
    # A turn ended: the panel scrolls to the end.
    replied = Signal()

    def __init__(self, workspace: Workspace, settings: Optional[AssistantSettings] = None,
                 delay_ms: int = STUB_DELAY_MS, parent=None):
        super().__init__(parent)
        self._workspace = workspace
        workspace.navigate = self.navigateRequested.emit
        self._settings = settings if settings is not None else AssistantSettings(parent=self)
        self._settings.changed.connect(self._settings_changed)
        self._stub = StubAssistant()
        self._items: list[dict] = []
        self._history: list = []  # the conversation the model sees, append-only
        self._streaming = ''
        self._status = ''
        self._generation = 0  # raised by clear and reset: results of older turns are dropped
        self._turn_id = 0
        self._turn: Optional[Turn] = None
        self._thread: Optional[threading.Thread] = None
        self._approval: Optional[dict] = None
        self._declined: set = set()  # (tool, input) the user declined in this turn
        self._usage = dict.fromkeys(USAGE_KEYS, 0)
        self._answering_model = ''
        self._disclosed = False
        self._question = ''

        self._stub_timer = QTimer(self, singleShot=True, interval=delay_ms)
        self._stub_timer.timeout.connect(self._stub_answer)
        self._approval_timer = QTimer(self, singleShot=True, interval=APPROVAL_TIMEOUT_MS)
        self._approval_timer.timeout.connect(lambda: self._decline('it timed out'))
        self._bridge = _Bridge(self)
        self._bridge.text.connect(self._on_text)
        self._bridge.tool.connect(self._on_tool)
        self._bridge.snapshot.connect(self._on_snapshot)
        self._bridge.done.connect(self._on_done)
        application = QCoreApplication.instance()
        if application is not None:
            application.aboutToQuit.connect(self.shutdown)
        self._settings_changed()

    # State for the panel

    @Property('QVariant', constant=True)
    def settings(self) -> AssistantSettings:
        return self._settings

    @Property(str, notify=modelChanged)
    def modelName(self) -> str:
        if not self._settings.configured:
            return self._stub.name
        model = self._settings.model
        answering = self._answering_model
        return f'{model} · answered by {answering}' if answering and answering != model else model

    @Property(bool, notify=modelChanged)
    def configured(self) -> bool:
        return self._settings.configured

    @Property('QVariantList', notify=messagesChanged)
    def messages(self) -> list:
        """[{id, role, text, ok, page}]; role is user, assistant, action, notice or error."""
        return list(self._items)

    @Property(int, notify=messagesChanged)
    def messageCount(self) -> int:
        return len(self._items)

    @Property(bool, notify=busyChanged)
    def busy(self) -> bool:
        return self._stub_timer.isActive() or self._turn is not None

    @Property(str, notify=statusChanged)
    def status(self) -> str:
        """What a busy assistant is doing: 'Thinking', 'Waiting for your confirmation', 'Cancelling'."""
        return self._status

    @Property(str, notify=streamingTextChanged)
    def streamingText(self) -> str:
        return self._streaming

    @Property('QVariantMap', notify=approvalChanged)
    def approval(self) -> dict:
        """{id, title, detail, confirm} of what waits for the user: an action, or sharing the
        first question; {} when nothing waits."""
        if self._approval is None:
            return {}
        return {'id': self._approval['id'], **self._approval['card']}

    @Property(str, notify=usageChanged)
    def usageText(self) -> str:
        u = self._usage
        return (f'{u["input_tokens"]} input, {u["cache_read_input_tokens"]} cached, '
                f'{u["cache_creation_input_tokens"]} written to cache and {u["output_tokens"]} output tokens this session')

    # Which page the user looks at: part of the snapshot, and picks the suggestions.
    @Property(str, notify=pageChanged)
    def page(self) -> str:
        return self._workspace.page

    @Slot(str)
    def setPage(self, name: str) -> None:
        if name != self._workspace.page:
            self._workspace.page = name
            self.pageChanged.emit()

    @Property('QStringList', notify=pageChanged)
    def suggestions(self) -> list:
        return self._stub.suggestions(self._workspace.brief())

    def refresh(self) -> None:
        """The workspace changed: the suggestions may be different now."""
        self.pageChanged.emit()

    # Commands from the panel

    @Slot(str)
    def send(self, text: str) -> None:
        question = text.strip()
        if not question or self.busy or self._approval is not None:
            return
        self._declined.clear()
        self._add('user', question)
        if not self._settings.configured:
            self._question = question
            self._stub_timer.start()
            self._set_status('Thinking')
            self.busyChanged.emit()
            return
        if sum(self._usage.values()) >= SESSION_TOKEN_LIMIT:
            self._add('notice', 'This session reached its token limit. Restart EasyQM to continue with the model.')
            return
        if not self._disclosed:
            # Nothing leaves the machine before the user agreed to what is shared.
            self._approval = {'id': 'disclosure', 'question': question,
                              'card': {'title': f'Share this with Anthropic ({self._settings.model})?',
                                       'detail': [self._disclosure()], 'confirm': 'Send'}}
            self.approvalChanged.emit()
            return
        self._start_turn(question)

    def _start_turn(self, question: str) -> None:
        try:
            client = self._settings.client()
        except Exception as error:
            self._add('error', f'The assistant could not start: {error}')
            return
        facts, data = self._workspace.snapshot()
        self._turn_id += 1
        turn_id, generation = self._turn_id, self._generation
        turn = Turn(client, self._settings.model, self._settings.effort, TOOLS, self._history,
                    [{'type': 'text', 'text': question}, {'type': 'text', 'text': data_text(data)}], facts_text(facts),
                    dispatch=lambda call_id, name, args: self._dispatch(turn, turn_id, call_id, name, args),
                    on_text=lambda text: self._bridge.text.emit(turn_id, text),
                    refresh=lambda: self._ask(turn, self._bridge.snapshot, turn_id, ()))
        self._turn = turn
        self._thread = threading.Thread(target=lambda: self._bridge.done.emit(turn_id, (generation, turn.run())),
                                        name='assistant-turn', daemon=True)
        self._set_status('Thinking')
        self.busyChanged.emit()
        self._thread.start()

    @Slot()
    def cancel(self) -> None:
        """Stop the answer being written; the conversation stays. A running engine job is not stopped."""
        if self._stub_timer.isActive():
            self._stub_timer.stop()
            self._add('notice', 'Cancelled.')
            self._set_status('')
            self.busyChanged.emit()
        elif self._turn is not None and not self._turn.cancelled.is_set():
            self._turn.cancel()
            if self._approval is not None:
                self._resolve_approval(Outcome('cancelled', 'Cancelled by the user.'))
            self._set_status('Cancelling')

    @Slot(str, bool)
    def answerApproval(self, approval_id: str, allowed: bool) -> None:
        if self._approval is None or self._approval['id'] != approval_id:
            return  # an answer to a card that is gone
        if 'question' in self._approval:
            question = self._take_approval()['question']
            if allowed:
                self._disclosed = True
                self._add('notice', self._disclosure())
                self._start_turn(question)
            else:
                self._add('notice', 'Nothing was sent.')
        elif allowed:
            approval = self._take_approval()
            self._execute(approval['action'], approval['future'])
        else:
            self._decline('the user declined')

    @Slot()
    def clear(self) -> None:
        """Forget the conversation; a turn in progress is cancelled and its answer dropped."""
        self.cancel()
        self._take_approval()  # a first question still waiting to be shared
        self._generation += 1
        self._items, self._history = [], []
        self._streaming = ''
        self.messagesChanged.emit()
        self.streamingTextChanged.emit()

    def reset(self) -> None:
        """For PyBackend.reset, before the parts reset: the conversation goes with the workspace."""
        self.clear()

    def shutdown(self) -> None:
        """At quit: cancel a turn and give its thread a bounded time to end."""
        self.cancel()
        if self._thread is not None:
            self._thread.join(SHUTDOWN_WAIT_S)

    # Worker thread

    def _dispatch(self, turn: Turn, turn_id: int, call_id: str, name: str, args: dict) -> tuple[str, str, bool]:
        """A tool call, run on the main thread; waits for it, or for the turn's cancellation."""
        outcome = self._ask(turn, self._bridge.tool, turn_id, (call_id, name, args))
        outcome = outcome or Outcome('cancelled', 'Cancelled by the user.')
        return outcome.status, outcome.text, outcome.is_error

    @staticmethod
    def _ask(turn: Turn, signal, turn_id: int, call: tuple):
        """What the main thread answers to `signal` with this call and a Future; None when the
        turn is cancelled first."""
        future = Future()
        signal.emit(turn_id, (*call, future))
        while not future.done() and not turn.cancelled.wait(0.05):
            pass
        return future.result() if future.done() else None

    # Main thread: worker events

    def _alive(self, turn_id: int) -> bool:
        return self._turn is not None and turn_id == self._turn_id and not self._turn.cancelled.is_set()

    def _on_text(self, turn_id: int, text: str) -> None:
        if self._alive(turn_id):
            self._streaming += text
            self.streamingTextChanged.emit()

    def _on_snapshot(self, turn_id: int, call: tuple) -> None:
        (future,) = call
        try:
            future.set_result(facts_text(self._workspace.snapshot()[0]) if self._alive(turn_id) else None)
        except Exception as error:  # the turn then ends with this error
            future.set_exception(error)

    def _on_tool(self, turn_id: int, call: tuple) -> None:
        future = call[-1]
        try:
            self._handle_tool(turn_id, *call)
        except Exception as error:  # the worker waits for an answer: no error may leave it waiting
            if not future.done():
                future.set_result(Outcome('failed', f'{call[1]} failed: {error}'))

    def _handle_tool(self, turn_id: int, call_id: str, name: str, args: dict, future: Future) -> None:
        if not self._alive(turn_id):
            future.set_result(Outcome('cancelled', 'Cancelled by the user.'))
            return
        self._flush_streaming()
        key = (name, json.dumps(args, sort_keys=True))
        if key in self._declined:
            future.set_result(Outcome('declined', 'The user already declined this; it was not done.'))
            return
        prepared = self._workspace.prepare(name, args)
        if isinstance(prepared, Outcome):
            if prepared.is_error:
                self._add('action', prepared.text, ok=False)
            future.set_result(prepared)
        elif self._workspace.approval_needed(prepared, self._settings.approvalMode):
            card = {'title': prepared.title, 'detail': prepared.detail, 'confirm': _CONFIRM.get(prepared.effect, 'Allow')}
            self._approval = {'id': f'{turn_id}:{call_id}', 'action': prepared, 'future': future, 'key': key,
                              'card': card}
            self._approval_timer.start()
            self._set_status('Waiting for your confirmation')
            self.approvalChanged.emit()
        else:
            self._execute(prepared, future)

    def _execute(self, action: Action, future: Future) -> None:
        changed = self._workspace.changed_since(action)
        if changed:
            outcome = Outcome('stale_state', f'The {", ".join(changed)} changed while this waited, so nothing was done. '
                                             'Read the workspace again.')
        else:
            try:
                outcome = action.run()
            except Exception as error:
                outcome = Outcome('failed', f'{action.title} failed: {error}')
        self._add('action', outcome.text, ok=not outcome.is_error, page=action.page)
        future.set_result(outcome)

    def _decline(self, why: str) -> None:
        approval = self._take_approval()
        if approval is not None:
            self._declined.add(approval['key'])
            title = approval['action'].title
            self._add('action', f'Not done: {title} ({why}).', ok=False)
            approval['future'].set_result(Outcome('declined', f'Not done: {why} ({title}). Do not ask for it again; '
                                                              'ask the user what they want instead.'))

    def _take_approval(self) -> Optional[dict]:
        approval, self._approval = self._approval, None
        self._approval_timer.stop()
        if approval is not None:
            self._set_status('Thinking' if self._turn is not None else '')
            self.approvalChanged.emit()
        return approval

    def _resolve_approval(self, outcome: Outcome) -> None:
        approval = self._take_approval()
        if approval is not None:
            approval['future'].set_result(outcome)

    def _on_done(self, turn_id: int, payload: tuple) -> None:
        generation, result = payload
        for key in USAGE_KEYS:
            self._usage[key] += result.usage[key]
        self.usageChanged.emit()
        if result.model and result.model != self._answering_model:
            self._answering_model = result.model
            self.modelChanged.emit()
        if generation == self._generation:
            self._history += result.messages
            if result.refused:
                self._streaming = ''  # text written before a refusal is dropped
            self._flush_streaming()
            if result.error:
                self._add('error', result.error)
            elif result.note:
                self._add('notice', result.note)
        else:
            self._streaming = ''
            self.streamingTextChanged.emit()
        if turn_id == self._turn_id:
            self._turn, self._thread = None, None
            self._set_status('')
            self.busyChanged.emit()
            self.replied.emit()

    # Stub

    def _stub_answer(self) -> None:
        facts, data = self._workspace.snapshot()
        self._add('assistant', self._stub.reply(self._question, facts, data))
        self._set_status('')
        self.busyChanged.emit()
        self.replied.emit()

    # Helpers

    def _add(self, role: str, text: str, ok: bool = True, page: str = '') -> None:
        self._items.append({'id': len(self._items), 'role': role, 'text': text, 'ok': ok, 'page': page})
        self.messagesChanged.emit()

    def _flush_streaming(self) -> None:
        text, self._streaming = self._streaming.strip(), ''
        if text:
            self._add('assistant', text)
        self.streamingTextChanged.emit()

    def _set_status(self, status: str) -> None:
        if status != self._status:
            self._status = status
            self.statusChanged.emit()

    def _settings_changed(self) -> None:
        self._workspace.send_output = self._settings.sendOutput
        self._workspace.send_results = self._settings.sendResults
        self.modelChanged.emit()

    def _disclosure(self) -> str:
        sent = ['the structure (coordinates, elements, labels)', 'the calculation and method settings', 'this conversation']
        if self._settings.sendOutput:
            sent.append('engine output and messages')
        if self._settings.sendResults:
            sent.append('results')
        return (f'The assistant sends {", ".join(sent[:-1])} and {sent[-1]} to Anthropic ({self._settings.model}). '
                'Choose what is shared in the assistant settings; turning sharing off later does not recall what was sent.')
