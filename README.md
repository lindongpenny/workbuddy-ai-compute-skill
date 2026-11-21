# WorkBuddy AI 算力自动接入 Skill V1.1.0

本包按机房提供的 New API rc.48 用户接口说明实现开户、登录、用户专属 Key、余额查询和充值入口，并按本机 WorkBuddy `models.json` 格式添加模型条目。

用户管理请求发往 `https://www.lianhuaai.com:8091`；skill 内部连通性验证使用 `https://token.lianhuaai.com/v1`（ adapter 自动拼接 `/chat/completions` ）；**写入 WorkBuddy 的模型地址是 `https://token.lianhuaai.com/`（不带 `/v1`）**，这是用户现有配置里已验证可用的写法。

## 状态与边界

公开状态接口只读检查返回 `v1.0.0-rc.48`、`quota_per_unit=500000`、`price=1`、币种 CNY、注册开启。写入的模型条目完全对齐用户机器上已跑通的 `kimi-k3.1-pro` 配置：

- 模型 ID 小写 `kimi-k3.1-pro`；大写 `Kimi-K3.1-Pro` 不解析，禁止写入。
- 能力开关 `supportsToolCall` / `supportsImages` / `supportsReasoning` 全部为 `true`。
- `reasoning.supportedEfforts = ["high", "xhigh"]`。
- 不写 `maxInputTokens` / `maxOutputTokens` 字段，与现有可用条目完全一致；WorkBuddy 走模型原生的 100 万上下文。V1.0 写死 32768 输入上限会砍掉模型能力，已移除。
- ¥10 新用户额度由机房后台“新用户配额”自动到账（已确认配置）；用户侧接口不能自行发放额度，兑换码仅作兜底。

仍需用户显式确认后才执行的动作：开户/登录、创建与揭示 Key、真实计费调用、写本地 `models.json`。默认命令只做本地校验、模拟和预览。真实写入前会为现有配置生成时间戳备份。

## 文件

```text
SKILL.md                         skill 入口与操作边界
README.md                        安装、使用与限制
config.example.json              示例配置，不含密钥
references/interface-contract.md New API / WorkBuddy 对接说明
adapters/new_api_adapter.py      rc.48+ 用户接口适配器
adapters/workbuddy_adapter.py    WorkBuddy models.json 备份与写入
scripts/cli.py                   校验、doctor、模拟和预览
scripts/onboard.py               需确认的开户、Key 创建和配置流程
scripts/apply_workbuddy.py       WorkBuddy 模型预览与确认写入
scripts/check_balance.py         使用本地会话状态查余额
scripts/validate_package.py      包结构检查
tests/test_smoke.py              无网络测试（9 项）
```

要求 Python 3.10+，仅使用标准库。

## 安装与本地校验

```powershell
Expand-Archive .\workbuddy-ai-compute-skill-v1.1.0.zip .\workbuddy-skill
Set-Location .\workbuddy-skill\workbuddy-ai-compute-skill-v1.1.0
Copy-Item config.example.json config.json
python scripts/cli.py --config config.json validate-config
python scripts/cli.py --config config.json doctor
python scripts/cli.py --config config.json mock-onboard
python scripts/validate_package.py
python -m unittest discover -s tests -v
```

> 注意 `--config` 必须放在子命令**前面**。V1.0 文档里写成 `validate-config --config config.json`，会被 argparse 判为无法识别的参数并报错，V1.1.0 已修正。

检查私有配置里的地址、模型 ID 和充值阈值后，把 `security.allow_live` 本地设为 `true`。创建新账户：

```powershell
python scripts/onboard.py --config config.json --create-account --confirm-create-account --confirm-key-creation
python scripts/apply_workbuddy.py --config config.json
python scripts/apply_workbuddy.py --config config.json --apply --confirm-write
```

脚本会交互读取用户名和密码，密码不回显；创建账号和 API Key 都要求显式确认。创建 Key 后先显示脱敏的 WorkBuddy 预览，并把待写 Key 保存在本机状态文件。检查预览后再运行 `apply_workbuddy.py --apply --confirm-write`。成功写入后状态文件中的待写 Key 会移除。若已有账户，改用 `--existing-account --confirm-key-creation`。不要将 `config.json`、状态文件或密钥加入 ZIP、Git 或聊天。

本地写入前还需在私有 `config.json` 中将 `security.allow_filesystem_write` 设为 `true`。

## ¥10 额度

新用户额度由站长后台“新用户配额”设置，单位是 quota；换算公式为 `人民币 = quota / quota_per_unit * price`。本站已确认自动到账（¥10 对应 5,000,000 quota）。用户侧接口不能自行发放额度。若需一次性兑换码兜底：

```powershell
$env:NEW_API_REDEEM_CODE = '<本机粘贴兑换码>'
python scripts/onboard.py --config config.json --existing-account --confirm-key-creation --redeem-code --confirm-redeem
```

脚本只报告观测到的实际余额，不假定赠额一定发生。

## WorkBuddy 模型字段

本机 `models.json` 是 JSON 数组。本包写入的模型对象（已对齐用户现有可用配置）：

```json
{
  "id": "kimi-k3.1-pro",
  "name": "kimi-k3.1-pro",
  "vendor": "Custom",
  "url": "https://token.lianhuaai.com/",
  "apiKey": "[本地用户 Key]",
  "supportsToolCall": true,
  "supportsImages": true,
  "supportsReasoning": true,
  "useCustomProtocol": false,
  "reasoning": { "supportedEfforts": ["high", "xhigh"] }
}
```

匹配到同一 `id` 时只更新该条，否则新增一条；更新前备份原文件。地址 `url` 保留用户现有写法（不带 `/v1`，带尾斜杠）。不写 token 上限字段，与现有可用条目逐字段一致。写入完成后是否热加载取决于当前 WorkBuddy 版本；若模型列表未刷新，可手动重载或重启客户端。

## 本地凭据

- 开户登录凭据由终端交互读取，不落盘。
- rc.48 登录 JWT 存在 `~/.workbuddy/suanli-auto-access.json`，供余额查询使用；脚本尽力将权限限制为当前用户。
- 用户 Key 写入 WorkBuddy 模型配置，不在标准输出显示。
- 本包不需要管理员密钥。

成功接入后可设置周期余额提醒，建议每 6 小时检查一次。提醒只在低于 `threshold_cny` 时发送，并带上充值入口。若当前 WorkBuddy 环境提供 `automation_update`，由 Skill 在征得用户同意后创建；否则需用户选择 Windows 任务计划程序等执行器及通知渠道。脚本自身不假称已经创建了计划任务。

余额查询：

```powershell
python scripts/check_balance.py --config config.json
```

充值入口根据管理站点地址生成 `<management_base_url>/console/topup`，需登录后使用。

## 修订历史

| 版本 | 日期 | 修订内容 | 主要影响 |
|---|---|---|---|
| 1.0.0 | 2026-11-12 | 初版：New API rc.48 开户/Key/余额/充值链路 | 基于未验证的保守占位配置 |
| 1.1.0 | 2026-11-21 | 模型名改小写 `kimi-k3.1-pro`；写入地址去掉 `/v1`；三个能力开关开为 true；补 `reasoning.supportedEfforts`；移除 V1.0 写死的 token 上限字段以匹配现有配置；确认 ¥10 自动到账；修 `cli.py --config` 参数顺序；版本号校验兼容 1.1.0；新增配置对齐测试 | 写入的模型条目与用户现有跑通配置逐字段一致，不会降级或产生重复条目 |
