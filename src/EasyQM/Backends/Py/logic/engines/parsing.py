# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Helpers the output parsers of all engines share."""

import re
from typing import Optional

NUMBER = r'-?\d+\.\d+(?:[eE][-+]?\d+)?'


def last_float(pattern: re.Pattern, text: str) -> Optional[float]:
    matches = pattern.findall(text)
    return float(matches[-1]) if matches else None


def block(lines: list[str], header: str, row: re.Pattern, start: int = 0) -> list[re.Match]:
    """Rows matching `row` that follow the last line matching `header` at or after `start`.

    Lines between the header and the first row (underlines, column titles) are skipped;
    the block ends at the first line after a row that is not a row.
    """
    title = re.compile(header)
    positions = [i for i in range(start, len(lines)) if title.search(lines[i])]
    if not positions:
        return []
    rows = []
    for line in lines[positions[-1] + 1 :]:
        match = row.match(line)
        if match:
            rows.append(match)
        elif rows:
            break
    return rows
