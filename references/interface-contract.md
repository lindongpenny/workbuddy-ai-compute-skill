# 接口与配置对接说明

## 来源与验证范围

以下接口行为来自机房提供的 `api.md`，其记录称已在 New API rc.18 / rc.48 测试。另对管理地址 `https://www.lianhuaai.com:8091/api/status` 做了只读请求，确认版本 `v1.0.0-rc.48`、`quota_per_unit=500000`、`price=1`、币种显示 CNY、注册开启。模型地址 `https://token.lianhuaai.com/v1/models` 未带凭证返回 401。尚未做注册、登录、Key 操作或认证模型调用。

不使用管理员密钥。开户密码由终端交互读取，登录后 JWT 保存在本机状态文件；用户 `sk-` Key 写进 WorkBuddy 模型条目，任何凭证都不进入 ZIP 或标准输出。

## New API 用户接口

| 用途 | 方法与路径 | 认证/说明 |
|---|---|---|
| 站点参数 | `GET /api/status` | 免鉴权，读 `quota_per_unit`、`price` 等 |
| 注册 | `POST /api/user/register` | JSON: `username`, `password`, `password2`；需用户明确确认 |
| 登录 | `POST /api/user/login` | rc.48 响应 `data.user.id`、`data.access_token` |
| 账户与配额 | `GET /api/user/self` | JWT Bearer；使用 `quota`、`used_quota`、`group` |
| 建用户令牌 | `POST /api/token/` | 尾斜杠不可省；创建结果不含完整 Key |
| 列令牌 | `GET /api/token/?p=0&size=100` | 根据随机唯一 name 找回 id |
| 揭示完整 Key | `POST /api/token/{id}/key` | 返回 `data.key`；最终 Key 前缀为 `sk-` |
| 兑换码 | `POST /api/user/topup` | JSON `{"key":"..."}`；一次性消耗，需用户另行确认 |
| 模型验证 | `POST /v1/chat/completions` | Bearer 用户 Key；会产生用量 |
| 充值页 | `<management_base_url>/console/topup` | 需用户登录；管理站点地址拼接 |

管理接口主机配置为 `https://www.lianhuaai.com:8091`，模型 API 主机配置为 `https://token.lianhuaai.com/v1`。rc.48 管理接口使用登录 JWT；模型调用使用 `sk-` 用户 Key。两类令牌不可混用。适配器始终保留 `/api/token/` 尾斜杠，以避免资料记录的静默失败。

### 余额换算

使用：

```text
balance_cny = quota / quota_per_unit * price
used_cny    = used_quota / quota_per_unit * price
```

脚本校验换算字段为数值、`quota_per_unit > 0`、`price >= 0`。不会把模型计费接口中单位未校准的 `total_usage` 当作余额。

### ¥10 测试额度

用户 API 没有任意赠送额度的接口。机房文档提供两条路：

1. 站长后台将“新用户配额”设为 `10 × quota_per_unit ÷ price`。当前公开 status 参数对应 `10 × 500000 ÷ 1 = 5,000,000 quota`。
2. 由站长生成兑换码，再由用户确认调用 `/api/user/topup`。

脚本只报告实际读取到的余额和兑换前后变化。注册成功、兑换请求成功或余额大于 ¥10 都不能单独证明特定来源的赠额。

## WorkBuddy `models.json`

本机文件路径为 `~/.workbuddy/models.json`，根结构为 JSON 数组。本包写入的模型对象如下，已与用户机器上跑通的配置逐字段对齐：

```json
{
  "id": "kimi-k3.1-pro",
  "name": "kimi-k3.1-pro",
  "vendor": "Custom",
  "url": "https://token.lianhuaai.com/",
  "apiKey": "[local secret]",
  "supportsToolCall": true,
  "supportsImages": true,
  "supportsReasoning": true,
  "useCustomProtocol": false,
  "reasoning": { "supportedEfforts": ["high", "xhigh"] }
}
```

要点：

- 模型 ID 与显示名均为小写 `kimi-k3.1-pro`。V1.0 的大写 `Kimi-K3.1-Pro` 在该站不解析，禁止写入。
- `url` 不带 `/v1` 且保留尾斜杠，与用户现有可用条目一致；skill 内部连通性验证另用 `model_base_url`（含 `/v1`），两者职责不同。
- 能力开关为 `true`，并写入 `reasoning.supportedEfforts`；V1.0 的 `false` 是未验证的保守占位值，已废弃。
- 不写 `maxInputTokens` / `maxOutputTokens`，与用户现有可用条目逐字段一致；V1.0 写死 32768 输入上限是错误值，已移除。

写入器在确认后创建带时间戳的备份，保留其他模型。相同 `id` 更新原条目，否则追加新条目。

## 继续核验清单

1. 用用户明确确认的测试账号验证管理端 JWT 登录、注册和 Key 创建/揭示流程。
2. 对 `Kimi-K3.1-Pro` 进行一次用户批准的 `max_tokens=1` 调用，确认大小写与可用性。
3. 比较新用户注册/兑换前后的余额，区分站点赠额与其他账户余额。
4. 在当前 WorkBuddy 版本确认模型列表热加载；未生效时提示用户重载/重启。
5. 低余额自动提醒还需确定调度器、周期、通知渠道及自动化工具。
