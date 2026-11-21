---
name: workbuddy-ai-compute-bridge
description: Safely onboard a WorkBuddy model through the documented New API rc.48+ user endpoints; create a user key, update models.json, check balance, and render recharge reminders.
metadata:
  version: "1.1.0"
  default_mode: dry-run
---

# WorkBuddy AI 算力自动接入

Use for onboarding a New API compatible account, creating its user key, adding a model to WorkBuddy, checking balance, or preparing low-balance reminders.

## Confirmed package inputs

- The provided user-side API notes specify New API rc.48+ JWT login, registration, account balance, token create/list/reveal, status, redeem, and `/v1/chat/completions` paths.
- Management host: `https://www.lianhuaai.com:8091` (register/login/balance). Inference host: `https://token.lianhuaai.com/v1` (internal verification; the adapter appends `/chat/completions`). The model entry WRITTEN to WorkBuddy uses `https://token.lianhuaai.com/` with NO `/v1`, which is the exact value already verified working in the user's `models.json`. Do not confuse the two: the internal verification URL and the written model URL are intentionally different.
- A live, unauthenticated `GET /api/status` to the management host returned rc.48 (`v1.0.0-rc.48`), `quota_per_unit=500000`, `price=1`, `quota_display_type=CNY`, and registration enabled.
- Model ID is the lowercase `kimi-k3.1-pro`, verified working in the user's live setup. The uppercase `Kimi-K3.1-Pro` from v1.0 does not resolve and MUST NOT be written.
- The verified model entry enables `supportsToolCall`, `supportsImages`, `supportsReasoning`, sets `reasoning.supportedEfforts` to `["high","xhigh"]`, and uses a 1M input context. v1.0's conservative `false` flags and 32768-token input cap were wrong; this package mirrors the working entry.
- New-user ¥10 credit is auto-granted by the site's server-side "new user quota" (confirmed configured on the lianhua site). A one-time redeem code is kept as fallback only. The user API cannot issue arbitrary credit.
- This machine's WorkBuddy config is `~/.workbuddy/models.json`, a JSON array of model objects. Preserve existing entries and make a timestamped backup before updating it.

## Boundaries

- The public status route is verified; the model ID, URL form, capability flags, and credit grant are confirmed from the user's live working setup. Registration, login, and token creation/reveal still execute only under the explicitly confirmed workflow below.
- Never claim an account, credit, key, balance, recharge URL, or local write succeeded without the corresponding response or filesystem result.
- Live onboarding requires `security.allow_live=true` in the private config and `--confirm-key-creation`; creating an account also requires `--create-account --confirm-create-account` (or `--existing-account`). Account/password prompts must not echo passwords.
- Redeeming a one-time code requires `--redeem-code --confirm-redeem`. A billed model test requires `--verify-call --confirm-model-call`.
- Writing WorkBuddy config requires `security.allow_filesystem_write=true` and `--confirm-write`. The script backs up the existing file and adds or updates only the selected model ID.
- Do not print API keys, passwords, JWTs, or Authorization headers. The issued user key belongs in the local WorkBuddy model entry; the login JWT belongs in the local state file.

## Workflow

1. Copy `config.example.json` to a private `config.json`; verify the base URL, model ID, threshold, and target path.
2. Run `python scripts/cli.py --config config.json validate-config`, `python scripts/cli.py --config config.json doctor`, and a `mock-*` command (e.g. `python scripts/cli.py --config config.json mock-onboard`). The `--config` flag belongs BEFORE the subcommand.
3. Explain that registration and API token creation change the provider account. After the user confirms, set `security.allow_live=true` locally and run `python scripts/onboard.py --config config.json --create-account --confirm-create-account --confirm-key-creation`. Use `--existing-account --confirm-key-creation` for an existing account.
4. If a one-time ¥10 code was supplied, pass both `--redeem-code --confirm-redeem` after setting its configured environment variable. The script reports observed balances and never assumes the grant happened.
5. Preview with `python scripts/apply_workbuddy.py --config config.json`. After review, set `security.allow_filesystem_write=true` in the private config and apply using `python scripts/apply_workbuddy.py --config config.json --apply --confirm-write`. Add the two model-test flags only when the user approves a real billable request.
6. Check balance with `python scripts/check_balance.py --config config.json`. After onboarding, offer a recurring balance check (suggested every 6 hours). If `automation_update` is available, create it only after the user agrees. Its prompt should run the check script, notify only when `below_threshold` is true, include `balance_cny` and `topup_url`, and stay quiet otherwise. If that tool is unavailable, ask which scheduler and channel to use. A model-driven scheduled task may fail when the configured model has no remaining quota; give the user the top-up URL as a manual fallback.

Read [references/interface-contract.md](references/interface-contract.md) for endpoint behavior, conversion, and remaining compatibility checks.
