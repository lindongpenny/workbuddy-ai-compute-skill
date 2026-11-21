"""WorkBuddy models.json preview and backup-first model entry writer."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


class WorkBuddyWriteError(RuntimeError):
    """Raised when a WorkBuddy write is unsafe or under-specified."""


def redact(value: Any) -> Any:
    if not isinstance(value, str) or not value:
        return value
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}…{value[-4:]}"


class WorkBuddyAdapter:
    def __init__(self, config: dict[str, Any]):
        self.config = config

    def _target(self) -> Path:
        value = self.config.get("workbuddy", {}).get("config_path") or "~/.workbuddy/models.json"
        path = Path(value).expanduser()
        if path.name.lower() != "models.json":
            raise WorkBuddyWriteError("WorkBuddy target must be the confirmed models.json file.")
        if path.exists() and path.is_dir():
            raise WorkBuddyWriteError("WorkBuddy models.json target is a directory.")
        return path

    def _entry(self) -> dict[str, Any]:
        wb = self.config.get("workbuddy", {})
        values = dict(wb.get("values", {}))
        key_env = values.pop("api_key_env", None)
        if key_env:
            values["api_key"] = os.environ.get(str(key_env))
        required = ("provider", "base_url", "api_key", "model")
        missing = [name for name in required if not values.get(name)]
        if missing:
            raise WorkBuddyWriteError(
                "Missing local values for: " + ", ".join(missing)
                + ". Set the API key environment variable before applying."
            )
        model_id = str(values["model"])
        display_name = str(values.get("display_name") or model_id)
        base_url = str(values["base_url"])
        if not base_url.startswith("https://"):
            raise WorkBuddyWriteError("WorkBuddy model URL must use HTTPS.")
        entry: dict[str, Any] = {
            "id": model_id,
            "name": display_name,
            "vendor": str(values["provider"]),
            "url": base_url,
            "apiKey": str(values["api_key"]),
            "supportsToolCall": bool(values.get("supports_tool_call", False)),
            "supportsImages": bool(values.get("supports_images", False)),
            "supportsReasoning": bool(values.get("supports_reasoning", False)),
            "useCustomProtocol": False,
        }
        efforts = values.get("reasoning_supported_efforts")
        if isinstance(efforts, list) and efforts:
            entry["reasoning"] = {"supportedEfforts": [str(item) for item in efforts]}
        if values.get("max_input_tokens") is not None:
            entry["maxInputTokens"] = int(values["max_input_tokens"])
        if values.get("max_output_tokens") is not None:
            entry["maxOutputTokens"] = int(values["max_output_tokens"])
        return entry

    def preview(self) -> dict[str, Any]:
        entry = self._entry()
        safe_entry = dict(entry)
        safe_entry["apiKey"] = redact(safe_entry["apiKey"])
        return {
            "config_path": str(self._target()),
            "model": safe_entry,
            "write": False,
            "status": "preview-only",
        }

    def apply(self, *, confirm_write: bool) -> dict[str, Any]:
        if not confirm_write:
            raise WorkBuddyWriteError("Pass --apply --confirm-write to enable a write.")
        if not self.config.get("security", {}).get("allow_filesystem_write", False):
            raise WorkBuddyWriteError(
                "Set security.allow_filesystem_write=true in the private config before applying."
            )
        target = self._target()
        entry = self._entry()
        current: list[dict[str, Any]] = []
        if target.exists():
            try:
                loaded = json.loads(target.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise WorkBuddyWriteError(f"Cannot safely read existing models.json: {type(exc).__name__}") from None
            if not isinstance(loaded, list) or any(not isinstance(row, dict) for row in loaded):
                raise WorkBuddyWriteError("Existing models.json must be a JSON array of model objects.")
            current = loaded
        existing = next((row for row in current if row.get("id") == entry["id"]), None)
        action = "updated" if existing else "added"
        if existing:
            existing.update(entry)
        else:
            current.append(entry)

        target.parent.mkdir(parents=True, exist_ok=True)
        backup_path: Path | None = None
        if target.exists():
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            backup_path = target.with_name(f"models.json.bak-{stamp}")
            shutil.copy2(target, backup_path)
        fd, temp_name = tempfile.mkstemp(prefix="models-", suffix=".json.tmp", dir=str(target.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(current, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
            os.replace(temp_name, target)
        except Exception:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
            raise WorkBuddyWriteError("WorkBuddy config write failed; inspect the backup before retrying.") from None
        return {
            "config_path": str(target),
            "backup_path": str(backup_path) if backup_path else None,
            "model_id": entry["id"],
            "action": action,
            "write": True,
            "status": "written",
        }
