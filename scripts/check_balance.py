#!/usr/bin/env python3
"""Query the logged-in user's balance without printing session credentials."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.new_api_adapter import NewApiAdapter, ProviderApiError  # noqa: E402
from scripts.cli import load_config  # noqa: E402
from scripts.onboard import state_path  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check New API balance")
    parser.add_argument("--config", default="config.json")
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        state = json.loads(state_path(config).read_text(encoding="utf-8"))
        adapter = NewApiAdapter(config)
        balance = adapter.balance(state["access_token"], state["user_id"])
        threshold = float(config.get("reminders", {}).get("threshold_cny", 2))
        print(json.dumps({
            **balance,
            "below_threshold": balance["balance_cny"] < threshold,
            "threshold_cny": threshold,
            "topup_url": adapter.recharge_entry(),
        }, ensure_ascii=False, indent=2))
        return 0
    except (OSError, KeyError, ValueError, ProviderApiError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
