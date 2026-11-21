"""New API rc.48 user-side adapter. No administrator credential is used."""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


class PendingIntegrationError(RuntimeError):
    """Raised when a required provider setting is not confirmed."""


class ProviderApiError(RuntimeError):
    """Safe provider error that never includes response bodies or credentials."""


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request: Any, response: Any, code: int, msg: str, headers: Any, new_url: str) -> None:
        return None


@dataclass
class NewApiAdapter:
    config: dict[str, Any]

    def __post_init__(self) -> None:
        self.base_url = str(self.config.get("new_api", {}).get("base_url", "")).rstrip("/")
        self.model_base_url = str(self.config.get("new_api", {}).get("model_base_url", "")).rstrip("/")
        for label, value in (("new_api.base_url", self.base_url), ("new_api.model_base_url", self.model_base_url)):
            parsed = urllib.parse.urlparse(value)
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                raise PendingIntegrationError(f"{label} must be a confirmed HTTPS URL.")
        security = self.config.get("security", {})
        self.timeout = max(3, min(int(security.get("timeout_seconds", 15)), 60))
        self.context = ssl.create_default_context()

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        access_token: str | None = None,
        user_id: str | int | None = None,
        base_url: str | None = None,
    ) -> dict[str, Any]:
        url = (base_url or self.base_url).rstrip("/") + "/" + path.lstrip("/")
        headers = {"Accept": "application/json", "User-Agent": "workbuddy-ai-compute-skill/1.0"}
        body = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload).encode("utf-8")
        if access_token:
            headers["Authorization"] = "Bearer " + access_token
        if user_id is not None:
            headers["New-Api-User"] = str(user_id)
        request = urllib.request.Request(url, data=body, headers=headers, method=method.upper())
        try:
            opener = urllib.request.build_opener(
                urllib.request.HTTPSHandler(context=self.context), _NoRedirectHandler()
            )
            with opener.open(request, timeout=self.timeout) as response:
                raw = response.read(2_000_000)
        except urllib.error.HTTPError as exc:
            # Do not surface server bodies: some versions echo submitted fields.
            raise ProviderApiError(f"Provider returned HTTP {exc.code} for {method} {path}.") from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            reason = getattr(exc, "reason", None)
            raise ProviderApiError(
                f"Provider request failed ({type(reason or exc).__name__}); check network and base URL."
            ) from None
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ProviderApiError("Provider returned a non-JSON response.") from None
        if not isinstance(data, dict):
            raise ProviderApiError("Provider returned an unexpected response shape.")
        return data

    def _endpoint(self, name: str, default: str) -> str:
        configured = self.config.get("new_api", {}).get("endpoints", {}).get(name)
        return str(configured or default)

    @staticmethod
    def _data(response: dict[str, Any]) -> dict[str, Any]:
        data = response.get("data", {})
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _ensure_success(response: dict[str, Any], operation: str) -> None:
        if response.get("success") is False or response.get("ok") is False:
            code = response.get("code")
            raw_code = str(code) if code is not None else "provider-rejected"
            safe_code = raw_code[:40] if all(ch.isalnum() or ch in "_.-" for ch in raw_code) else "provider-rejected"
            raise ProviderApiError(f"{operation} failed ({safe_code}); provider details were withheld.")

    def get_status(self) -> dict[str, Any]:
        response = self._request("GET", self._endpoint("status", "/api/status"))
        self._ensure_success(response, "status")
        return self._data(response)

    def register(self, username: str, password: str) -> dict[str, Any]:
        response = self._request("POST", self._endpoint("register", "/api/user/register"), payload={
            "username": username,
            "password": password,
            "password2": password,
        })
        self._ensure_success(response, "register")
        return {"registered": True}

    def login(self, username: str, password: str) -> dict[str, Any]:
        response = self._request("POST", self._endpoint("login", "/api/user/login"), payload={
            "username": username,
            "password": password,
        })
        self._ensure_success(response, "login")
        data = self._data(response)
        user = data.get("user") if isinstance(data.get("user"), dict) else {}
        access_token = data.get("access_token")
        user_id = user.get("id", data.get("id"))
        if not access_token or user_id is None:
            raise ProviderApiError("Login response did not contain the rc.48 access_token and user id.")
        return {"access_token": str(access_token), "user_id": str(user_id)}

    def user_self(self, access_token: str, user_id: str | int) -> dict[str, Any]:
        response = self._request("GET", self._endpoint("user_self", "/api/user/self"), access_token=access_token, user_id=user_id)
        self._ensure_success(response, "user self")
        return self._data(response)

    def create_user_key(
        self,
        access_token: str,
        user_id: str | int,
        *,
        token_name: str,
    ) -> dict[str, str]:
        response = self._request(
            "POST",
            self._endpoint("create_token", "/api/token/"),
            payload={
                "name": token_name,
                "expired_time": -1,
                "remain_quota": 0,
                "unlimited_quota": True,
            },
            access_token=access_token,
            user_id=user_id,
        )
        self._ensure_success(response, "token create")
        listing = self._request(
            "GET", self._endpoint("list_tokens", "/api/token/?p=0&size=100"), access_token=access_token, user_id=user_id
        )
        self._ensure_success(listing, "token list")
        data = listing.get("data", [])
        if isinstance(data, dict):
            items = data.get("items", data.get("tokens", []))
        else:
            items = data
        matches = [item for item in items if isinstance(item, dict) and item.get("name") == token_name]
        if len(matches) != 1 or matches[0].get("id") is None:
            raise ProviderApiError("Could not uniquely identify the newly created token; inspect account manually.")
        token_id = urllib.parse.quote(str(matches[0]["id"]), safe="")
        revealed = self._request(
            "POST", self._endpoint("reveal_token", "/api/token/{id}/key").format(id=token_id),
            payload={}, access_token=access_token, user_id=user_id
        )
        self._ensure_success(revealed, "token reveal")
        key = self._data(revealed).get("key")
        if not isinstance(key, str) or not key:
            raise ProviderApiError("Token reveal response did not contain a key.")
        return {"token_id": str(matches[0]["id"]), "api_key": key if key.startswith("sk-") else "sk-" + key}

    def balance(self, access_token: str, user_id: str | int) -> dict[str, Any]:
        account = self.user_self(access_token, user_id)
        status = self.get_status()
        try:
            quota = float(account["quota"])
            used_quota = float(account.get("used_quota", 0))
            quota_per_unit = float(status["quota_per_unit"])
            price = float(status["price"])
        except (KeyError, TypeError, ValueError):
            raise ProviderApiError("Balance conversion fields are missing or invalid.") from None
        if quota_per_unit <= 0 or price < 0:
            raise ProviderApiError("Provider returned invalid quota conversion values.")
        return {
            "balance_cny": round(quota / quota_per_unit * price, 6),
            "used_cny": round(used_quota / quota_per_unit * price, 6),
            "raw_quota": quota,
            "raw_used_quota": used_quota,
            "group": account.get("group"),
        }

    def redeem_code(self, access_token: str, user_id: str | int, code: str) -> dict[str, Any]:
        response = self._request(
            "POST", self._endpoint("topup", "/api/user/topup"), payload={"key": code}, access_token=access_token, user_id=user_id
        )
        self._ensure_success(response, "redeem")
        return {"redeemed": True}

    def recharge_entry(self) -> str:
        return self.base_url + "/console/topup"


class MockNewApiAdapter:
    """Deterministic local responses for tests and dry-run demonstrations."""

    def __init__(self, config: dict[str, Any]):
        self.config = config

    def authorize_account(self, request: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": True,
            "status": "authorized",
            "provider_request_id": "mock-authorize-0001",
            "account_id": "mock-account",
        }

    def issue_test_credit(self, request: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": True,
            "status": "pending-admin-grant",
            "requested_amount": 10,
            "currency": "CNY",
            "message": "A ¥10 welcome grant requires server-side new-user quota or a redemption code.",
        }

    def issue_user_key(self, request: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "status": "issued", "user_key": "mock_****_key"}

    def get_balance(self, request: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "status": "active", "balance": {"amount": 10, "currency": "CNY"}}

    def get_recharge_entry(self, request: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "status": "active", "recharge_url": "https://example.invalid/mock-recharge"}
