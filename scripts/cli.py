#!/usr/bin/env python3
"""Safe local CLI for the WorkBuddy AI compute bridge."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.new_api_adapter import (  # noqa: E402
    MockNewApiAdapter,
    PendingIntegrationError,
)
from adapters.workbuddy_adapter import WorkBuddyAdapter, WorkBuddyWriteError  # noqa: E402


def load_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    data = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("config must be a JSON object")
    return data


def validate_config(config: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if config.get("version") not in {"1.0.0", "1.1.0"}:
        errors.append("version must be 1.0.0 or 1.1.0")
    if config.get("mode") not in {"dry-run", "mock", "live"}:
        errors.append("mode must be dry-run, mock, or live")
    new_api = config.get("new_api")
    if not isinstance(new_api, dict):
        errors.append("new_api must be an object")
        new_api = {}
    credit = new_api.get("test_credit", {})
    if credit.get("amount") != 10 or credit.get("currency") != "CNY":
        errors.append("test_credit must be exactly 10 CNY for this V1 package")
    endpoints = new_api.get("endpoints", {})
    if not isinstance(endpoints, dict):
        errors.append("new_api.endpoints must be an object")
    elif any(not value for value in endpoints.values()):
        warnings.append("one or more New API endpoints are 待适配")
    for url_key in ("base_url", "model_base_url"):
        if not str(new_api.get(url_key, "")).startswith("https://"):
            errors.append(f"new_api.{url_key} must use HTTPS")
    if new_api.get("api_version") != "rc.48+":
        warnings.append("API version is unconfirmed; current adapter implements rc.48+ bearer JWT")
    wb = config.get("workbuddy", {})
    if not isinstance(wb, dict):
        errors.append("workbuddy must be an object")
        wb = {}
    values = wb.get("values", {})
    missing_slots = [slot for slot in ("provider", "base_url", "model") if not values.get(slot)]
    if not values.get("api_key_env"):
        missing_slots.append("api_key_env")
    if missing_slots:
        warnings.append("WorkBuddy model values are missing: " + ", ".join(missing_slots))
    if not wb.get("config_path"):
        warnings.append("WorkBuddy config_path is missing; default is ~/.workbuddy/models.json")
    security = config.get("security", {})
    if not security.get("allow_live", False):
        warnings.append("live onboarding is disabled; set security.allow_live=true after reviewing the target")
    return {"ok": not errors, "errors": errors, "warnings": warnings}


def emit(payload: dict[str, Any], exit_code: int = 0) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return exit_code


def run_action(config: dict[str, Any], args: argparse.Namespace, method: str, request: dict[str, Any]) -> int:
    try:
        result = getattr(MockNewApiAdapter(config), method)(request)
        return emit({"ok": True, "operation": method, "result": result})
    except PendingIntegrationError as exc:
        return emit({"ok": False, "status": "pending-adaptation", "operation": method, "message": str(exc)}, 2)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="WorkBuddy AI compute bridge (dry-run by default)")
    p.add_argument("--config", default="config.json", help="JSON config path")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("validate-config")
    sub.add_parser("doctor")
    for name in ("mock-onboard", "mock-test-credit", "mock-issue-key", "mock-balance", "mock-recharge-entry"):
        sub.add_parser(name)
    apply_cmd = sub.add_parser("apply-workbuddy")
    apply_cmd.add_argument("--apply", action="store_true", help="perform the configured JSON write")
    apply_cmd.add_argument("--confirm-write", action="store_true")
    sub.add_parser("reminder")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        config = load_config(args.config)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return emit({"ok": False, "error": f"config error: {exc}"}, 2)

    if args.command == "validate-config":
        result = validate_config(config)
        return emit(result, 0 if result["ok"] else 2)
    if args.command == "doctor":
        result = validate_config(config)
        result["checks"] = {
            "network": "not attempted",
            "provider": "public rc.48 status verified; authenticated endpoints not tested",
            "workbuddy_write": "not attempted",
            "secret_logging": "redacted by design",
        }
        return emit(result, 0 if result["ok"] else 2)
    if args.command == "mock-onboard":
        return run_action(config, args, "authorize_account", {"purpose": "workbuddy-compute"})
    if args.command == "mock-test-credit":
        return run_action(config, args, "issue_test_credit", {"amount": 10, "currency": "CNY"})
    if args.command == "mock-issue-key":
        return run_action(config, args, "issue_user_key", {"purpose": "workbuddy"})
    if args.command == "mock-balance":
        return run_action(config, args, "get_balance", {})
    if args.command == "mock-recharge-entry":
        return run_action(config, args, "get_recharge_entry", {})
    if args.command == "reminder":
        reminders = config.get("reminders", {})
        return emit({
            "ok": True,
            "status": "disabled" if not reminders.get("enabled") else "rendered-only",
            "schedule": reminders.get("schedule"),
            "timezone": reminders.get("timezone"),
            "channel": reminders.get("channel"),
            "recharge_url": reminders.get("recharge_url"),
            "delivery": "not attempted; scheduler/channel is 待适配",
        })
    if args.command == "apply-workbuddy":
        adapter = WorkBuddyAdapter(config)
        try:
            if not args.apply:
                return emit(adapter.preview())
            return emit(adapter.apply(confirm_write=args.confirm_write))
        except WorkBuddyWriteError as exc:
            return emit({"ok": False, "status": "pending-adaptation", "message": str(exc)}, 2)
    return emit({"ok": False, "error": "unknown command"}, 2)


if __name__ == "__main__":
    raise SystemExit(main())
