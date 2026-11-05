# Review of the EasyQM LLM integration design

Reviewed: 2026-11-04  
Target: `LLM_INTEG_DESIGN.md`  
Basis: the current working tree, including the uncommitted assistant mock-up, and current primary Anthropic, Qt and keyring documentation.

## Overall assessment

The proposed split between a network worker, a main-thread controller, a workspace snapshot and dedicated tools is a useful starting point. Reusing backend operations, keeping executable-path changes outside the tool surface, validating against engine capabilities and making actions visible are sound choices.

The design is **not ready to implement as written**. Its main weaknesses are the contracts between these components: approval is not tied to the state being approved; cancellation does not prevent stale tool execution; the transcript has ambiguous ownership; privacy settings do not cover all outgoing data; and several tools do not match the semantics of the existing backend. These problems can produce incorrect scientific settings, unintended changes, repeated runs, misleading success reports and unintended disclosure of workspace data.

This is a design review, not a claim that a finished LLM implementation already has these bugs. Findings marked **confirmed mismatch** are established by the proposal and current source. Findings marked **design gap** describe behavior the proposal does not specify sufficiently to implement safely.

Priority meanings:

- **P1:** resolve before enabling model-driven mutations or releasing network chat where the issue concerns data disclosure.
- **P2:** resolve before a usable first release; otherwise functionality, reliability or cost reporting is materially misleading.
- **P3:** improve maintainability and usability; these need not block an internal prototype.

No application code was changed. This review used source inspection and documentation verification; it did not execute a live Anthropic request, launch a calculation, or run the test suite.

## Findings at a glance

| ID | Priority | Finding |
|---|---|---|
| R01 | P1 | Workspace text is elevated to system authority, while file access is broader than the stated boundary |
| R02 | P1 | The engine-output privacy switch can be bypassed through tools and existing history |
| R03 | P1 | Approval is not bound to an immutable action or workspace revision |
| R04 | P1 | Cancellation and shutdown can leave waits, queued mutations and late events alive |
| R05 | P1 | Transcript ownership and recovery after executed tools are underspecified |
| R06 | P1 | Reusing `setAtomFixed` can change atoms outside the tool's requested indices |
| R07 | P1 | The proposed disk-write gates miss automatic saves and scratch runs |
| R08 | P1 | Charge, multiplicity and method updates need cross-field scientific validation |
| R09 | P1 | Results are not identified with the sample and method that produced them |
| R10 | P2 | Main-thread execution does not make file loads, snapshots and job stops nonblocking |
| R11 | P2 | Tool success cannot be inferred from existing setters returning normally |
| R12 | P2 | The method tool and snapshot disagree with actual capabilities and values |
| R13 | P2 | `save_project` does not save the workspace the assistant edits |
| R14 | P2 | API settings need a supported SDK/model capability contract |
| R15 | P2 | Caching, token accounting and history trimming do not implement the promised behavior |
| R16 | P2 | Size limits do not bound tokens, memory or regex execution |
| R17 | P2 | Keyring availability and authentication source reporting are incomplete |
| R18 | P2 | The implementation order and tests defer essential correctness controls |
| R19 | P3 | UI models, navigation and persisted conversations need explicit contracts |

## R01 — Untrusted workspace content receives system authority

**Priority:** P1. **Type:** design gap with an explicit trust-boundary error.  
**Design:** §§4 and 9, particularly lines 149–153 and 409–414.

The snapshot mixes application-generated facts with externally supplied strings: project names, file-derived atom labels, engine output and error text. The proposal assigns the entire document operator authority by placing it in a system message. Being observed application state does not make a string an instruction from the application. JSON serialization and an XML-like wrapper do not establish that distinction.

For example, an engine output line can tell the assistant to load another structure, change settings, or retrieve more output. Default approval permits many mutations without a card. An action row records a change after it happens; it is not a security boundary.

There is also a mismatch between the filesystem non-goal and `load_structure(name_or_path)`: arbitrary absolute and home-relative paths are allowed without any requirement that the human selected that path. A path supplied by a model is not evidence of user authorization. Read-only access can still disclose private structures. The current loader reads the whole file before parsing, and parse failures can include source text: see `logic/sample.py:188` and `read_xyz`, including the invalid-element and invalid-coordinate messages. Thus even a failed load can reveal fragments through `loadError` and a tool result.

**Recommended correction:** keep trusted behavioral instructions in the system prompt and pass external content as explicitly untrusted data in user content or tool results. Keep permissions in application code. Limit automatic structure access to packaged examples and an explicitly authorized project root. Use a picker or a human-selected file handle for other paths. Resolve canonical paths, check containment after resolving links/junctions, reject traversal and unsupported special/network paths according to an explicit policy, enforce file-size/type limits, and redact parse errors before transmission. If arbitrary paths remain a feature, document the wider access boundary and approve that access separately from discard approval.

