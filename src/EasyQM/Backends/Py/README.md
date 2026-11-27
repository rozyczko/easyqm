# Python backend

The code in this folder is the Python backend serving the QML GUI, laid out as in
EasyReflectometryApp.

## Folder root

The modules in the root define the API of the backend, one class per GUI page (`Project`,
`Sample`, `Calculations`, `Method`, and `Results` for the Summary page). They are `QObject`s exposing
`Property`/`Slot`/`Signal` and hold no logic of their own: every method delegates to a class
in `logic/`. `helpers.py` holds the helpers the proxies share (`apply` for change-only
setters, `choices` for combo-box models, `to_local_path` for file dialog URLs). `job.py` is
the one part that is not a page: it runs the current workflow for the Run card of the Method
page and streams the engine output. `PyBackend` collects the parts and wires the relays
between them:

| Source | Target | Effect |
|---|---|---|
| `sample.externalSampleChanged` | `project.setSampleName` | formula and atom count on the Project card and status bar |
| `calculations.externalSelectionChanged` | `project.setCalculations` | names of the ticked calculations |
| `method.engineChanged` | `project.setEngine` | engine name |
| `method.engineChanged` | `job.set_executable` | the detected executable, or none |
| `sample.externalSampleChanged` | `method.set_sample` | the cell and elements: the engine for a molecule or a crystal, and the engine options that cover the elements |
| `calculations.selectionChanged`, `calculations.frequenciesChanged` | `method.frequenciesNoteChanged` | the line on how the engine computes frequencies |
| `project.createdChanged`, `project.locationChanged` | `job.set_root_folder` | runs go into `<project>/runs/` once the project exists |
| `job.stateChanged` | `project.setStatus` | running, completed, failed, stopped |
| `job.stateChanged` | `results.clear` / `results.set_results` | Summary results: cleared when a job starts, read by the job's adapter (`read_results`) from its output and run folder when it ends |

The GUI reaches the backend only through `Gui/Globals/BackendWrapper.qml`.

The assistant panel has parts of its own (design: `MD/LLM_INTEG_DESIGN.md`):

- `assistant.py` is the chat controller.
- `assistant_settings.py` holds its settings and the API key.
- `workspace.py` is what the model sees of the other parts and the tools it changes them with.
- `voice.py` is speech: push-to-talk recognised on this computer, and answers read aloud.

Speech is the optional `voice` extra; the design document's §18 describes it.

## `logic/` folder

Plain Python, no PySide. This is where the project state, the sample, the calculation
catalogue and options, the method settings, and the engine adapters live until they are
extracted into a Qt-free library package.

`logic/engines/` holds one adapter per quantum-chemistry code (`base.EngineAdapter`): ORCA
(`orca.py`), Quantum ESPRESSO (`quantum_espresso.py`) and CASTEP (`castep.py`), each with an
`*_output.py` reader. An adapter knows how to detect its executable, which choices it offers to
the Method page (`Capabilities`), the options only it has (`EngineOption`, shown in the Extra
controls' Engine-specific group), how to write the input for a workflow, the steps the runner
takes, the environment of its processes, and how to tell from the output whether each step and
the job succeeded. Every hook has a default that fits an engine writing one log to standard
output, so an adapter overrides only what its engine does differently; CASTEP overrides most
of them, because it writes its log to a file and exits with code 0 after a failure.

`logic/results.py` is the engine-agnostic results schema that an adapter's `parse()` fills
(`engines/orca_output.py` for ORCA); `results.py` in the folder root formats it for the
Summary page. `logic/kpath.py` chooses the high-symmetry path of a band structure from the
lattice of the cell.

`logic/claude_backend.py` runs one assistant turn with the model, and `logic/assistant.py` is
the offline assistant. `logic/speech.py` is speech without Qt:
- the speech recogniser and the engine terms it is primed with;
- the conversion of a recording into what the recogniser takes;
- an answer written as plain sentences to read aloud.

`logic/runner.py` is the only code that starts a process: numbered run folders, the steps of
a workflow (`Step`) run one after the other with their output written to one file,
incremental reading of that file, and stopping the engine with its child processes. A step
whose program writes its own log file (CASTEP's `<seed>.castep`) gets a header line, and the
runner copies the log into the output file as it grows; a step is judged by its exit code and
by the adapter's `step_succeeded` before the next starts.
