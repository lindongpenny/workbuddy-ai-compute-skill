from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from adapters.new_api_adapter import NewApiAdapter  # noqa: E402
from adapters.workbuddy_adapter import WorkBuddyAdapter, WorkBuddyWriteError  # noqa: E402
from scripts.cli import main, validate_config  # noqa: E402
from scripts.onboard import main as onboard_main  # noqa: E402


class WorkBuddySkillSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8"))
        self.config_path = ROOT / "config.example.json"

    def test_example_config_is_valid_and_live_is_off(self) -> None:
        result = validate_config(self.config)
        self.assertTrue(result["ok"])
        self.assertFalse(self.config["security"]["allow_live"])
        self.assertTrue(any("disabled" in item for item in result["warnings"]))

    def test_mock_onboard_does_not_make_network_request(self) -> None:
        with patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")):
            code = main(["--config", str(self.config_path), "mock-onboard"])
        self.assertEqual(code, 0)

    def test_live_adapter_token_flow_uses_documented_paths_and_prefixes_key(self) -> None:
        adapter = NewApiAdapter(self.config)
        with patch.object(adapter, "_request", side_effect=[
            {"success": True, "data": {}},
            {"success": True, "data": [{"id": 42, "name": "unique-name"}]},
            {"success": True, "data": {"key": "abcdef123456"}},
        ]) as request:
            result = adapter.create_user_key("jwt", "9", token_name="unique-name")
        self.assertEqual(result["api_key"], "sk-abcdef123456")
        calls = [call.args[:2] for call in request.call_args_list]
        self.assertEqual(calls, [
            ("POST", "/api/token/"),
            ("GET", "/api/token/?p=0&size=100"),
            ("POST", "/api/token/42/key"),
        ])

    def test_balance_conversion_uses_status_units(self) -> None:
        adapter = NewApiAdapter(self.config)
        with patch.object(adapter, "user_self", return_value={"quota": 5_000_000, "used_quota": 500_000}), \
             patch.object(adapter, "get_status", return_value={"quota_per_unit": 500_000, "price": 1}):
            result = adapter.balance("jwt", "1")
        self.assertEqual(result["balance_cny"], 10.0)
        self.assertEqual(result["used_cny"], 1.0)

    def test_workbuddy_write_preserves_entries_and_makes_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "models.json"
            target.write_text(json.dumps([{"id": "existing", "name": "Existing"}]), encoding="utf-8")
            self.config["workbuddy"]["config_path"] = str(target)
            self.config["security"]["allow_filesystem_write"] = True
            with patch.dict("os.environ", {"WORKBUDDY_KIMI_API_KEY": "local-test-secret-12345"}):
                adapter = WorkBuddyAdapter(self.config)
                preview = adapter.preview()
                self.assertNotIn("local-test-secret-12345", json.dumps(preview))
                result = adapter.apply(confirm_write=True)
            self.assertTrue(Path(result["backup_path"]).is_file())
            models = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(models[0]["id"], "existing")
            self.assertEqual(models[1]["id"], "kimi-k3.1-pro")
            self.assertEqual(models[1]["apiKey"], "local-test-secret-12345")

    def test_written_entry_matches_verified_live_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "models.json"
            target.write_text(json.dumps([]), encoding="utf-8")
            self.config["workbuddy"]["config_path"] = str(target)
            self.config["security"]["allow_filesystem_write"] = True
            with patch.dict("os.environ", {"WORKBUDDY_KIMI_API_KEY": "sk-test-key"}):
                result = WorkBuddyAdapter(self.config).apply(confirm_write=True)
            entry = json.loads(target.read_text(encoding="utf-8"))[0]
            self.assertEqual(entry["id"], "kimi-k3.1-pro")
            self.assertEqual(entry["name"], "kimi-k3.1-pro")
            self.assertEqual(entry["url"], "https://token.lianhuaai.com/")
            self.assertTrue(entry["supportsToolCall"])
            self.assertTrue(entry["supportsImages"])
            self.assertTrue(entry["supportsReasoning"])
            self.assertEqual(entry["reasoning"]["supportedEfforts"], ["high", "xhigh"])
            self.assertNotIn("maxInputTokens", entry)
            self.assertNotIn("maxOutputTokens", entry)

    def test_workbuddy_write_requires_explicit_confirmation(self) -> None:
        with self.assertRaises(WorkBuddyWriteError):
            WorkBuddyAdapter(self.config).apply(confirm_write=False)

    def test_workbuddy_write_respects_local_write_gate(self) -> None:
        with self.assertRaisesRegex(WorkBuddyWriteError, "allow_filesystem_write"):
            WorkBuddyAdapter(self.config).apply(confirm_write=True)

    def test_onboarding_stays_blocked_until_live_opt_in(self) -> None:
        with patch("builtins.input", side_effect=AssertionError("must not prompt")), \
             patch("urllib.request.build_opener", side_effect=AssertionError("must not connect")):
            code = onboard_main([
                "--config", str(self.config_path), "--create-account", "--confirm-create-account"
            ])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
