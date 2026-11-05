# Using ASE in EasyQM

This note answers two questions:

1. Should EasyQM use ASE (the Atomic Simulation Environment) to import and export structure files?
2. Should ASE be the common way of calling computational backends?

**Short answer:** use ASE for structure import and export, which
[GENERAL_DESIGN.md](GENERAL_DESIGN.md) §3.2 already plans. Don't use ASE calculators to call
backends: the `EngineAdapter` interface already does that job, at the level the GUI needs.

Checked against ASE 3.29.0.

## 1. Import and export: worth adding

### Cost

- ASE is a 3 MB pure-Python wheel.
- Its dependencies (numpy, scipy, matplotlib) are already installed, because chemcoord pulls in
  pymatgen.
- The import can be lazy, as gemmi's is now.

### What it adds

- **About 100 formats.** These include POSCAR/CONTCAR, CASTEP `.cell`, PDB, SDF/mol, TURBOMOLE
  `coord`, DMol3 `.car`, XSF, cube and Quantum ESPRESSO input.
- **Opening output files.** ASE reads geometries from ORCA, Quantum ESPRESSO, Gaussian, VASP,
  CASTEP, NWChem and FHI-aims output. A user can open the geometry from someone else's run.
- **Export.** EasyQM cannot save a structure today. `ase.io.write` would provide this, including
  saving the optimised geometry.
- **The assistant.** The LLM chat's file tool would get the same formats with no extra work.

### Gaps and catches

- **mol2 and `.mdf` are not supported.** Both are in the design's list of formats. Either drop
  them from the list or give them their own reader.
- **The conversion still needs work:**
  - ASE `Atoms` objects carry no site labels. Labels would be numbered in cell order, as they are
    now.
  - They carry no total charge or multiplicity.
  - Files with several frames need a rule: take the last frame of outputs and trajectories.
  - Structures periodic in only some directions, such as slabs, must be refused. A sample is
    either a molecule or a crystal.

### Proposed shape

- Keep `read_xyz`. It handles labels like `Cl_a` and the extended XYZ `Lattice=` comment.
- Keep the gemmi CIF reader. It refuses partially occupied sites and reads the space group.
- Add one `read_ase` fallback for every other file extension. It converts ASE `Atoms` to atoms and
  a cell, and turns ASE's errors into `ValueError`.
- Add "Save structure as…", built on `ase.io.write`.
- The reader is roughly 40 lines plus tests.

## 2. Calling backends through ASE calculators: no

- **They cover only a small part of the results.** ASE's ORCA calculator and output reader provide
  energy, free energy, forces and dipole, and nothing more. These would all stay in EasyQM's own
  adapters anyway:
  - frequencies and IR intensities;
  - TD-DFT and EOM-CCSD excited states;
  - orbitals and charges;
  - Quantum ESPRESSO bands and gaps.
- **They clash with the Runner.** `calculate()` blocks and launches the engine process itself.
  That rules out:
  - live log streaming;
  - cancelling a job;
  - detecting which step is running;
  - keeping all output in one file;
  - a future remote runner.

  These follow from design rules 3–5 in [GENERAL_DESIGN.md](GENERAL_DESIGN.md) §4.
- **Workflows would get worse.** ASE's optimisers and `Vibrations` replace ORCA's own optimiser
  and analytic frequencies with Python loops of single-point runs. That is slower and less robust.
- **Input writing gains nothing.** ASE's ORCA writer emits `! keywords`, then the `%` blocks, then
  the geometry. All the knowledge about the method and the calculations would still live in the
  adapter.

### Where ASE does help a new backend

ASE can help inside that backend's adapter:

- **Per-code writers** for geometry and k-points: `castep-cell`, `vasp`, `aims`, `espresso-in`.
- **Per-code output readers.**
- **File-IO templates** (`GenericFileIOCalculator`), which separate writing the input and reading
  the results from running the process.

An adapter can call these for the structure part. It keeps its own capabilities, method mapping
and parsing, and the Runner keeps the process. This is a choice to make per backend. CASTEP,
which the design names, is the obvious first candidate: ASE reads both `.cell` and `.castep`
files.

## 3. Later and optional

These are not needed now:

- **`atoms.cell.bandpath()`** gives high-symmetry k-paths, for when Quantum ESPRESSO band
  structures are added. Quantum ESPRESSO jobs use only automatic k-point grids today.
- **`make_supercell`** would support the supercell building the design mentions.
