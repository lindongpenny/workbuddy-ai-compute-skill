#!/usr/bin/env python3
"""Static package validation; no network and no external writes."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.cli import validate_config  # noqa: E402


REQUIRED = (
    "SKILL.md",
    "README.md",
    "config.example.json",
    "references/interface-contract.md",
    "scripts/cli.py",
    "scripts/onboard.py",
    "scripts/apply_workbuddy.py",
    "scripts/check_balance.py",
    "scripts/validate_package.py",
    "adapters/new_api_adapter.py",
    "adapters/workbuddy_adapter.py",
    "tests/test_smoke.py",
)


def main() -> int:
    missing = [path for path in REQUIRED if not (ROOT / path).is_file()]
    if missing:
        print(json.dumps({"ok": False, "missing": missing}, ensure_ascii=False, indent=2))
        return 2
    try:
        config = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    result = validate_config(config)
    result["required_files"] = len(REQUIRED)
    result["network_calls"] = 0
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