**Acceptance test:** an output line requesting a different local file cannot expand allowed roots or authorize a read; malformed input cannot leak arbitrary source lines to the API.

## R02 — The privacy switch has multiple bypasses

**Priority:** P1. **Type:** design gap.  
**Design:** §3 line 116, §4 snapshot, §5 read tools, §9 lines 406–407.

The checkbox promises control over output and results, but its storage key is absent from the settings list. The design only describes omitting them from the initial snapshot. It does not specify filtering `get_job_output`, `get_workspace`, action errors, saved conversations or earlier messages being resent. Turning the checkbox off after a diagnostic conversation would otherwise keep transmitting the output already stored in history. Removing just the original output blocks can also leave assistant summaries quoting that output.

The statement that the model receives only snapshots and tool results omits the user's question, conversation history and any persisted transcript. The first request also sends molecular coordinates by default; an engine-output checkbox does not communicate that broader data transfer.

**Recommended correction:** define one outbound-data policy used by initial snapshots, every read tool, tool errors and transcript serialization. Persist the preference. When output sharing is disabled, refuse output tools locally even if the model requests them. Define what happens to previous sensitive turns: starting a fresh sanitized conversation is simpler than claiming selective redaction is complete. Explain that disabling future transmission cannot retract data already sent. Disclose the categories sent before the first network turn and provide a genuine offline mode even when credentials are discoverable.

**Acceptance test:** capture complete fake-client request bodies before and after disabling the option; assert that no output, results, or prior quotations of those fields are resent. Test every tool path, not only the snapshot builder.

## R03 — Approval does not identify exactly what will execute

**Priority:** P1. **Type:** design gap.  
**Design:** §§5.3–5.4 and 7.

The panel is non-modal and the workspace remains editable. A run card can show benzene with B3LYP/cc-pVDZ, then the user can change the sample, calculations, engine path or project folder before pressing Run. `Job.run()` reads live backend objects at execution time (`job.py:158`), so the approved card can describe a different computation from the one started.

The same race affects atom indices, sample replacement and `save_project`. A queued request can also refer to a project that has since been replaced. Disabling the chat input does not address these races.

A denial returned with `is_error: false` does not force a model to stop. It can request the same operation again or execute another mutating call already present in the same batch. The proposal leaves this to model behavior.

**Recommended correction:** create an action record containing conversation/turn/tool-call IDs, normalized arguments, project identity, relevant workspace revisions and the exact effects displayed in the card. On approval, recheck those revisions and preconditions on the main thread immediately before execution. Either execute a prepared immutable run configuration or reject and rebuild the card when it has changed. Expired, duplicate and late approvals must be harmless. A denial or timeout should be a structured `declined` result, with a controller policy that prevents the denied action from being automatically requested again in the same turn and defines what happens to remaining mutations in the batch.

Use separate revisions for relevant configuration and live output if necessary; an appended output line should not invalidate an unrelated method approval.

**Acceptance test:** change sample, basis, job state and project independently while a card waits. The approved action must never silently execute against changed state.

## R04 — Cancellation is insufficient to prevent stale work or shutdown deadlocks

**Priority:** P1. **Type:** design gap.  
**Design:** §2 lines 69–73; §5 approval waits; §7 lines 376–379.

Checking a flag between stream events does nothing while the worker is blocked waiting for network data, SDK retry backoff, a GUI dispatch or approval. A queued mutation may already be waiting on the main thread when Clear is pressed. Discarding the answer does not retract that request or reverse an operation already executed.

