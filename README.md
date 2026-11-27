# easyqm
EasyApp application for running and visualizing quantum chemical calculations

## Engines

| Engine | Runs | Calculations |
|---|---|---|
| ORCA | molecules | single point, optimisation, frequencies with IR and Raman, excited states |
| Quantum ESPRESSO | crystals | single point, optimisation, Γ phonons, band structure, DOS |
| CASTEP | crystals | single point, optimisation, Γ phonons (with IR intensities when analytical), band structure, DOS |

The Method page shows one card per engine. A crystal runs with Quantum ESPRESSO or CASTEP:
click a card to choose. The choice is remembered on this computer, as are the executables
(*Configure paths…*). Options only one engine has are under *Extra controls →
Engine-specific*.

### CASTEP

EasyQM runs CASTEP 26 serially (checked on 26.11). Pseudopotentials are generated on the fly,
so no files are needed.

1. **Install.** If `castep.serial` is not on `PATH`, choose it with *Configure paths…* on the
   CASTEP card. A MinGW build for Windows needs its runtime DLLs next to the executable:
   copy `libgfortran-5.dll`, `libgcc_s_seh-1.dll`, `libgomp-1.dll`, `libwinpthread-1.dll`,
   `libfftw3-3.dll` and `libopenblas.dll` from `C:\msys64\ucrt64\bin`. Without them the card
   says `does not start (0xC0000135: a DLL it needs was not found)`.
2. **Engine-specific options.**
   - *Pseudopotentials*: `Automatic` takes C19, or the norm-conserving NCP19 when the
     frequencies can be computed analytically with it. You can also choose a library, or a
     folder of potential files from `PSPOT_DIR` that has one file for every element of the
     sample; those files are copied into the run folder.
   - *Basis precision*: CASTEP's cut-off energy, from coarse to extreme (default fine).
3. **Frequencies.** The Frequencies group on the Calculations page says how they will be
   computed. Analytical (DFPT) frequencies with IR intensities need fixed occupations and no
   dispersion other than TS or G06. Otherwise CASTEP uses finite displacement, without IR.
   CASTEP refuses frequencies on a geometry that is not relaxed, so tick Optimisation as well.

Each job is one run folder: `job` (single point or optimisation) runs first, then
`job-phonon`, `job-bands` and `job-dos`, each continuing from `job.check`. `job.out` holds
every run's log.

**Examples** (in `examples/CIF`, a few seconds to a minute each with *Basis precision*
coarse):

- `Si_primitive.cif`, fixed occupations, Band structure and Density of states: the
  textbook band structure, with an indirect gap.
- `NaCl_primitive.cif`, fixed occupations, Frequencies: the IR-active TO mode at about
  185 cm⁻¹, with its IR intensity.
- `Si_primitive.cif` with smearing and D3: the same Frequencies are finite displacement,
  and the Frequencies group says why.

Design, decisions and limits: `MD/ADD_CASTEP_DESIGN.md`.

## Assistant

The assistant panel (the robot button in the app bar, or Ctrl+Shift+A) answers questions about
the workspace and can change it. It has two optional parts:

| Extra | Install | Adds |
|---|---|---|
| `llm` | `pip install "EasyQM[llm]"` | Answers by Claude, with an Anthropic API key, `ANTHROPIC_API_KEY` or an `ant auth login` profile. Without it, an offline assistant answers. |
| `voice` | `pip install "EasyQM[voice]"` | Speech: talk to the assistant, and hear its answers. |

### Speech

Turn it on in the assistant settings (the gear in the panel header), under *Speech*:

- **Talk to the assistant.** Hold the microphone button beside Send, or Ctrl+Space in the input
  box, and speak. Release it to stop. The text appears in the input box and is sent after a
  moment; type or press Esc to correct it first.
- **Read answers aloud.** Answers are read with the system's voices. Talking, sending a new
  question, Esc or the speaker button stops the reading.

Speech is recognised on this computer: the recording is not sent or kept, only its text is sent,
as typed text would be. The first use downloads the speech model (about 140 MB); the settings
dialog shows where it goes. Recognition is English only for now. Design and limits:
`MD/LLM_INTEG_DESIGN.md`, §18.
