#!/usr/bin/env python3
"""Explicitly confirmed New API onboarding for a WorkBuddy model entry."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import secrets
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.new_api_adapter import NewApiAdapter, ProviderApiError  # noqa: E402
from adapters.workbuddy_adapter import WorkBuddyAdapter, WorkBuddyWriteError  # noqa: E402
from scripts.cli import load_config  # noqa: E402


def state_path(config: dict[str, Any]) -> Path:
    value = config.get("new_api", {}).get("state_path") or "~/.workbuddy/suanli-auto-access.json"
    return Path(value).expanduser()


def write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        os.chmod(temp, 0o600)
    except OSError:
        pass
    os.replace(temp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def verify_chat(adapter: NewApiAdapter, api_key: str, model: str) -> bool:
    response = adapter._request(
        "POST",
        adapter._endpoint("chat_completions", "/chat/completions"),
        payload={"model": model, "messages": [{"role": "user", "content": "Reply with OK."}], "max_tokens": 1},
        access_token=api_key,
        base_url=adapter.model_base_url,
    )
    if response.get("error") or not isinstance(response.get("choices"), list) or not response["choices"]:
        raise ProviderApiError("Model test did not return a completion; response details were withheld.")
    return True


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Create/login to a New API account and issue a user key")
    p.add_argument("--config", default="config.json")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--create-account", action="store_true")
    mode.add_argument("--existing-account", action="store_true")
    p.add_argument("--confirm-create-account", action="store_true")
    p.add_argument("--confirm-key-creation", action="store_true")
    p.add_argument("--redeem-code", action="store_true", help="redeem NEW_API_REDEEM_CODE (one-time use)")
    p.add_argument("--confirm-redeem", action="store_true")
    p.add_argument("--verify-call", action="store_true", help="send one billable chat request")
    p.add_argument("--confirm-model-call", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        config = load_config(args.config)
        if not config.get("security", {}).get("allow_live", False):
            raise ValueError("Set security.allow_live=true in your private config after reviewing this provider.")
        if args.create_account and not args.confirm_create_account:
            raise ValueError("Account registration requires --confirm-create-account.")
        if not args.confirm_key_creation:
            raise ValueError("Creating a provider API token requires --confirm-key-creation.")
        if args.redeem_code and not args.confirm_redeem:
            raise ValueError("Redeeming a one-time code requires --confirm-redeem.")
        if args.verify_call and not args.confirm_model_call:
            raise ValueError("A real model call requires --confirm-model-call.")

        adapter = NewApiAdapter(config)
        username = input("New API username: ").strip()
        if not username or len(username) > 64:
            raise ValueError("Username must contain 1–64 characters.")
        password = getpass.getpass("New API password: ")
        if len(password) < 8 or len(password) > 128:
            raise ValueError("Password must contain 8–128 characters.")
        if args.create_account:
            adapter.register(username, password)
        session = adapter.login(username, password)
        session["username"] = username
        session["base_url"] = config["new_api"]["base_url"]
        session["created_by_skill"] = bool(args.create_account)
        state_file = state_path(config)
        write_state(state_file, session)

        balance_before_redeem = adapter.balance(session["access_token"], session["user_id"])
        if args.redeem_code:
            code = os.environ.get(config["new_api"]["test_credit"].get("redeem_code_env", "NEW_API_REDEEM_CODE"), "")
            if not code:
                raise ValueError("Redeem code environment variable is empty; no code was consumed.")
            adapter.redeem_code(session["access_token"], session["user_id"], code)
        balance_after_redeem = adapter.balance(session["access_token"], session["user_id"])

        token_name = "workbuddy-" + secrets.token_hex(5)
        issued = adapter.create_user_key(session["access_token"], session["user_id"], token_name=token_name)
        session.update({"token_id": issued["token_id"], "api_key": issued["api_key"], "token_name": token_name})
        write_state(state_file, session)

        verify = {"attempted": False, "reachable": None}
        if args.verify_call:
            model = str(config["workbuddy"]["values"]["model"])
            verify_chat(adapter, issued["api_key"], model)
            verify = {"attempted": True, "reachable": True}

        key_env = config["workbuddy"]["values"].get("api_key_env", "WORKBUDDY_KIMI_API_KEY")
        os.environ[str(key_env)] = issued["api_key"]
        workbuddy_preview = WorkBuddyAdapter(config).preview()

        balance = adapter.balance(session["access_token"], session["user_id"])
        threshold = float(config.get("reminders", {}).get("threshold_cny", 2))
        output = {
            "ok": True,
            "account": "created" if args.create_account else "existing-account-login",
            "api_key": "issued and stored locally; value redacted",
            "balance": balance,
            "test_credit": {
                "requested_cny": 10,
                "observed_balance_cny_before_redeem": balance_before_redeem["balance_cny"],
                "observed_balance_cny_after_redeem": balance_after_redeem["balance_cny"],
                "redeem_delta_cny": round(
                    balance_after_redeem["balance_cny"] - balance_before_redeem["balance_cny"], 6
                ) if args.redeem_code else None,
                "server_new_user_grant": "not controlled by user API; check observed balance or server admin settings"
            },
            "verify": verify,
            "workbuddy_preview": workbuddy_preview,
            "workbuddy_write": "pending user review; run scripts/apply_workbuddy.py",
            "state_file": str(state_file),
            "topup_url": adapter.recharge_entry(),
            "below_threshold": balance["balance_cny"] < threshold,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, ProviderApiError, WorkBuddyWriteError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
