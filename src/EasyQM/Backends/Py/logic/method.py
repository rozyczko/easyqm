# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Qt-free method state: level of theory, SCF and run settings (GENERAL_DESIGN.md, 3.4).

`Method` holds values only. Which values are permitted is the engine adapter's business
(`engines.base.Capabilities`), so one `Method` can later be checked against several engines.
"""

import math
from dataclasses import dataclass
from dataclasses import field
from typing import Optional

from .geometry import norm


@dataclass
class KPoints:
    """Monkhorst-Pack sampling of a crystal: from a spacing, unless a grid is set by hand.

    The spacing follows CASTEP's kpoint_mp_spacing: it is compared with reciprocal vectors
    without the 2π factor, so 0.1 Å⁻¹ gives cubic NaCl (a = 5.64 Å) a 2 × 2 × 2 grid.
    """

    spacing: float = 0.1  # Å⁻¹
    grid: Optional[tuple[int, int, int]] = None  # set by hand; None follows the spacing

    def for_cell(self, cell) -> tuple[int, int, int]:
        """The grid set by hand, else the one the spacing gives this cell."""
        return self.grid or kpoint_grid(cell, self.spacing)


def kpoint_grid(cell, spacing: float) -> tuple[int, int, int]:
    """The smallest grid whose points are at most `spacing` apart along each reciprocal vector."""
    return tuple(max(1, math.ceil(norm(vector) / spacing - 1e-9)) for vector in cell.reciprocal)


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
    occupations: str = 'smearing'  # plane-wave engines: 'smearing' (metals) or 'fixed' (insulators)
    kpoints: KPoints = field(default_factory=KPoints)  # crystals only


@dataclass
class RunSettings:
    cores: int = 1  # serial runs only in PoC1
    memory_gb: int = 16


def reference_problem(reference: str, multiplicity: int) -> str:
    """Why this reference cannot describe this multiplicity, or '' if it can."""
    if multiplicity > 1 and reference == 'RKS':
        return f'Multiplicity {multiplicity} needs an open-shell reference, not RKS.'
    return ''


def describe(method: Method, capabilities) -> str:
    """Short level-of-theory label with display names, e.g. 'B3LYP-D3(BJ)/def2-TZVP'."""
    if method.family == 'HF':
        theory = 'HF'
    else:
        theory = dict(capabilities.functionals).get(method.functional, method.functional)
        if method.dispersion != 'none':
            theory += '-' + dict(capabilities.dispersions).get(method.dispersion, method.dispersion)
    return f'{theory}/{dict(capabilities.basis_sets).get(method.basis_set, method.basis_set)}'
