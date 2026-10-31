# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Qt-free method state: level of theory, SCF and run settings (GENERAL_DESIGN.md, 3.4).

`Method` holds values only. Which values are permitted is the engine adapter's business
(`engines.base.Capabilities`), so one `Method` can later be checked against several engines.
"""

from dataclasses import dataclass


@dataclass
class Method:
    family: str = 'DFT'
    functional: str = 'B3LYP'
    dispersion: str = 'D3BJ'
    basis_set: str = 'def2-TZVP'
    auxiliary_basis: str = 'def2/J'
    reference: str = 'RKS'
    solvation: str = 'none'
    scf_convergence: str = 'tight'
    scf_max_iterations: int = 125
    integration_grid: str = 'DefGrid2'
    stability_check: bool = False


@dataclass
class RunSettings:
    cores: int = 1  # serial runs only in PoC1
    memory_gb: int = 16
