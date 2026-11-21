#!/usr/bin/env python3
"""Preview or apply the issued local model key to WorkBuddy models.json."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.workbuddy_adapter import WorkBuddyAdapter, WorkBuddyWriteError  # noqa: E402
from scripts.cli import load_config  # noqa: E402
from scripts.onboard import state_path, write_state  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preview/apply a pending WorkBuddy model entry")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-write", action="store_true")
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        state_file = state_path(config)
        state = json.loads(state_file.read_text(encoding="utf-8"))
        api_key = state.get("api_key")
        if not api_key:
            raise ValueError("No pending user key found in local onboarding state.")
        key_env = config["workbuddy"]["values"].get("api_key_env", "WORKBUDDY_KIMI_API_KEY")
        os.environ[str(key_env)] = str(api_key)
        adapter = WorkBuddyAdapter(config)
        preview = adapter.preview()
        if not args.apply:
            print(json.dumps(preview, ensure_ascii=False, indent=2))
            return 0
        result = adapter.apply(confirm_write=args.confirm_write)
        state.pop("api_key", None)
        write_state(state_file, state)
        print(json.dumps({"ok": True, "preview": preview, "result": result}, ensure_ascii=False, indent=2))
        return 0
    except (OSError, KeyError, ValueError, json.JSONDecodeError, WorkBuddyWriteError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
