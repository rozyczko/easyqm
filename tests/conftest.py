# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
import sys
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication

# The app is run from src/EasyQM (see run.py), so its packages are imported from there.
SRC = Path(__file__).resolve().parents[1] / 'src' / 'EasyQM'
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture(scope='session')
def qcore_application():
    app = QCoreApplication.instance() or QCoreApplication([])
    yield app


# Rock salt in its conventional cell: 2 sites, Fm-3m, 8 atoms. Ionic type symbols, as many
# CIFs give them.
NACL_CIF = """data_NaCl
_cell_length_a 5.6402
_cell_length_b 5.6402
_cell_length_c 5.6402
_cell_angle_alpha 90
_cell_angle_beta 90
_cell_angle_gamma 90
_symmetry_space_group_name_H-M 'F m -3 m'
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
Na1 Na+ 0 0 0
Cl1 Cl- 0.5 0.5 0.5
"""


@pytest.fixture
def nacl_cif(tmp_path) -> Path:
    path = tmp_path / 'NaCl.cif'
    path.write_text(NACL_CIF, encoding='utf-8')
    return path
