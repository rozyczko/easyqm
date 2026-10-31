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
