# EasyQM assistant — LLM integration design

*How the assistant panel gets a real model behind it: Anthropic API key in Options, the
whole workspace in the model's context, and tools that let the model drive the GUI.*

Status: implemented, revision 4, 2026-11-05. Revision 1 (2026-11-04) was reviewed in
`LLM_INTEG_REVIEW_DS.md` and `LLM_INTEG_REVIEW_GPT.md`; §16 records what changed and why.
§17 records where the implementation is simpler than revision 2 or corrects it; §5.3, §8.1 and
§8.4 are updated to match the code. Revision 4 (same day) adds the atom-editing, cell, view and project tools (§6) and
makes the two patch tools non-strict to stay within the API's schema limits.
Builds on the panel mock-up (`Gui/Components/AssistantPanel.qml`, `Backends/Py/assistant.py`,
`Backends/Py/logic/assistant.py`) and replaces its stub.

---

## 1. Goals

1. **Talk about the workspace.** The model sees what the GUI shows: project, sample (atoms,
   cell, symmetry, charge and multiplicity), selected calculations and their options, engine,
   level of theory, SCF and run settings, job state and output, results. §5 lists exactly which
   fields; "everything" is a direction, the registry is the contract.
2. **Act on the workspace.** The model changes the sample and the calculation setup and runs the
   workflow through backend *commands* that the sidebar controls also use. The GUI follows because
   the commands emit the signals the QML binds to.
3. **Stay truthful and safe.** Every action is recorded as a receipt and shown in the chat. Actions
   that start a job, replace the structure or persist to disk are gated, and the gate is bound to
   the exact state that was approved. The key is stored locally and never logged.
4. **Work offline.** Without a key, without the optional `anthropic` package, or with the offline
   switch on, the panel degrades to the current stub.

Example that must work end to end:

> "Load benzene.xyz, choose cc-pVDZ basis set and run geometry optimization with ORCA"

Expected: structure loaded from the packaged examples, basis set set to cc-pVDZ after checking it
is in the ORCA choices, geometry optimisation ticked, a confirmation card for *Run workflow* that
names the destination folder (project or scratch), then the job starts and the model summarises
what it did. ORCA is not chosen by a tool: the engine follows the sample (molecule → ORCA, periodic
→ Quantum ESPRESSO), so the model reports that ORCA is already active or explains why the named
engine cannot run this sample.

Decisions that were implicit in revision 1 and are now explicit:

- **Arbitrary file paths are not a v1 feature.** `load_structure` resolves packaged examples, files
  in the project folder, and files the user picked in a file dialog this session. Nothing else.
