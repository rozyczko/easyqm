# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Launch the EasyQM GUI (src/EasyQM/main.py)."""
import runpy
import sys
from pathlib import Path

MAIN = Path(__file__).parent / 'src' / 'EasyQM' / 'main.py'

if __name__ == '__main__':
    sys.path.insert(0, str(MAIN.parent))
    runpy.run_path(str(MAIN), run_name='__main__')
