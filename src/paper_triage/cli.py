"""Minimal local, read-only report CLI contract."""
from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from .reporting import RunReport


def render_report(report: RunReport) -> str:
    """Render an already validated report; this function performs no I/O."""
    return json.dumps(report.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, indent=2)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="paper-triage")
    parser.add_argument("command", choices=("report",), help="read-only local report command")
    parser.parse_args(argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