- **Mutations during a running job are refused** by the tools (the GUI still allows them; the
  snapshot reports the running job's own configuration separately).
- **Scratch runs are allowed** without a project, and the run card says so.
- **Autosave is part of an approved mutation.** A gated change that the user approves includes the
  project file write that follows it; ungated changes with autosave on also write, and the one-time
  disclosure says so.

Non-goals: multi-user or server deployment, file-system browsing by the model, editing engine
paths or preferences by the model, running arbitrary code, workspace serialisation beyond what
`project.json` holds today (see `save_project`).

---

## 2. Architecture

```
QML AssistantPanel  ──signals/slots──  Assistant (QObject, main thread)
                                           │  controller: state machine, transcript owner,
                                           │  receipts, approval gate, settings
                                           │
                                   AssistantWorker (QThread)
                                           │  one turn: SDK tool runner, streaming, events with turn_id
                                           │
                       ┌───────────────────┼─────────────────────┐
               ClaudeBackend          WorkspaceSnapshot       WorkspaceTools
          (anthropic SDK client)   (registry-driven, pure)   (ToolRequest → ActionRecord →
                                                              command on the main thread → ToolOutcome)
                                                                      │
                                   Commands layer (atomic, revisioned) over
                                   Project · Sample · Calculations · Method · Job · Results
```

| Module | Thread | Responsibility |
|---|---|---|
| `logic/assistant.py` (exists) | any | `Context`/`Message`, `AssistantBackend` protocol, `StubAssistant`. The protocol gains `run_turn` (§8); `reply` stays for the stub and its tests. |
| `logic/assistant_registry.py` (new) | any | The **field registry** (§5.2): one entry per GUI-exposed value with path, kind, unit, choices, `effective_for` engines, trust class and byte cap. Generates the snapshot, the tool schemas and the validation. |
| `logic/assistant_snapshot.py` (new) | main | Builds `WorkspaceSnapshot` (plain dataclass, no Qt objects) from the parts through the registry and the `OutboundPolicy`. |
| `logic/assistant_tools.py` (new) | main for execution | Tool definitions, `ToolRequest` normalisation, validation, `ActionRecord` creation, dispatch to commands, `ToolOutcome` → tool-result text. |
| `logic/assistant_policy.py` (new) | any | `OutboundPolicy` (§12), `ModelPolicy` (§8.2), `Budgets` (§8.4), the path resolver policy. |
| `logic/claude_backend.py` (new) | worker | Wraps `anthropic.Anthropic`. Runs one turn with the tool runner and reports events. Imported lazily. |
| `Backends/Py/commands.py` (new) | main | Atomic, revisioned commands over the parts (§3). The GUI slots call them too. |
| `assistant.py` (exists, extended) | main | Controller: state machine, `protocol_history`, `ui_items`, `action_receipts`, worker lifetime, approval gate, QML signals. |
| `assistant_settings.py` (new) | main | Key resolution and storage, model, effort, approval mode, outbound options. |
| `Gui/Components/AssistantPanel.qml` (exists, extended) | GUI | Streaming item updated in place, action rows, approval cards, cancel, navigation. |
| `Gui/Components/AssistantSettingsDialog.qml` (new) | GUI | The Options UI (§4). |

Two rules hold everything together:

- **Only the worker talks to the network; only the main thread touches the parts.** The worker
  receives immutable data (`turn_id`, a copy of the committed transcript, settings values) and
  emits events; it never holds a reference to a part or to the settings object.
- **One mechanism for tool dispatch:** a worker→main signal carrying `(turn_id, call_id, request)`
  and a `QWaitCondition` the worker blocks on, with a bounded wait and a generation check. Not
  `BlockingQueuedConnection`: a wait condition can be woken by cancellation and by shutdown, a
  blocking queued call cannot.

---

## 3. Prerequisites in the backend (independent of the LLM)

The reviews showed that the parts do not yet offer what a tool layer can build on. These items are
small, benefit the GUI too, and come first.

| # | Change | Why |
|---|---|---|
| P1 | **Revision counters** on `Sample`, `Calculations`, `Method` (level of theory, SCF, run, k-points), `Project`, bumped in every setter. | Approvals and atom indices are bound to a revision (§7). None exist today; signals carry no counter. |
| P2 | **Commands layer** (`commands.py`): `set_method_fields(patch)`, `set_calculation_options(patch)`, `select_calculations(types, mode)`, `set_atoms_fixed(indices, fixed)`, `set_electronic_state(charge, multiplicity)`, `load_structure(path)`, `run_workflow()`, `stop_job()`, `save_project()`. Each validates the **whole** proposed state first, applies all or nothing, emits each changed signal once, and returns a `CommandOutcome` (`ok` / `changed` / `declined` / `failed` / `already_running` / `stale_state`, applied values, effective values, messages). | `helpers.apply` validates nothing; multi-field edits today emit one signal and one autosave per field; `Job.run`, `Project.save`, `Sample.loadStructure` return `None` and report through signals. |
| P3 | **Exact-index fix command.** `Sample.setAtomFixed` expands to the GUI selection by design; the new `set_atoms_fixed` takes explicit zero-based base-atom indices, deduplicated, validated against the sample revision, and returns the atoms it changed. The GUI slot calls it with the selection. | The assistant must fix exactly the atoms it names. |
| P4 | **Validation at the point of use.** `logic.method.validate(method, capabilities)` and `logic.calculations.validate(...)` return a list of problems; adapters map unknown enum values to `ValueError('unsupported <field>: <value>')` instead of `KeyError`; `Job.run` catches `Exception`, logs the traceback, and sets `failed` with the message. | A missed field today escapes `Job.run` as an uncaught `KeyError` after the tool already said "started". |
| P5 | **Effective fields.** Each adapter declares which method and option fields its input generation consumes (`consumed_fields()` derived from the keyword tables). `RunSettings.cores` is read by no adapter and `keep_trajectory` by none; either remove them from the GUI or mark them *not effective* in the registry. The HF/dispersion and analytical-plus-Raman overrides in the ORCA adapter become explicit validation messages. | The tool must never report "cores set to 4" for a value nothing reads. |
| P6 | **Electronic state setters** (`Sample.setCharge`, `setMultiplicity`) that share the parity invariant `logic/sample.py` applies on atom changes, validated together against the electron count and the method reference, plus the sidebar controls that today show the values read-only. | Needed by `set_electronic_state`; without them the only writer of charge is `load()`, which resets it. |
| P7 | **Run provenance.** `Job.run` records a `RunRecord` (run id, folder, engine and version, sample fingerprint = atom count + element sequence + coordinate hash, method label and effective settings, calculation order) and `Results` carries the record it was parsed from plus `matches_current_state` and `stale_reason` (sample replaced, method changed, geometry applied). | Results today stay on screen after the sample or method changed, with nothing saying which run they belong to. |
| P8 | **Preflight.** `Job.preflight()` generates the input files and checks executables and resources (pseudopotential folder, `ph.x`/`dynmat.x`, empty selection) without starting anything, returning the problems. | The approval card must describe a run that can start; a KeyError-class failure after approval is a false "started". |
| P9 | **Loader hardening.** Size cap before `read_text` (default 20 MB), parse errors without file text ("line N: not `element x y z`"), and `load()` reporting the previous and new charge/multiplicity. | Parse errors today quote the offending line; the design must not ship file bytes to the API through an error message. |
| P10 | **Reset and project-change ordering.** `PyBackend.reset()`, project create and project load call `assistant.cancel_turn()` and wait for the acknowledgement **before** touching any part; `externalProjectChanged` becomes a conversation boundary. | Today the assistant is reset last, after the parts an in-flight tool may be mutating. |

---

## 4. API key and settings (Options)

### Storage and resolution

- Preferences (`model`, `effort`, `approval_mode`, `send_engine_output`, `send_results`,
  `offline`, `api_key_storage`) live in `QSettings('EasyScience', 'EasyQM')`, group `assistant`,
  the store the engine paths use.
- The key: `AssistantSettings` probes the OS credential store at start-up through `keyring`
  (`get_keyring()` and a sentinel write/read/delete under service `EasyQM`, user `assistant-probe`)
  and reports one of *secure store available* / *store present but locked or failing* / *no store*.
  Only a passing probe enables "Remember this key". Otherwise the dialog offers **session only**
  (default) or **store in settings as plain text** behind an explicit checkbox that names the file.
  No silent base64 fallback.
- Resolution at request time, first match wins: Options key (session or stored) → `ANTHROPIC_API_KEY`
  / `ANTHROPIC_AUTH_TOKEN` → an `ant auth login` profile (the SDK resolves the last two when it is
  built without `api_key=`). The dialog shows the active source: *Options*, *environment*, *CLI
  profile*, *none*. `assistantConfigured` means "a credential resolves now and offline is off", not
  "Options holds a key".
- An invalid Options key is reported as such; it is not silently bypassed by an environment key.
  *Clear key* removes it from the session, the secure store and the settings file.
- **Offline switch** (default off): when on, no request is made even if a credential resolves.
- The secret is wrapped in a `Secret` type that renders as `***` in `repr`, logs and tracebacks, is
  never a QObject property, and never enters a turn object, snapshot or persisted transcript. A test
  runs a full fake session with a synthetic key and greps every log and request-body capture.

### UI

The framework `PreferencesDialog` hard-codes its tabs and the app bar cog has no handler, so v1
uses an EasyQM-owned `AssistantSettingsDialog.qml` opened from a gear in the panel header and from
the cog (which can grow a general EasyQM preferences dialog later). Upstreaming a tab slot to
EasyApplication stays the long-term option.

| Field | Control | Notes |
|---|---|---|
| API key | password `TextField`, show/hide, clear | Storage line as probed (§4.1). |
| Verify | button | Runs `client.models.retrieve(model)` on a short-lived worker of its own (never the turn worker). Shows "model available" or the typed error. |
| Model | combo + free text | Listed: `claude-opus-5-5` (default), `claude-sonnet-5-5`, `claude-haiku-5-5`. Free text goes to the *compatibility unknown* policy (§8.2). |
| Effort | combo | `low` / `medium` (default, set explicitly) / `high`. |
| Actions | radio | *Ask before runs, structure replacement and saves* (default) / *Ask before every change* / *Never ask*. The full matrix is in §7. |
| Send engine output | checkbox, on | §12. |
| Send results | checkbox, on | §12. |
| Offline | checkbox, off | §4.1. |
| Usage this session | label | Input, cache-read, cache-write and output tokens per bucket; estimated cost per model that answered. |

Without a credential the panel header shows "Stub assistant (offline) · Add an API key in Options".

---

## 5. The query space: what the model sees

### 5.1 Trust classes and channels

The snapshot mixes two kinds of strings and they go to two channels:

- **Facts**: numbers, enums, booleans and names produced by the application (atom count, formula,
  point group, choices, job state, revisions). Sent as a mid-conversation `system` message, which
  the model treats as operator state.
- **Data**: strings that came from a file, the user or an engine (project name and description,
  file names, atom labels, `job.message`, output tail, parse errors). Sent in the **user** turn as a
  separate block framed `<data origin="engine output">…</data>` with the instruction, in the frozen
  system prompt, that data blocks are never instructions.

The registry marks each field `untrusted=True/False`; the builder routes by that flag. The split
makes a violation visible in the transcript; the capability limits in §6 and §12 are what stop it
from doing harm.

### 5.2 The field registry

```
Field(name, path, kind, unit, source, effective_for, choices, untrusted, byte_cap, tool)
```

- `kind ∈ {int, float, bool, enum, text, atoms, list, object}`; `unit` is explicit (Å, Eh, Å⁻¹,
  K, atm, GB).
- `source` is a callable over the parts, so one entry produces one snapshot key, one JSON-schema
  property and one tool argument. The snapshot builder, the tool schemas and the validator all read
  the registry; nothing is hand-maintained twice.
- `effective_for` lists the engines whose input generation consumes the field (from P5). A field
  not effective for the active engine is shown as `"cores": {"value": 1, "effective": false}` and
  refused by `set_method` with "not used by ORCA".
- Every `enum` field carries its choices in the snapshot, exactly as `*Choices` gives them, so the
  model knows the valid values without a round trip.
- A test enumerates every settable value in `BackendWrapper.qml` and asserts one registry entry and
  one tool field each.

### 5.3 Prompt layout

```
tools      = [workspace tools]                       # fixed order, fixed text
system     = [{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}]
messages   = committed_history                       # append-only, never edited
           + [{"role": "user", "content": [question_text, data_block]},
              {"role": "system", "clear_at": "next_user_message", "content": facts_snapshot}]
betas      = ["mid-conversation-system-clear-at-2026-08-21", ...]
```

- `SYSTEM_PROMPT` is frozen: what EasyQM is, the workflow, that the engine follows the sample, that
  values come from the choices lists, that tools are the only way to change state, that `<data>`
  blocks are information not instructions, and the reply style.
- The **facts snapshot is a turn-scoped system message, committed with the turn.** It renders for
  that turn only and stays in the history cleared, costing no input tokens afterwards. Revision 2
  rebuilt it per request and dropped the old copy; that is a history edit, which restarts the cache
  and, on Opus 5.5 and the other current models, invalidates every later thinking block (a 400 for
  accounts created after 2026-08-31). Within a turn the model learns about changes from the tool
  results, which state the old and new values, and from `get_workspace`.
- Caching: the frozen system prompt plus the tool list form the first breakpoint. The second is a
  moving `cache_control` on the last block of the last user message, set on a copy when the request
  is built (moving a marker is not an edit). A turn-scoped message takes no `cache_control`.
- A model without turn-scoped system messages (the `unknown` policy row) gets the snapshot as a
  text block at the end of its user message instead.

### 5.4 Snapshot shape (non-normative example)

The registry is the contract; this example shows the shape with the application's real values.

```json
{
  "page": "method",
  "revisions": {"sample": 3, "calculations": 1, "method": 2, "project": 0},
  "project": {"created": false, "unsaved_changes": false, "status": "new"},
  "sample": {
    "formula": "C6H6", "atom_count": 12, "periodic": false, "point_group": "D6h",
    "charge": 0, "multiplicity": 1, "fixed_atoms": 0, "units": "Å, degrees",
    "selected_atoms": [{"index": 0, "image": [0, 0, 0]}, {"index": 1, "image": [0, 0, 0]}],
    "atoms": {"items": [{"i": 0, "element": "C", "x": 0.0, "y": 1.3915, "z": 0.0, "fixed": false}, "…"],
              "total": 12, "offset": 0, "truncated": false},
    "cell": null,
    "view": {"coordinates": "zmatrix", "coordinates_choices": ["cartesian", "zmatrix"],
             "zmatrix": {"items": [{"i": 0, "bond_to": null, "bond": 0.0, "angle_to": null, "angle": 0.0,
                                    "dihedral_to": null, "dihedral": 0.0},
                                   {"i": 1, "bond_to": 0, "bond": 1.3915, "angle_to": null, "…": "…"}, "…"],
                         "total": 12, "truncated": false}}
  },
  "calculations": {
    "selected": ["geometry_optimisation"],
    "available": ["single_point", "geometry_optimisation", "vibrational_frequencies"],
    "options": {
      "single_point": {"print_orbitals": true, "geometry": "optimised", "geometry_choices": ["optimised", "input"]},
      "geometry_optimisation": {"convergence": "tight", "convergence_choices": ["loose", "normal", "tight", "verytight"],
                                "max_steps": 100, "optimise": "positions", "optimise_choices": ["positions", "positions_and_cell"]},
      "vibrational_frequencies": {"type": "analytical", "type_choices": ["analytical", "numerical"],
                                  "temperature": 298.15, "temperature_unit": "K", "pressure": 1.0, "pressure_unit": "atm", "raman": false}
    }
  },
  "method": {
    "engine": {"name": "ORCA", "found": true, "version": "6.1.1", "can_run": true, "cannot_run_reason": ""},
    "engines": [{"name": "ORCA", "active": true, "found": true, "problem": ""},
                {"name": "Quantum ESPRESSO", "active": false, "found": false, "problem": "Quantum ESPRESSO runs periodic samples only; this sample is a molecule."}],
    "family": "DFT", "family_choices": ["HF", "DFT"],
    "functional": "B3LYP", "functional_choices": ["B3LYP", "PBE", "PBE0", "…"],
    "dispersion": "D3BJ", "dispersion_choices": ["…"],
    "basis_set": "def2-TZVP", "basis_set_choices": ["def2-SVP", "def2-TZVP", "cc-pVDZ", "…"],
    "auxiliary_basis": "def2/J", "auxiliary_basis_choices": ["def2/J", "def2/JK", "none"],
    "reference": "RKS", "reference_choices": ["RKS", "UKS", "ROKS"],
    "solvation": "none", "solvation_choices": ["…"],
    "scf": {"convergence": "tight", "convergence_choices": ["loose", "normal", "tight", "verytight"],
            "max_iterations": 125, "integration_grid": "DefGrid2", "integration_grid_choices": ["…"], "stability_check": false},
    "run": {"memory_gb": 16, "cores": {"value": 1, "effective": false}},
    "kpoints": null
  },
  "job": {"state": "idle", "run_id": null, "running_config": null, "steps": {}},
  "results": {"available": false}
}
```

After a run, `job.running_config` holds the `RunRecord` while the job runs, and `results` holds
`run_id`, `matches_current_state`, `stale_reason`, `process_ended_normally`, `scf_converged`,
`optimisation_converged`, `geometry_applied`, `tiles`, and `modes` as a paginated envelope.

The `<data>` block of the same turn carries: project name and description, structure file name,
atom labels, `job.message`, output tail (last 60 lines, each line capped at 400 bytes, whole block
capped at 8 KB), folder paths with the home directory replaced by `~`.

Limits are **bytes, not rows**: every text field has a `byte_cap`; `atoms` is always an envelope
`{items, total, offset, truncated}` (never a type switch to a string); the whole snapshot is capped
at 24 KB, and the builder drops `atoms.items` to the first 50 before anything else when the cap is
hit. The reviews' point stands: 200 atom dicts are ~18 KB, not "1–3 KB".

---

## 6. Tools: how the model changes the workspace

### 6.1 Rules

- One tool per GUI concept, typed optional fields, `strict: true` with `additionalProperties:
  false`, descriptions that say *when* to call. Schemas come from the registry.
- The API caps a request at 20 strict tools, 24 optional parameters and 16 union-type parameters
  across all strict tools, and refuses the whole request above that. `set_method` (15) and `set_calculation_options` (12) exceed it on their own,
  so these two patch tools are sent with `strict: false`. The registry validates every key and value of a
  patch anyway. The other 18 are strict, with 10 optional parameters and no unions; a test keeps
  them within the limits.
- A tool request is normalised to `ToolRequest(turn_id, call_id, tool, args)` and validated against
  the registry on the main thread. Multi-field patches are **all or nothing**: any invalid or
  ineffective field rejects the whole patch with the valid options, and nothing is applied.
- A mutation becomes an `ActionRecord(turn_id, call_id, tool, normalised_args, effects, revisions,
  preview)`. Effects ∈ {`read`, `navigate`, `mutate`, `replace-sample`, `persist`, `start-job`,
  `stop-job`}. `persist` is added automatically when autosave is on and a project is created.
- Immediately before commit the main thread re-checks: turn still live, revisions unchanged,
  job-state precondition. A mismatch returns `stale_state` with what changed; nothing executes.
- Every tool returns a `ToolOutcome` → text for the model (`"basis_set: def2-TZVP → cc-pVDZ
  (revision method 3)"`) plus the outer `is_error` flag for `failed`/`stale_state`; `declined` is
  not an error. A receipt is stored before the next request. The action row is rendered from the
  receipt, not from provider content.
- Twenty tools. No `bash`, no file browsing, no engine-path or preference edits, and no tool that
  clicks a control: each tool names the state it changes, as a control does, so that it can be
  validated and shown on an approval card. "Click Add atom" is `add_atom`, "show the Z-matrix" is
  `set_view`; the system prompt says so.

### 6.2 Tool table

| Tool | Inputs | Precondition | Effects | Notes |
|---|---|---|---|---|
| `get_workspace` | `sections?` | – | read | Current facts + data for the listed sections. |
| `get_atoms` | `offset`, `count ≤ 100` | – | read | Envelope; includes sample revision. |
| `get_job_output` | `lines ≤ 200`, `contains?` (literal, ≤ 100 chars) | – | read | Byte-capped (16 KB). Refused locally when *Send engine output* is off. |
| `show_page` | `page` enum | no modal dialog open | navigate | Emits `navigateRequested`; QML sets `EaGlobals.Vars.appBarCurrentIndex` and acknowledges; the result reports the page actually shown. |
| `load_structure` | `name` | job not running | replace-sample (+persist) | Resolver policy: packaged examples (`Resources/structures/…`, the repository `examples/` are copied there at build), files in the project folder, files picked in a dialog this session. Canonicalised, link-resolved, containment-checked, size-capped. Result names previous and new charge/multiplicity. Gate: replace-sample when `Sample` revision > 0 since the last load. |
| `add_atom` | `element`, `position`, `coordinates` = cartesian/fractional | job not running | mutate | As the Add atom button, at a given position; the new atom is selected. Fractional for crystals only. |
| `remove_atoms` | `indices`, `sample_revision` | job not running; one atom stays | mutate | Exact indices; later indices drop. Stale revision → `stale_state`. |
| `move_atoms` | `moves` [{`index`, `position`}], `coordinates`, `sample_revision` | job not running | mutate | All moves or none, one notification. |
| `set_zmatrix_value` | `atom`, `field` = bond/angle/dihedral, `value`, `sample_revision` | job not running; the tables show the Z-matrix | mutate | Values measured to the origin or an axis are refused; values the Z-matrix cannot place fail with the reason. |
| `set_cell` | `a`, `b`, `c`, `alpha`, `beta`, `gamma` | job not running; crystal | mutate | All six, checked before anything changes; atoms keep fractional coordinates. |
| `set_view` | `coordinates?`, `repeat?`, `boundary_atoms?`, `selected?` | – | navigate | Done at once, never asks; switches to the Sample page. Choices from `sample.view`; repeat and boundary atoms for crystals. |
| `set_project_details` | `name?`, `description?`, `autosave?` | – | mutate, or persist when it turns autosave on for a created project | The name must be usable as a folder name (it is one until the project is created). |
| `set_electronic_state` | `charge?`, `multiplicity?` | job not running; P6 done | mutate (+persist) | Validated together against electron count and the method reference. |
| `set_atoms_fixed` | `indices`, `fixed`, `sample_revision` | job not running | mutate | Exact indices (P3); stale revision → `stale_state`. |
| `select_calculations` | `types`, `mode` = replace/add/remove | job not running | mutate (+persist) | One command, one signal, one save. |
| `set_calculation_options` | per-type objects | job not running | mutate (+persist) | Engine-ineffective options refused with the reason (Raman on QE, Raman with analytical on ORCA). |
| `set_method` | `family?`, `functional?`, `dispersion?`, `basis_set?`, `auxiliary_basis?`, `reference?`, `solvation?`, `occupations?`, `scf_convergence?`, `scf_max_iterations?`, `integration_grid?`, `stability_check?`, `memory_gb?`, `kpoint_spacing?` xor `kpoint_grid?` | job not running | mutate (+persist) | `family` added; `cores` removed (not effective, P5). Spacing and grid are mutually exclusive in one call. |
| `run_workflow` | – | job idle/ended; preflight passes | start-job (+persist of status) | Card shows engine and version, calculations in order, method label, sample fingerprint, **destination folder (project or scratch)**. Running → `already_running` with the run id. Result: new run id, folder, state. |
| `stop_job` | – | job running | stop-job | Returns when the process ended; bounded wait, reported if exceeded. |
| `save_project` | – | project created | persist | Result text is scoped: "project metadata saved (name, description, sample summary, calculations, engine, status); coordinates, options and method settings are not stored in the project file." |

Deliberately absent: `set_engine` (engine follows the sample), `set_engine_path`,
`create_project` (needs a folder picker; the model asks the user), a generic "click this control"
tool (see §6.1).

---

## 7. Gates and approvals

| Effect | Ask before runs, replacement and saves (default) | Ask before every change | Never ask |
|---|---|---|---|
| read, navigate | – | – | – |
| mutate | – | card | – |
| replace-sample | card | card | – |
| persist (explicit `save_project`) | card | card | – |
| persist (autosave after an approved mutation) | included in that approval | included | – |
| persist (autosave after an ungated mutation) | silent, disclosed once (§12) | n/a | silent |
| start-job | card | card | – |
| stop-job | – | card | – |

Mechanics:

- The card is rendered from the `ActionRecord`; the answer carries `record_id`. Expired, duplicate
  and late answers are no-ops. While a card waits the input is disabled but **Cancel generation**
  stays available (§11).
- The worker waits on the wait condition with a timeout (default 5 min). Denial or timeout returns
  the outcome `declined`, and the controller refuses a second identical `(tool, args)` in the same
  turn with "already declined". Remaining mutations in the same assistant message after a denial
  are also declined, so a batch cannot half-execute.
- On approval the main thread re-checks revisions and preconditions; a mismatch rebuilds the card
  with a diff ("basis set changed to def2-SVP since this card was shown").
- `run_workflow` runs `Job.preflight()` **before** the card; a failing preflight returns `failed`
  with the problems and no card.

---

## 8. Request shape, model policy, budgets, errors

### 8.1 One turn

`logic/claude_backend.Turn.run()` runs on the worker thread: a manual loop over
`client.beta.messages.stream(...)` (see §17 for why not the SDK tool runner).

```python
for _ in range(MAX_REQUESTS):                                  # 6
    with client.beta.messages.stream(model=..., max_tokens=8000, system=[...], tools=TOOLS,
                                     messages=with_breakpoint(history + pending),
                                     output_config={"effort": effort}, betas=[...],
                                     fallbacks="default") as stream:   # per the model policy
        for text in stream.text_stream: on_text(text)          # to the panel's streaming bubble
        message = stream.get_final_message()
    pending.append({"role": "assistant", "content": message.content})
    if message.stop_reason != "tool_use":                      # end_turn, max_tokens, refusal, …
        break                                                  # (unexecuted tool_use blocks get results)
    results = [dispatch(use) for use in tool_uses(message)]    # main thread: check, approve, run
    pending.append({"role": "user", "content": results})
return TurnResult(messages=pending_up_to_the_last_complete_exchange, note, error, usage, model)
```

The controller, not the worker, appends the returned messages to the history. A tool only runs on
a completed `tool_use` block of a `tool_use` stop; a `tool_use` in a message cut off by
`max_tokens` gets a "not executed" result so the next request stays valid. Eager input streaming is
off, so the server validates the `strict` schemas (all tools except the two patch tools, §6.1). `max_tokens`, `refusal`, budget exhaustion and
unknown stop reasons end the turn with a visible note.

### 8.2 Model policy

`ModelPolicy` is a small table consulted when the request is built; free-text model IDs get the
`unknown` row.

| Model | inline `system` messages | `effort` | thinking | strict tools | fallbacks | max output | context |
|---|---|---|---|---|---|---|---|
| `claude-opus-5-5` | yes | yes (default medium) | always on, omit param | yes | `fallbacks="default"` + beta `server-side-fallback-2026-07-01` | 128K | 1M |
| `claude-sonnet-5-5` | yes | yes | adaptive | yes | `"default"` form only, Claude API only | 128K | 1M |
| `claude-haiku-5-5` | yes | yes (default medium) | adaptive | yes | **none** | 128K | 1M |
| unknown | no: snapshot goes into the user turn instead, consistently for the whole conversation | no | omitted | yes | none | 8K | 200K assumed |

The row also decides the fallback policy. Fallbacks are a product decision: on by default for Opus
and Sonnet, shown in the dialog, and the **model that actually answered** (from `response.model`
and `usage.iterations`) is recorded per turn and shown in the header when it differs from the
configured one. The SDK version is pinned (`anthropic>=1.1,<2`) and a test serialises a real
request body through the runner against a fake HTTP transport.

### 8.3 Transcript ownership and recovery

| Structure | Owner | Content |
|---|---|---|
| `protocol_history` | `Assistant`, committed in one place | provider messages with full content blocks (text, tool_use, tool_result, thinking) |
| `ui_items` | `Assistant`, exposed to QML | user / assistant / action / approval / outcome items with stable ids |
| `action_receipts` | `Assistant`, never discarded | `{turn_id, call_id, tool, args, outcome, effects, revisions_after, run_id}` |

A turn commits the user turn once, then each assistant message and tool-result group as the events
arrive. On a network failure mid-turn the committed exchanges stay; an assistant message whose tool
results never completed is removed together with its tool_use blocks (the API rejects a dangling
pair), but the receipts of tools that did run stay and the outcome line says "connection lost after:
basis set changed, run 003 started". The stub never answers a failed network turn as if it were the
model; it only reports the failure. Replaying a completed action is distinguished from a fresh one
by `call_id`.

### 8.4 Budgets and trimming

Per turn: 6 requests, 12 tool calls, 4 min wall clock (checked before each request), and an action
the user declined is not asked for again in the same turn. Per session: 2M tokens counted over all
four usage buckets; past it the assistant says so and stops sending. The dialog shows the usage per
bucket. Hitting a budget ends the turn with a visible line.

**No client-side trimming.** Dropping old turns is a history edit, which invalidates the thinking
blocks after it on the current models. With a 1M context and byte-capped snapshots a session reaches
the session token ceiling long before the context limit; an oversized request comes back as a
`BadRequestError`, whose message tells the user to clear the conversation. Server-side compaction is
the way to add long sessions later.

### 8.5 Errors

Most specific first; every path clears `busy` through one finaliser.

| Condition | Message in the panel |
|---|---|
| `AuthenticationError` | "The API key was rejected. Check it in Options." |
| `PermissionDeniedError` / `NotFoundError` | "This key cannot use model X. Pick another model in Options." |
| `BadRequestError` (invalid request, oversized context) | "The request was rejected: <message>. Try a shorter conversation (Clear) or another model." |
| billing/credit errors (`APIStatusError` 402/403 with billing text) | "The account has no remaining credit." |
| `RateLimitError` | "Rate limited; try again in N s" when `retry-after` is present, else "try again shortly" |
| `APIStatusError` ≥ 500 | "Anthropic reported a server error; try again." |
| `APIConnectionError` / `APITimeoutError` / stream broken after 200 | "Connection lost. <receipts of what ran>" — no stub answer |
| `stop_reason == "refusal"` on the final message | "The model declined this request." |
| budget hit, `max_tokens`, iteration limit | one outcome line naming the limit and the receipts |

---

## 9. Controller state machine, cancellation, shutdown

States: `idle → streaming → awaiting_approval → executing → finishing → idle`, plus `cancelling`.
Every worker event and every main-thread command carries `turn_id`; events for a dead turn are
dropped.

Cancellation (`Cancel generation`, `clear()`, `reset()`, project create/load, settings change of
model or key during a turn):

1. mark the turn dead and set the state to `cancelling`;
2. wake the approval and dispatch wait conditions, which return `declined`/`cancelled` to the
   worker;
3. close the stream (`stream.close()` on the SDK stream object) and let the runner raise into the
   worker's `finally`, which releases the client;
4. on the main thread, before any pending mutation commits, re-check that the turn is alive;
5. keep the GUI event loop running until the worker acknowledges; bound the wait (10 s), log and
   mark the worker abandoned if exceeded.

A cancel keeps the transcript and the receipts; `clear()` asks for confirmation when a turn is live
and then discards the transcript. Cancelling generation never stops an engine job; the Method page
Stop button and `stop_job` do that.

Shutdown: `aboutToQuit` → `assistant.shutdown()` cancels as above with the bounded wait, before
`Job.stop()` runs (connection order is made explicit in `PyBackend.__init__`, not left to signal
order).

---

## 10. Threading notes

Qt object affinity keeps commands on the main thread. What runs there is the same work the GUI
does today when the user clicks (file parse, point-group detection under 300 atoms, scene rebuild,
project save, input generation, process start). Two additions keep it bounded: the loader's size
cap (P9) and `Job.output` tail reads through a bounded ring of the last N bytes instead of joining
every chunk. `Job.stop` keeps its blocking wait (it is what the GUI does) but the tool reports if
it exceeded 10 s. A responsiveness budget of 200 ms per command is measured in tests with the
largest packaged structure and a 50 MB synthetic output.

---

## 11. Panel changes

- **Items model:** `ui_items` is a `QAbstractListModel`; the streaming assistant item is updated in
  place with `dataChanged`, deltas coalesced at ~30 Hz. The panel scrolls on `streamingTextChanged`
  and on new items. `modelName` becomes notifiable and splits into `configuredModel` and
  `answeringModel`.
- **Controls:** Cancel generation (keeps the transcript; visible during streaming, approval and
  execution), Clear conversation (confirms when a turn is live), and the existing Method page Stop.
  Escape cancels an approval card; closing the panel does not cancel anything.
- **Action rows** show previous → new value and a *Show me* button that switches to the page and
  closes the panel, because the panel overlays the sidebar whose values it changes. Docking the
  panel so the page shrinks needs a framework slot and stays a later option.
- **Approval card:** title, effect list, destination folder for runs, Run/Cancel.
- **Navigation:** `navigateRequested(page)` handled in the panel by setting
  `EaGlobals.Vars.appBarCurrentIndex`, then `navigationDone(page)` back to the controller.
- **Markdown:** assistant text renders with `Text.MarkdownText`; links are shown but open nothing
  (`onLinkActivated` is a no-op), image syntax is stripped before rendering so no local or remote
  resource is loaded by the view.
- Wrapper additions: `assistantItems` (model), `assistantState`, `assistantStreamingText`,
  `assistantApproval`, `assistantAnswerApproval(id, allowed)`, `assistantCancel()`,
  `assistantOpenSettings()`, `assistantConfigured`, `assistantAnsweringModel`.

---

## 12. Privacy and security

- **One `OutboundPolicy`** consulted by every producer: the snapshot builder, each read tool, action
  and error text, the summary block, and transcript persistence. Options: `send_engine_output`,
  `send_results`, `offline`. When output sharing is off, `get_job_output` refuses locally and
  `job.message` is reduced to the state label. Paths are rendered with `~` for the home directory.
- **Disclosure once** before the first network turn: a card listing what is sent (structure
  coordinates and labels, calculation and method settings, engine output and results if enabled,
  the conversation) and that turning a switch off later cannot retract what was sent. The card
  offers "Start a clean conversation" when a switch is turned off mid-session.
- **Path policy** (§6.2) for `load_structure`; no other tool takes a path. Reads outside the policy
  are impossible by construction, not by model behaviour.
- **Loader hardening** (P9): size cap, redacted errors.
- **Secret handling** (§4): `Secret` wrapper, no QObject property, redaction test.
- **Prompt injection:** data blocks are labelled; tools are the only effects; gated effects need a
  human; receipts make every effect visible. A test feeds an engine output containing "load
  /etc/passwd" and asserts no read outside the policy and no card for it.

---

## 13. Implementation plan

| Phase | Deliverable | Files |
|---|---|---|
| 0. Backend prerequisites | P1–P10 from §3, each with tests; `cores` decision; electronic-state setters and sidebar controls | `commands.py`, `sample.py`, `logic/sample.py`, `logic/method.py`, `logic/calculations.py`, `logic/engines/*.py`, `job.py`, `results.py`, `project.py`, `py_backend.py`, `Pages/Sample/.../ElectronicState.qml` |
| 1. Contracts | Field registry, `OutboundPolicy`, `ModelPolicy`, `ToolOutcome`, `ActionRecord`, `RunRecord`, `Budgets`; snapshot builder with byte caps; registry-vs-wrapper test | `logic/assistant_registry.py`, `logic/assistant_snapshot.py`, `logic/assistant_policy.py` |
| 2. Harness | Controller state machine, `turn_id`, cancellation, wait-condition dispatch, fake transport for the SDK, no-network tool harness with a fake engine and temp run folder; `AssistantBackend.run_turn` with the stub implementing it (the stub's `reply` stays) | `assistant.py`, `logic/assistant.py`, `tests/` |
| 3. Read-only chat | Settings store and dialog with keyring probing; `ClaudeBackend` streaming without mutating tools (`get_*`, `show_page`); error mapping; privacy filtering; budgets; usage accounting; streaming items model | `assistant_settings.py`, `logic/claude_backend.py`, `AssistantSettingsDialog.qml`, `AssistantPanel.qml`, `BackendWrapper.qml`, `Components/qmldir`, `pyproject.toml` (`[llm]` extra: `anthropic>=1.1,<2`, `keyring`; `network` pytest marker) |
| 4. First mutating tool end to end | `set_atoms_fixed` with its command, receipt, revision check and gate; then the other mutating tools in the same pattern | `logic/assistant_tools.py`, `assistant.py`, `AssistantPanel.qml` |
| 5. Workflow tools | `run_workflow` with preflight, card with destination, `stop_job`, provenance in the snapshot | `logic/assistant_tools.py`, `job.py` |
| 6. Persistence and polish | Opt-in `assistant.json` in the project folder (schema version, atomic write, redaction, corrupt-file handling; actions and approvals rendered as history, never resumed), suggestions from the model, cost display | `assistant.py`, `project.py` |

`anthropic` is an **optional extra** (`pip install EasyQM[llm]`), imported lazily; a plain install
stays lean and offline.

---

## 14. Test matrix

| Area | Test |
|---|---|
| Registry | every settable wrapper value has one entry and one tool field; snapshot bytes identical for identical state; no untrusted string in the facts channel |
| Snapshot cost | largest packaged structure and a 50 MB output stay under the byte caps; main-thread command ≤ 200 ms |
| Validation | every registry field with a value outside its choices → rejected outcome, no exception, no state change; mixed valid/invalid patch applies nothing |
| Effective fields | every accepted `set_method` field changes the generated input file, or is refused as not used by the engine |
| Selection | `set_atoms_fixed([0])` with atoms 0 and 1 selected fixes exactly atom 0; stale revision changes nothing |
| Approval | state changed while waiting → card rebuilt; duplicate, late and timed-out answers are no-ops; denial then re-request → declined; two mutations in one batch after a denial |
| Cancellation | during approval, stalled stream, retry back-off, dispatch wait; then Clear; then Reset; then quit — no stale mutation, no late text, no deadlock |
| Reset ordering | `PyBackend.reset()` with a turn executing leaves no trace |
| Transcript | two turns, several tools: each user message once, snapshot not in history, tool linkage valid; disconnect after a setter, after `run_workflow`, between two tools → receipts kept, run not repeated |
| Disk effects | `Project.save` instrumented for every mutating tool with autosave on and off; writes match the card's effects; scratch destination shown without a project |
| Provenance | run A, change to B, ask "did it converge" → A identified, mismatch stated |
| Files | traversal, symlink/junction escape, UNC, oversized, malformed (redacted error, nothing outbound), duplicate example names |
| Privacy | full request bodies captured before and after each switch; no output, results or quotes after off; injection string in output causes no read and no card |
| Credentials | no keyring backend, locked store, failing write, stale settings copy, invalid Options key with a valid env key; synthetic-secret grep of logs and bodies |
| Request body | pinned SDK serialises the registry tools, `cache_control` placement, per-model fields; answering model recorded on fallback |
| Budgets | iteration, tool-call, wall-clock, token and repeated-call ceilings each produce the outcome line |
| UI | 3000-character stream scrolls and keeps position when scrolled up; model switch updates the header; Cancel keeps the transcript |
| Packaging | built wheel loads the packaged examples and opens the settings dialog |
| Live (opt-in, `network` marker, cost-capped) | the benzene sentence against a fake engine in a temp folder; never discovers a real engine |

---

## 15. Worked trace of the example

User, no project, default workspace (benzene, def2-TZVP, nothing selected):

1. Facts snapshot: page `sample`, revisions `{sample 0, calculations 0, method 0}`, engine ORCA
   6.1.1 found, no calculation selected, job idle. Data block: file name `benzene.xyz`.
2. `load_structure("benzene.xyz")` → resolves to the packaged example; sample revision is 0 since
   the last load, so no replace gate. Outcome `changed`: "Loaded benzene.xyz: C6H6, 12 atoms,
   molecule, D6h; charge 0 → 0, multiplicity 1 → 1; sample revision 1." Action row; viewer reloads.
3. `set_method(basis_set="cc-pVDZ")` → in `basis_set_choices` and effective for ORCA → `changed`:
   "basis_set: def2-TZVP → cc-pVDZ; method revision 1." Sidebar combo updates.
4. `select_calculations(types=["geometry_optimisation"], mode="replace")` → `changed`; one signal.
5. `run_workflow()` → preflight passes → card: "Run workflow · ORCA 6.1.1 · geometry optimisation
   (tight, 100 steps) · B3LYP-D3BJ/cc-pVDZ · C6H6, 12 atoms · **destination: scratch folder
   `~/AppData/Local/Temp/EasyQM/runs/001` (no project created)**". User clicks Run → revisions
   re-checked → `Job.run()` → `RunRecord` 001 → outcome: "Started run 001 in the scratch folder;
   state running." Status bar shows *Running*.
6. Reply: "Loaded benzene (C6H6, D6h), set the basis to cc-pVDZ with B3LYP-D3BJ, selected a
   geometry optimisation and started run 001 with ORCA 6.1.1 in the scratch folder, since no
   project is open. ORCA was already the active engine because the sample is a molecule."
7. Later, after the user changed the basis to def2-SVP: "did it converge?" → `results.run_id` 001,
   `matches_current_state: false`, `stale_reason: "method changed"` → "Run 001 (cc-pVDZ) converged
   in 7 steps; the current method is def2-SVP, which has not been run."

---

## 16. Disposition of the review findings

Both reviews were checked against the working tree before being accepted. IDs: DS = `LLM_INTEG_REVIEW_DS.md`,
R = `LLM_INTEG_REVIEW_GPT.md`.

| Finding | Verified in code | Disposition |
|---|---|---|
| DS01 / R01 untrusted strings in the system channel; `load_structure` too broad; parse errors quote file text | yes (`logic/sample.py` load and error messages) | Accepted: facts/data split (§5.1), path policy (§6.2), loader hardening (P9). R01's "do not use a system message" not taken: the channel is the documented operator channel; provenance is the fix. |
| DS02 / R03 approval not bound to state | yes (`Job.run` reads live parts; no revision counters) | Accepted: revisions (P1), `ActionRecord`, re-check before commit, declined outcome, no re-request (§6–7). |
| DS03 validation is the only defence and fails with `KeyError` | yes (`orca.py` keyword dicts, `job.py` narrow except) | Accepted: validation at the point of use, total adapters, wide except (P4). |
| DS04 / R12 inert fields (`cores`, `keep_trajectory`, HF+dispersion, Raman+analytical) | yes | Accepted: `effective_for` in the registry, `cores` dropped from the tool (P5). |
| DS05 / R06 `setAtomFixed` amplifies to the selection | yes (`sample.py:489`) | Accepted: exact-index command (P3). |
| DS06 / R07 autosave on every setter; no sample dirty flag; scratch runs | yes (`project.py:46`, `_mark_dirty`, `job.py:31`) | Accepted: effects-based gates with autosave folded into approval, batch commands, destination on the card, scratch allowed explicitly (§1, §7). |
| DS07 / R09 no run provenance; edits mid-run | yes (`_relay_results`) | Accepted: `RunRecord`, stale flags, `running_config` (P7, §5.4); mutating tools refused while running (§6.2). |
| DS08 / R04 cancellation, reset ordering, shutdown | yes (`reset()` order) | Accepted: state machine, wait-condition dispatch only, ordered shutdown (§9, P10). |
| DS09 load resets electronic state; no preconditions | yes (`logic/sample.py` load) | Accepted: precondition column, result reports previous/new state. |
| DS10 / R05 transcript ownership; duplicated user message; receipts lost on failure | yes (my pseudocode) | Accepted: three structures, controller commits, receipts survive (§8.3). |
| DS11 / R19 streaming UI contract on current properties | yes (`constant=True`, scroll hooks) | Accepted: items model, in-place updates, notifiable model names (§11). |
| DS12 panel covers the sidebar; Clear is the only cancel | yes | Partially: Cancel generation and *Show me* added (§11). Docking needs a framework slot; stays an option, not a requirement. |
| DS13 / R19 `show_page` cannot navigate | yes | Accepted: `navigateRequested` + acknowledgement (§6.2, §11). |
| DS14 / R12 example values wrong; examples not packaged; sizes off | yes (defaults, enums, `pyproject`) | Accepted: example corrected and marked non-normative; registry is the contract; examples packaged under `Resources/structures`; byte caps. |
| DS15 / R02 privacy switch covers one path | yes | Accepted: `OutboundPolicy`, local refusal, disclosure, clean-conversation offer (§12). |
| DS16 / R17 keyring import ≠ usable store; base64 default | n/a (library behaviour) | Accepted: probe, session-only default, explicit plaintext opt-in, `Secret` wrapper (§4). |
| DS17 / R14 / R15 model compatibility, caching, accounting, trimming | partly (Haiku has no fallback per the API reference) | Accepted: `ModelPolicy`, moving cache breakpoint, three-bucket accounting, group-wise trimming, answering model recorded (§8). |
| DS18 / R18 phase order; stub protocol breaks tests; fake runner hides SDK | yes (`tests/test_py_parts.py` uses `reply`) | Accepted: phases reordered, `reply` kept, pinned SDK with a fake transport test, `network` marker (§13–14). |
| DS19 `anthropic` as hard dependency | yes | Accepted: `[llm]` extra. |
| DS20 snapshots accumulate; `page` stale in turn | yes | Accepted: snapshot not committed, rebuilt per request; tool results carry page and revisions (§5.3). |
| DS21 / R13 `save_project` over-promises | yes (`as_dict`) | Accepted: scoped result text; serialisation stays a non-goal. |
| DS22 / R15 no per-turn request bound | yes | Accepted: budgets (§8.4). |
| R08 cross-field validation (charge/multiplicity/reference, spacing vs grid) | yes | Accepted: validated together in P6; spacing xor grid in `set_method`. |
| R10 main-thread work can freeze the GUI | yes, but it is the GUI's own cost today | Partially: output ring buffer and size cap added; parse and symmetry stay on the main thread as the GUI does them (§10). |
| R11 setters return `None`; no outcome contract | yes | Accepted: `CommandOutcome` (P2); scoped signal capture is small, as DS notes. |
| R14 "runner guidance recommends a manual loop for approval" | no: the current SDK guidance says gates work inside tool functions or via the per-turn hooks | Declined; the runner stays, and phase 2 prototypes the gate lifecycle before the mutating tools land. |
| R16 regex over output; unbounded ranges | yes | Accepted: literal `contains`, caps on lines, bytes and count (§6.2). |
| R19 Markdown links/images; project boundary; persistence schema | yes | Accepted (§11, §13 phase 6). |
| DS §6 contradictions 1–7 | yes | Resolved by all-or-nothing patches, effects-based gates, scratch disclosure, registry as the inventory, a separate Verify worker, `run_turn` with optional tools, receipts surviving failure. |

---

## 17. Implementation notes (revisions 3 and 4)

The code follows revisions 2 and 3 of this document. Where it is simpler, the simplification was
chosen on YAGNI/KISS grounds; where it differs for correctness, the sections above are updated.

### 17.1 Where things live

| Design element | Code |
|---|---|
| Field registry, snapshot (facts/data), tools, validation, gates, `Outcome`/`Action` | `Backends/Py/workspace.py` |
| Turn loop, model policy, system prompt, error messages | `Backends/Py/logic/claude_backend.py` |
| Offline stub (reads the same snapshot) | `Backends/Py/logic/assistant.py` |
| Controller: history, items, approvals, cancellation, worker thread | `Backends/Py/assistant.py` |
| Key storage, options, verify | `Backends/Py/assistant_settings.py` |
| Revisions | kept by `Workspace`, counted from the parts' change signals |
| Run provenance | `Job.record` and `job.configuration()`; `PyBackend` marks an applied optimised geometry |
| Panel, settings dialog, editable charge/multiplicity | `AssistantPanel.qml`, `AssistantSettingsDialog.qml`, `ElectronicState.qml` |
| Optional dependencies | `pip install EasyQM[llm]` (`anthropic>=1.1,<2`, `keyring`) |
| Tests | `tests/test_assistant.py` (fake Anthropic client, fake engine, no network); fakes shared in `tests/fakes.py` |

### 17.2 Corrections to revision 2

- **Snapshot as a committed turn-scoped system message** (§5.3), not rebuilt per request: rebuilding
  is a history edit that breaks preserved thinking on Opus 5.5.
- **No trimming** (§8.4), for the same reason.
- **Home folder redaction resolves the path first**, so Windows short names (`C:\Users\ABCDEF~1`)
  in the temp folder are recognised.
- **Atom editing, the cell, the view and the project details have tools** (§6.2, revision 4).
  Revision 2 deferred atom editing and left the view out, so "click Add atom" or "show the
  Z-matrix" could not be done. The sample part gained `add_atom`, `remove_atoms`,
  `set_atom_positions`, `set_cell_parameters`, `set_zmatrix_value` and `select_atoms`, which
  raise their errors; the GUI slots now call them.
- **Excited states are a calculation like the others**: `select_calculations` takes
  `excited_states` (refused for a crystal, which the snapshot lists under
  `calculations.unavailable`), and `set_calculation_options` an `excited_states` group (method
  `tddft` or `eom_ccsd`, number of states, TDA, triplets, orbital counts, frozen core) from the
  same registry as the sidebar. Combinations ORCA refuses are checked by the adapter's
  `excited_states_problem`, for the GUI's run and the assistant alike; results carry the
  transitions.
- **The patch tools are not strict** (§6.1): with them strict, the strict tools had 30 optional
  parameters and the API refused every request (limit 24).
- **`describe_error` does not import the SDK**: an SDK error implies the SDK is already imported,
  and the import took seconds on the worker.

### 17.3 Simplifications

- **Manual streaming loop instead of the SDK tool runner.** Gating, cancellation, committing and
  the "declined, skip the rest of this step" rule sit in one 60-line loop that a fake client can
  drive in tests. The runner would add a beta dependency and a second place where history is built.
- **No separate commands module.** The registry in `workspace.py` validates a whole patch before
  calling the existing part setters, so patches are all-or-nothing. A few small part methods were
  added where the setters did not fit: `Calculations.set_selection` (one notification, one
  autosave), `Sample.set_atoms_fixed` (exact indices), `Sample.set_electronic_state`,
  `Sample.load_file` (returns its error instead of opening the GUI's error dialog). A multi-field
  `set_method` still emits one change signal per field; method changes do not autosave.
- **A stale approval returns `stale_state` to the model** instead of rebuilding the card; the model
  reads the workspace and asks again, which shows a fresh card.
- **Panel items stay a `QVariantList`**, rebuilt only when an item is added. The answer being
  written is a separate `streamingText` property shown as the list footer, so streaming does not
  rebuild the list.
- **`cores` and `keep_trajectory` are not exposed** to the model (no adapter reads them); the GUI is
  unchanged. Memory is offered only for engines with `uses_memory` (ORCA).
- **Disclosure is a one-time chat notice** before the first network turn, not a separate card.
- **Clear is disabled while a turn runs**; Stop (the send button while busy) cancels and keeps the
  conversation.
- **No `Secret` wrapper type.** The key is held in one Python attribute, is never a QML property,
  and is written to the settings file only when the user ticks "remember" without a working
  credential store, as the dialog says.
- **Examples** are resolved from `Resources/structures` and, in a source checkout, the repository
  `examples/` folder. Packaging the examples is left to the packaging work.
- **Not built** (later, when needed): opt-in `assistant.json` conversation persistence, suggestions
  written by the model, a responsiveness benchmark, an opt-in live test against the API.
