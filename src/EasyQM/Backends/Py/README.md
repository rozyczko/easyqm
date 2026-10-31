# Python backend

The code in this folder is the Python backend serving the QML GUI, laid out as in
EasyReflectometryApp.

## Folder root

The modules in the root define the API of the backend, one class per GUI page (`Project`,
`Sample`, `Calculations`, `Method`; `Summary` later). They are `QObject`s exposing
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
| `project.createdChanged`, `project.locationChanged` | `job.set_root_folder` | runs go into `<project>/runs/` once the project exists |
| `job.stateChanged` | `project.setStatus` | running, completed, failed, stopped |

The GUI reaches the backend only through `Gui/Globals/BackendWrapper.qml`.

## `logic/` folder

Plain Python, no PySide. This is where the project state, the sample, the calculation
catalogue and options, the method settings, and the engine adapters live until they are
extracted into a Qt-free library package.

`logic/engines/` holds one adapter per quantum-chemistry code (`base.EngineAdapter`). An
adapter knows how to detect its executable, which choices it offers to the Method page
(`Capabilities`), how to write the input for a workflow, the command line, and how to tell
from the output whether the job succeeded.

`logic/runner.py` is the only code that starts a process: numbered run folders, the engine
run as a subprocess with its output written to a file, incremental reading of that file,
and stopping the engine with its child processes.
