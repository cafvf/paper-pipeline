"""Secret-safe text redaction for logs and reports."""

from __future__ import annotations

import re
from collections import Counter

# Match both header-style (``token=value``) and JSON-style (``"token": "value"``)
# credentials.  The value is always replaced as a whole, so raw payload fragments
# cannot leak through a log or report.
_PATTERNS = (
    (
        "authorization",
        re.compile(
            r'''(?ix)(["']?authorization["']?\s*[:=]\s*)(?:bearer\s+)?(?:"[^"]*"|'[^']*'|[^\s,;}]+)'''
        ),
    ),
    (
        "token",
        re.compile(
            r'''(?ix)(["']?(?:token|api[_-]?key|secret|password)["']?\s*[:=]\s*)(?:"[^"]*"|'[^']*'|[^\s,;}]+)'''
        ),
    ),
)


def redact_text(value: str) -> tuple[str, dict[str, int]]:
    """Redact credential values before text is included in a log or report."""

    counts: Counter[str] = Counter()
    for category, pattern in _PATTERNS:

        def replace(match: re.Match[str], category: str = category) -> str:
            counts[category] += 1
            return f"{match.group(1)}[REDACTED]"

        value = pattern.sub(replace, value)
    return value, dict(counts)