There are two shutdown hazards: the main thread waiting for a worker that itself waits for the main thread, and destroying a running worker after the GUI event loop has stopped servicing its requests. `BlockingQueuedConnection` and a wait condition have different lifecycle implications and should not be presented as interchangeable implementation details. Qt documents that queued delivery depends on the receiving event loop and that blocking connections block the caller. [Qt threading documentation](https://doc.qt.io/qt-6/threads-qobject.html).

`PyBackend.reset()` currently resets the workspace parts before calling `assistant.reset()` (`py_backend.py:114`). With queued tools, invalidating the turn should happen before replacing those parts. Project create/load also emits `externalProjectChanged`, but `_connect_parts()` does not use it to establish an assistant-session boundary.

**Recommended correction:** specify one controller state machine, for example `idle → streaming → awaiting_approval/executing → completed/failed/cancelled`. Every event and command carries a generation/turn ID. Check cancellation again on the main thread immediately before any mutation; ignore stale deltas, results and approvals. Cancellation must wake all approval/dispatch waiters, abort or close network activity through the selected transport's supported mechanism, and release runner/client resources in `finally`. Keep the GUI event loop running until worker cleanup is acknowledged. Choose and document a bounded shutdown policy rather than relying on a generic stop call.

Distinguish cancelling assistant generation from stopping an engine job. Clearing chat must not imply that a job already launched has stopped.

**Acceptance test:** cancel during an approval, a stalled stream, retry delay and queued tool dispatch; clear then immediately start a new turn; close the app in each state. No stale mutation, late bubble, deadlock or live-worker destruction is acceptable.

## R05 — The transcript can omit inputs, lose executed actions or become invalid

**Priority:** P1. **Type:** confirmed pseudocode omission and design gap.  
**Design:** §4 history rules; §6 lines 288–343; §7 `send`.

`run_turn(history, question, snapshot, ...)` constructs `history + [question, snapshot]`, then appends only assistant messages and tool results to the original history. That does not retain the new question or snapshot. Separately, §7 says `Assistant.send()` appends the user message already. If both refer to the same history, the question is duplicated in the request; if they refer to separate UI/API histories, the API history loses the input. The document needs to choose explicitly.

The failure rule is more serious: dropping the partial assistant turn after a network failure can erase the record of tools that have already changed the workspace or started a job. A subsequent retry may repeat a run after the first has finished. The stub can then answer a generic overview without acknowledging completed actions.

UI rows with `role: action` also cannot simply be appended to the provider transcript. UI presentation, provider content blocks and local action receipts need different representations. Ownership matters for threading too: the main controller is said to own history, while the worker mutates it.

**Recommended correction:** give the protocol transcript one owner and define the turn boundary. Build a copied request from previously committed protocol messages; append the current user/context exactly once; commit completed assistant/tool exchanges through explicit events. Retain successful action receipts even if the next model request fails. An incomplete tool block must not execute. Recovery must preserve or repair complete tool-use/result groups before another request, while retaining a local audit of actual side effects. Deduplicate execution by tool-call ID and distinguish replay of a completed action from a fresh action requiring authorization.

Do not report a canned fallback as though the requested workflow completed. Report the failure, what definitely executed, what did not, and the current job identifier.

**SDK nuance:** calling `generate_tool_call_response()` explicitly is not by itself a double-execution bug: the current runner caches that result. Its history-mutating helpers can invalidate that cache, so any custom history integration must be tested against the chosen SDK version. [Anthropic runner source](https://raw.githubusercontent.com/anthropics/anthropic-sdk-python/main/src/anthropic/lib/tools/_beta_runner.py).

**Acceptance test:** a two-turn transcript contains each input and snapshot exactly once. Inject a stream failure after a successful setter, after `run_workflow`, and after the first of several tool calls; retry without losing receipts or duplicating effects.

## R06 — `set_atom_fixed` does not match `Sample.setAtomFixed`

**Priority:** P1. **Type:** confirmed mismatch.  
**Design:** §5 tool table, line 240.  
**Source:** `src/EasyQM/Backends/Py/sample.py:489`; selection behavior is also covered in `tests/test_py_parts.py` around lines 135–147.

The tool accepts explicit indices, but the existing setter intentionally expands a change to every selected atom if the supplied index belongs to the current selection. If atoms 0 and 1 are selected and the assistant calls `set_atom_fixed(indices=[0], fixed=True)`, naively looping over the setter fixes both atoms. The result could claim only atom 0 changed. Fixed-atom constraints alter the calculation, so this is a scientific correctness issue.

**Recommended correction:** add a backend command with exact-index semantics, independent of GUI selection, and reuse it from both the GUI selection-aware wrapper and assistant tools. Validate all indices before applying any change; use zero-based base-atom IDs explicitly, deduplicate indices, bind them to the sample revision, and return the actual affected IDs. Do not silently clear the user's selection as a workaround.

**Acceptance test:** tool calls affect exactly the requested atoms regardless of selection; invalid or stale indices change nothing.

## R07 — Disk effects bypass the proposed gate

**Priority:** P1. **Type:** confirmed mismatch.  
**Design:** §1 safety goal, §5 gates, §9 line 411.  
**Source:** `project.py:46`, `project.py:228`, `py_backend.py:183`, `py_backend.py:187`, `job.py:31`, `job.py:167`.

Project autosave is enabled by default. Loading a different sample, changing calculation selection or switching the effective engine triggers project relays that call project setters; those setters can save `project.json` immediately. Therefore gating only `save_project` does not meet the promise to ask before disk writes. Replacing a selection one type at a time can also persist intermediate states.

The claim that no tool writes outside the project folder is false for `run_workflow`: without a created project, runs go to `tempfile.gettempdir()/EasyQM/runs/...`. The example is allowed to start from a workspace with no project, but its card and trace show only `runs/001`.

**Recommended correction:** define gates in terms of effects, including automatic persistence, rather than tool names alone. Decide whether autosave following an approved workspace change is included in that approval, and state this clearly. Batch related updates so observers and autosave see a consistent result. Include the actual project or scratch destination in run approval. Either allow scratch execution explicitly or require a created project; do not claim both unrestricted scratch runs and project-only writes.

The three approval modes also need a complete matrix covering reads, navigation, ordinary changes, disk effects, replacement, start and stop. The default mode label currently omits disk writes although the goals include them.

**Acceptance test:** instrument saves during every mutating tool with autosave both on and off. Verify the displayed/authorized effects include every resulting write.

## R08 — Independent enum/range validation is not enough for scientific state

**Priority:** P1. **Type:** design gap.  
**Design:** §§5 and 9; `set_electronic_state`, `set_calculation_options`, `set_method`.

Charge and multiplicity are correctly identified as prerequisites requiring new backend/UI work. However, adding two unrestricted setters would permit inconsistent electronic states. The existing sample logic already considers electron-count parity when atoms change (`logic/sample.py:183`, `logic/sample.py:291`), while ORCA input writes charge, multiplicity and reference directly. Quantum ESPRESSO uses multiplicity to set magnetization only with `UKS` (`logic/engines/quantum_espresso.py`, `input_text`). A multiplicity change with an incompatible reference can therefore be rejected by an engine or have an unexpected effect.

For the ordinary integer-electron states supported here, validate charge and multiplicity together against electron count, allowed spin population and parity; also validate the method/reference and engine's supported interpretation. Do not silently select a scientifically different state to make a request pass.

Other cross-field examples include setting both k-point spacing and a grid (the spacing setter clears the explicit grid), molecular cell optimization, a functional while the method family is HF, or a frequency option not implemented by the chosen engine. QE explicitly rejects Raman in this adapter, while several other shared options are not consumed there. Membership in a global choices list does not prove that an option is effective for this run.

The design also conflicts with itself: validation is promised before setters run, but `set_method` is described as returning both applied and rejected fields. Partial application can leave an unintended configuration, with signals and autosave already emitted.

**Recommended correction:** validate a proposed complete state before committing a multi-field command. Default to all-or-nothing updates and return normalized values, units and the actual effective change. Define omitted versus null fields, reject unknown nested fields, non-finite numbers and out-of-range values, and explicitly handle mutually exclusive settings. Share domain validation with GUI/backend commands where possible, rather than maintaining assistant-only rules.

**Acceptance test:** invalid charge/spin/reference combinations and mixed valid/invalid method patches produce no change. Reject or clearly report engine-ignored options. Test spacing/grid conflicts deterministically.

## R09 — Results can be attributed to the wrong workspace

**Priority:** P1. **Type:** confirmed missing provenance in the proposed snapshot.  
**Design:** §4 `job`/`results`, §12 final question.  
**Source:** `py_backend.py:204`, `job.py:47` onward, `results.py`.

The user can change the sample or method after a run while results from the previous run remain displayed. The next snapshot then combines current sample/method with old output and results. There is no run ID, input revision, structure fingerprint, effective method, or explicit stale-results indicator. The assistant can answer that the current molecule converged when the available results actually belong to another setup.

The backend already retains the job adapter separately from the active adapter, which illustrates why these identities must not be merged. It also guards applying optimized geometry by checking the initial positions (`sample.py:318`); this existing protection should be preserved, not replaced with an unconditional update.

**Recommended correction:** attach immutable run provenance to output and parsed results: run ID, source configuration/revision, engine/version, sample fingerprint, calculation order and effective settings. Include whether results correspond to the current configuration and whether optimized geometry was applied. Distinguish execution success, SCF convergence, optimization convergence, partial results and available frequency data. A normal process termination or `results.available` is not by itself proof of the requested scientific outcome.

**Acceptance test:** run A, modify the workspace to B, and ask whether “it” converged. The response must identify A's result and the mismatch instead of asserting a result for B.

## R10 — Main-thread operations can still freeze the GUI

**Priority:** P2. **Type:** confirmed incorrect architectural claim.  
**Design:** §2 lines 69–73; §4 snapshot construction.

The worker waiting does not make work performed by the main thread cheap. Existing operations include whole-file reads and structure parsing (`logic/sample.py:196`), lazy symmetry calculation in `Sample.pointGroup`, scene rebuilding, project disk writes, engine input generation and process startup. `Job.stop()` calls `JobRunner.stop()`, which waits for process termination (`logic/runner.py:111`). These can block the event loop.

Even a read-only snapshot is not necessarily a pure or bounded operation: property getters can compute and cache derived data, and `job.output` joins every accumulated output chunk before a tail is sliced.

**Recommended correction:** keep Qt-object reads and mutations on the main thread, but separate expensive preparation from commit. Copy immutable data, parse/load or compute outside the GUI thread, then validate revision and commit on the main thread. For long-lived process operations, use an asynchronous lifecycle with bounded termination. Prefer cached summaries and a bounded output buffer/index for snapshots. State a responsiveness budget and measure representative large structures and output.

Qt object affinity is still a valid reason for main-thread commits; moving arbitrary live `Sample` or `Job` calls into the network thread would introduce a different bug.

## R11 — Tool results need explicit backend outcomes

**Priority:** P2. **Type:** confirmed mismatch.  
**Design:** §5 return-value rules and `run_workflow`, `save_project`, `load_structure`.

`Job.run()`, `Project.save()` and `Sample.loadStructure()` return `None`, including failure cases. They report failure through state or signals. `Job.run()` is also a no-op when already running. Checking `method.canRun`, engine detection and selected-count does not cover missing QE pseudopotentials, cutoff files, phonon executables or invalid combinations caught during input generation.

The design names `loadError` but does not define scoped capture or a result object. `save_project` has no corresponding success/error capture contract. An implementation that treats normal return as success can say a file was saved or a workflow started when it did not.

**Recommended correction:** add command-level outcomes such as `ok`, `changed`, `declined`, `failed`, `already_running` and `stale_state`, with safe diagnostics, actual resulting values and operation IDs. Existing QML slots can wrap those commands. Preflight input generation and required resources before asking to run where practical; revalidate at commit. A run-start success must include the new run ID/folder and actual running state, not just the old folder property.

For the SDK, distinguish tool-result transport metadata from the result payload. Returning the text `is_error: true` or a JSON field with that name is not equivalent to setting the outer tool-result flag. Define and test the adapter from domain outcomes to the chosen runner's error mechanism.

**Acceptance test:** disk permission failure, load parse error, missing pseudo data and an already-running job all produce truthful results and action rows. A failed start cannot return a previous run as newly launched.

## R12 — Several snapshot/tool values do not describe the actual application

**Priority:** P2. **Type:** confirmed mismatches and incomplete mapping.  
**Design:** §4 JSON example, §5 tool table, §12 worked trace.

| Proposal | Current code / consequence | Correction |
|---|---|---|
| `family: "dft"` | Values are `DFT` and `HF` in engine capabilities | Use machine values exactly; keep display labels separately |
| No `family` input in `set_method` | `Method.setFamily` and GUI family selection exist | Add `family`; otherwise “use Hartree–Fock” cannot be implemented |
| `optimise: "all"` | Allowed targets are `positions` and `positions_and_cell` | Use the real enum and validate sample/engine applicability |
| `auxiliary_basis: "auto"`, `reference: "auto"`, grid `"default"` | These are not current ORCA choices | Replace with actual values or mark examples as deliberately non-contractual |
| `cores` accepts 1–256 | Run settings say serial-only; ORCA input has no parallel directive and QE commands do not launch MPI | Expose only the effective supported value, or implement parallel execution first |
| Every combo has choices | Example omits family, dispersion, auxiliary, reference, solvation, SCF, grid, optimization-target and frequency-type lists | Define a complete field registry instead of hand-maintained partial JSON |
| `results.optimisation` from public properties | `Results` exposes rows/tiles/modes, not that proposed object directly | Add a documented summary accessor or map existing fields explicitly |
| Bundled `examples/XYZ` and `examples/CIF` | These are repository folders; the wheel packages `src/EasyQM`, and startup benzene comes from `Resources/structures` | Package supported examples explicitly and resolve package resources |

The demonstration also differs from current defaults: auxiliary basis is `def2/J`, reference `RKS`, SCF convergence `tight`, grid `DefGrid2`, run memory 16 GB and cores 1 (`logic/method.py`). Different values are legal as an illustrative state, but they should not be presented as the default trace without initialization steps.

The snapshot should declare units and coordinate frame. For crystals, selected atoms can include periodic images (`sample.py:62`), while a list of base indices alone loses which drawn copy was selected. A selection summary helps, but does not provide an exact model for follow-up actions. Include base-atom ID plus image vector where relevant and distinguish fractional from Cartesian coordinates.

The broad “everything the GUI shows” goal also exceeds the listed snapshot: display settings, detailed results and some project information are absent. Replace it with an explicit supported context inventory, including truncation and unavailable-field behavior.

## R13 — Saving the project does not save the edited workspace

**Priority:** P2. **Type:** confirmed mismatch with likely user expectations.  
**Design:** `save_project` and phase 5 persistence.  
**Source:** `logic/project.py:134`, `py_backend.py:106` onward.

`project.json` currently contains project metadata, a sample summary string, calculation names, engine and status. It does not store coordinates, fixed flags, charge, multiplicity, calculation options or method settings. The backend explicitly treats many part edits as work that reset will discard even after a project save.

An assistant that says “saved your project” after modifying these fields can give the user a false expectation of recoverability. Conversation persistence would preserve statements about the configuration without necessarily preserving that configuration.

**Recommended correction:** either implement and test full workspace serialization as a prerequisite, or scope the tool and its success text to “saved project metadata; current calculation setup is not persisted.” Do not use `project.hasUnsavedChanges` as a complete workspace-dirty flag. The discard decision needs component-specific state, because `PyBackend.edited` also becomes true after unrelated method changes or a job run, not just sample edits.

**Acceptance test:** document what survives close/reopen and verify it. After saving metadata, the assistant must not claim unsaved coordinates or method settings are recoverable.

## R14 — Model flexibility exceeds the request compatibility contract

**Priority:** P2. **Type:** confirmed compatibility gap.  
**Design:** §§3 and 6, dependency plan.

The proposal always sends effort and server-side fallback options, while allowing Haiku and arbitrary model IDs. Current documentation explicitly excludes Haiku 5.5 from server-side fallback. Support for inline system messages and thinking behavior also varies by model. A model metadata lookup does not validate the complete streaming/tool request. [Anthropic fallback documentation](https://platform.claude.com/docs/en/build-with-claude/refusals-and-fallback).

Pin a tested SDK baseline and maintain a small model capability policy covering inline system messages, effort, thinking, strict tools, fallbacks, output limits and context capacity. Generate the request from that policy. Free-text IDs should enter an explicitly unsupported/verified path rather than inheriting every default feature. If inline system messages are unsupported, transform all relevant historical context consistently; changing only the newest snapshot leaves old incompatible messages in the transcript.

The default fallback feature can also change the model actually answering. Capture the returned model and fallback usage metadata so the label, cost estimate and audit do not attribute everything to the selected primary model. Make fallback behavior a deliberate product decision rather than an invisible consequence of the sample request.

The error table omits invalid-request/configuration errors, billing failures and oversized requests. Streaming can fail after HTTP success, and not every rate-limit error supplies a retry delay. Map these separately and always clear busy state through a finalization path. Streaming reduces some long-request timeout problems; it does not eliminate disconnects, stalled reads or server limits. [Anthropic error documentation](https://platform.claude.com/docs/en/api/errors).

Specify terminal behavior for `max_tokens`, context exhaustion, refusal, iteration exhaustion and unknown stop reasons. The example executes `generate_tool_call_response()` after every response except two named stops, rather than explicitly requiring a completed `tool_use` response. It also supplies no user-visible outcome for an iteration limit reached after local tools executed. Only completed, authorized calls should execute; truncated input must remain non-executable, and a turn ending without a final model answer must still report its actual action receipts. Keep this policy in sync with the pinned runner instead of partially reimplementing its stop-reason handling.

### API details that should not be incorrectly flagged as errors

The review checked current documentation rather than assuming older SDK behavior:

- The proposed 5.5 model family and Opus 5.5's default medium effort / always-on adaptive thinking are documented. Model availability still needs verification for the user's credentials. [Effort documentation](https://platform.claude.com/docs/en/build-with-claude/effort).
- Mid-conversation `system` messages are supported by the proposed 5.5 models, and placing one after a user message is supported. The defect is trusting external content as instructions and failing to define compatibility handling, not categorical API rejection. [Inline system messages](https://platform.claude.com/docs/en/build-with-claude/mid-conversation-system-messages).
- `ant auth login` profile resolution is documented; it should not be dismissed as invented behavior. [Anthropic CLI authentication](https://platform.claude.com/docs/en/cli-sdks-libraries/cli/authentication).
- Server-side fallbacks and the named beta exist; they are not universal across the offered models. See the fallback source above.
- The Python helper supports a `strict` argument. Use explicit decorator/schema configuration and inspect the generated nested schema; plain type hints alone are not a complete validation policy. [Python tool helper source](https://raw.githubusercontent.com/anthropics/anthropic-sdk-python/main/src/anthropic/lib/tools/_beta_functions.py).

Current SDK runner guidance recommends a manual loop when human approval or conditional execution is needed. This does not prove a gate inside a tool wrapper is impossible, but the proposal should justify that choice with a working lifecycle prototype rather than assert there is no orchestration to maintain. [Tool runner documentation](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-runner).

## R15 — Cache placement, accounting and trimming need correction

**Priority:** P2. **Type:** confirmed errors plus missing budget policy.  
**Design:** §4 caching; §6 lines 336–343; session cost label.

The sample puts its only cache marker on the static system prompt. That can cache the tools/system prefix, subject to model minimums, but does not mark the growing message history for caching. Append-only history preserves a prefix; it does not by itself cache that prefix. Use a deliberate moving message breakpoint or supported automatic caching.

`usage.input_tokens` alone is not total context size with caching. Total input also includes cache-read and cache-creation tokens. Set trimming thresholds using the selected model's capacity, tools/system overhead and reserved output, and count the next request before sending. Track per-call usage across the entire tool loop and distinguish cached reads, writes and ordinary input in cost calculations. [Anthropic prompt caching documentation](https://platform.claude.com/docs/en/build-with-claude/prompt-caching).

Dropping “oldest turns in pairs” is not a valid description of this transcript: a user turn can contain a snapshot, several assistant/tool exchanges and thinking blocks. Trim complete interaction groups and preserve tool-call/result linkage. Keep a bounded summary of relevant user constraints and actual actions; a one-line “older messages removed” note does not preserve intent. Treat summaries as summaries, not new operator instructions.

The configuration can request up to 12 model iterations with up to 16,000 output tokens each: a nominal ceiling of 192,000 generated tokens per user turn before other request behavior is considered. An iteration bound is also not a tool-call bound when one reply requests several tools. Add elapsed-time, token, tool-call and repeated-action budgets, and report when one is reached. Limit handling belongs in the first usable tool release, not polish.

## R16 — Payload and computation limits are not actually bounded

**Priority:** P2. **Type:** design gap.  
**Design:** §4 size limits and §5 read tools.

Two hundred atom objects plus choices cannot generally fit the claimed 1–3 KB snapshot. Sixty output lines may contain an arbitrarily long line. The 500-line output tool has no byte/token limit. `get_atoms.count` has no maximum or total per-turn read budget. A regex over all output can consume large CPU time, especially if run on the main thread. The code already retains the full output in chunks, and repeated `job.output` access joins all of it.

The rule that `atoms` changes type from a list to a summary string is also an avoidable schema inconsistency. First-30-mode truncation does not provide a typed way to fetch remaining modes; raw output search is a weak substitute for structured scientific data.

**Recommended correction:** impose byte/token ceilings on every snapshot field and tool result, not only row counts. Return stable envelopes such as `{items, total, offset, truncated, next_offset}`. Limit range requests and include sample/run identity. Prefer bounded literal output search for v1; if regex is required, cap pattern/input sizes and use an execution strategy with a real timeout. Provide paginated structured result retrieval where the product promises full results. Put file-size limits before parsing and expensive computations.

**Acceptance test:** one multi-megabyte output line, a large structure, invalid/huge ranges and pathological patterns must remain bounded and leave the UI responsive.

## R17 — Credential storage is not determined by whether `keyring` imports

**Priority:** P2. **Type:** confirmed incorrect assumption and design gaps.  
**Design:** §3 storage and UI.

Importing `keyring` does not establish a usable OS credential store. The package can select a failing, unavailable, locked, user-configured or alternative backend. Reads, writes and deletion can fail independently. Backend configuration is explicitly supported by the library. [Keyring documentation](https://keyring.readthedocs.io/en/latest/).

A silent fallback to base64 in QSettings makes insecure persistent storage the default when the optional extra is absent. Calling it plain text in a hint is accurate, but does not address migration, failures, stale copies or user expectations.

**Recommended correction:** inspect the selected backend and handle operation failures. Offer session-only credentials when secure storage is unavailable; require a deliberate choice for plaintext persistence. Define migration/removal of old QSettings values and clear both stores when requested. Keep secret resolution in Python; avoid exposing a saved secret as a broad QML property or copying it into turn objects, snapshots, telemetry or raw exception displays.

The source label has only Options/environment/none despite a fourth profile source. Presence of an Options key must not be the only criterion for `assistantConfigured`. Define precedence and behavior for an invalid Options key, clearing it when an environment/profile credential remains, and switching credentials during a turn. A local offline toggle must override automatic SDK credential discovery.

The log policy should cover application logs, SDK debug logs, tracing and saved transcripts, rather than only assuming `ANTHROPIC_LOG` stays unset. Test redaction using a synthetic secret. This does not require claiming an existing logger leaks keys; it establishes a verifiable implementation requirement.

## R18 — Implementation order and tests do not protect the first mutating release

**Priority:** P2. **Type:** confirmed sequencing issue.  
**Design:** §§10–11.

Phase 3 enables mutating tools before phase 4 adds approval and cancellation. Phase 5 postpones history limits and usage accounting. This creates an intermediate integration with the most important controls missing. The acknowledged charge/multiplicity prerequisite also has no assigned phase/files in the plan.

The proposed fake runner can make the pseudocode appear correct while hiding real SDK serialization, strict schema, stop-reason and iteration behavior. Live LLM output is nondeterministic, and an end-to-end test that requires a key must not accidentally discover and run the user's real expensive engine.

**Recommended sequence:**

1. Specify the snapshot schema, protocol transcript, outbound-data policy, model compatibility policy and typed tool outcomes.
2. Build controller cancellation, generation IDs, fake transport and a no-network tool harness.
3. Implement settings and read-only chat with real privacy filtering, limits and error handling.
4. Add transactional backend commands, revision checks, approval and action receipts together with each mutating tool.
5. Add workflow preflight/run/stop, provenance and scratch-folder disclosure.
6. Add conversation persistence and optional UI polish after the preceding behavior is verified.

### Required acceptance coverage

| Area | High-value test |
|---|---|
| Transcript | Two turns, multiple tools, complete snapshots, no duplicate input, valid tool-result linkage |
| Partial failure | Disconnect after each side-effect boundary; receipts remain truthful and retries do not duplicate effects |
| Approval | State changes while waiting, duplicate answer, late answer, timeout, denial followed by more calls |
| Cancellation | Queued tool, stalled stream, retry, clear/new turn, reset and application close |
| Threading | Assert QObject operations run on the main thread; responsiveness under slow preparation |
| Selection | Fix exact requested atoms despite a larger GUI selection |
| Validation | Invalid combined state is atomic; engine-ignored settings are rejected or clearly disclosed |
| Privacy | Inspect all outgoing requests after each sharing preference change; include old history and error messages |
| Files | Traversal, absolute paths, junctions/symlinks, malformed files, large files and duplicate example names |
| Persistence | Autosave side effects, failed save, actual close/reopen behavior and conversation/project identity |
| Results | Current workspace differs from the completed run; partial/failed/stopped jobs remain correctly identified |
| API contract | Chosen SDK serializes actual tool schemas and request parameters; fake HTTP streams cover supported stop/error events |
| Resources | Token/byte/call/time limits, iteration exhaustion, long single-line output and bounded output search |
| Credentials | No usable keyring backend, locked store, failed write/delete, profile source and clear/fallback behavior |
| Packaging | Example load and settings dialog work from the built/distributed application, not only the source checkout |

Use a deterministic fake engine and temporary run folder for the automated benzene workflow. Separate live-model evaluation from real-engine validation, make live tests explicitly opt-in, and register the proposed `network` marker (`pyproject.toml` currently registers only `fast`). Real request smoke tests should be small and cost-bounded.

## R19 — UI and persistence contracts need a few explicit decisions

**Priority:** P3. **Type:** design gaps.  
**Design:** §§7–8 and phase 5.

- `Assistant.modelName` is currently a constant Qt property (`assistant.py:58`); switching model/backend needs a notify signal. Configured model and model actually answering may differ.
- Current messages are `{role, text}` dataclasses exported as a new `QVariantList`. Define stable message/tool-call IDs and event ordering before adding action, approval and partial-text items. Coalesce deltas and update the active item rather than rebuilding/re-rendering the whole conversation for every token. The current scroll hooks observe message count and final replies, not growing content.
- Define a visible Cancel generation control distinct from Clear and engine Stop. Closing the panel, pressing Escape and changing settings during a turn need documented behavior. Waiting for approval should not accidentally hide the only usable cancellation path.
- `assistantSetPage` records context; it does not navigate. `show_page` needs a main-thread navigation signal mapped by QML to `EaGlobals.Vars.appBarCurrentIndex`, followed by acknowledgment. It must not just call `setPage` and falsely report that the visible page changed.
- Model-generated Markdown should have a deliberate policy for links, images and local resource references. Do not let rendering introduce an unreviewed filesystem/network path outside the tool policy; verify the actual Qt component's behavior before claiming it is safe.
- Define whether project create/load/reset starts a new conversation, migrates it or retains it with a visible boundary. An opt-in `assistant.json` needs schema versioning, atomic writes, redaction, retention and corrupt-file handling. On load, render stored approvals/actions as historical records; never resume pending tools or approvals automatically.
- Add the new QML component to the component registration/package setup as required by the current project. The plan should explicitly include `BackendWrapper.qml`, `ApplicationWindow.qml`, `Components/qmldir`, and any prerequisite backend/UI files.

## Suggested minimum execution contract

The existing module split can be retained if the interfaces are made concrete. A minimal command flow should be:

1. The main controller creates a turn ID and immutable, privacy-filtered workspace snapshot with project/sample/configuration revisions.
2. The worker receives plain data and fixed per-turn settings, constructs a compatible provider request, and emits structured events carrying that turn ID.
3. A tool request is normalized and validated against the current domain state. Reads obey the same outbound-data policy as the initial snapshot.
4. For a mutation, the controller prepares an action record with exact arguments, anticipated effects and relevant revisions. It requests approval if the effect policy requires it.
5. Immediately before commit, the main thread checks cancellation, identity, revisions and preconditions again. It executes a domain command with defined atomicity and captures its actual outcome.
6. An action receipt is recorded before the next network request. The UI and tool result are derived from the same receipt.
7. Completed protocol exchanges are committed once. Network failure leaves local facts about executed actions intact. Limits, denial and cancellation have explicit terminal states.
8. A workflow run records immutable input provenance; later output and results refer to that run rather than being implicitly assigned to the current workspace.

This is more orchestration than the proposal acknowledges, but it can remain small. It replaces implicit assumptions with testable boundaries and avoids building a large general-purpose agent framework.

## Recommendation

Retain the broad architecture and dedicated-tool approach. Revise the design around R01–R09 before enabling actions, then resolve the request compatibility, limits and error-outcome contracts before shipping network chat. The most urgent concrete corrections are exact-index atom updates, approval tied to workspace revisions, preservation of executed-action receipts, privacy filtering across all outbound paths, and truthful treatment of autosave, scratch runs and metadata-only project saving.

The claimed API features should be versioned and tested, not removed merely because older Anthropic APIs behaved differently. The implementation should be judged by a deterministic failure-and-recovery test matrix, not just the successful benzene demonstration.
