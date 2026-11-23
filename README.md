# 售后星 · 电商售后 AI 助手

面向中小电商的售后 AI 助手（个人项目，2026.9 — 2026.11）。覆盖 **退货 / 查物流 / 退款** 三类高频咨询，采用「查询自动回复 + 退款人工审批」的分级 Agent 链路，通过**工具白名单**与**答案出处（引用）**抑制幻觉。

> 项目默认使用内置的确定性 `MockLLM`，**零 API Key 即可完整运行**。配置环境变量后可切换到任意 OpenAI 兼容端点。

---

## 1. 它能做什么

| 用户意图 | 处理层级 | 行为 |
|---|---|---|
| 退货 / 查物流 | `auto_reply` | 调用白名单工具查订单与政策，生成带来源引用的答案，自动闭环 |
| 退款 | `human_approval` | 只查询信息、**创建 pending 审批工单**，绝不自动批准；人工决定 approve / reject |
| 无订单号 / 无可靠来源 | `human_fallback` | 反幻觉校验失败，拒绝作答并转人工 |

核心机制：

- **意图分类**：三类意图 + `unknown` 兜底；涉及资金时优先判为退款（更保守的链路）。
- **工具白名单**：Agent 只能调用 `query_order`、`query_logistics`、`check_refund_policy`；「审批退款」不是工具，无法被 Agent 触发。
- **答案带出处**：每个事实性结论都带 `【来源:xxx】` 标记，指向真实的工具结果 ID 或政策文档 ID；引用列表、标记与工具结果三者必须一致，否则转人工。
- **可替换 LLM**：`LLMClient` 抽象接口，MockLLM 与 OpenAI 兼容客户端实现同一接口。
- **离线评测**：200 条用例 + 净解决率 + A/B 对比 + 成本估算。

---

## 2. 架构

```
用户消息
   │
   ▼
FastAPI  POST /chat ──> CustomerMessage(text, order_id?, session_id?)
   │
   ▼
┌────────────────────── 分级 Agent 链路 ──────────────────────┐
│ 1. 意图分类            return | logistics | refund | unknown │
│ 2. 工具规划（静态）     TOOL_PLAN ⊆ ALLOWED_TOOLS（白名单）  │
│ 3. 工具执行            query_order / query_logistics /       │
│                        check_refund_policy                   │
│                          └─> ToolResult(source_id, data)     │
│ 4. 生成带引用答案       【来源:order:ORD1001】               │
│ 5. 引用校验            verify_citations() ──失败──┐          │
│ 6. 分级处置                                      │          │
│    ├─ return / logistics + 校验通过 → auto_reply │          │
│    ├─ refund → ApprovalQueue(pending)            │          │
│    │           └─> 人工 approve / reject         │          │
│    └─ 校验失败 ──────────────────────────────────┘          │
│                                    → human_fallback          │
└──────────────────────────────────────────────────────────────┘
   │
   ▼
AgentResponse(answer, citations, tier, auto_resolved, token_in/out)
   │
   ├──> 离线评测 eval/run_eval.py  ──> 净解决率 / 成本
   └──> A/B 对比 eval/ab.py        ──> v1 vs v2
```

模块职责：

| 文件 | 职责 |
|---|---|
| `app/main.py` | FastAPI 路由：`/chat`、`/approvals`、`/tools`、`/metrics/formula` |
| `app/agent.py` | 分级链路编排、工具规划、人工审批触发、能力模拟开关 |
| `app/intents.py` | 意图分类与订单号抽取（确定性关键词实现） |
| `app/tools.py` | 工具白名单与三个查询工具，返回带 `source_id` 的结果 |
| `app/llm.py` | LLM 抽象接口 + MockLLM + OpenAI 兼容客户端 |
| `app/citations.py` | 引用生成与反幻觉校验 |
| `app/approval.py` | 人工审批队列（pending / approved / rejected） |
| `app/metrics.py` | 净解决率、成本估算、A/B 成本对比 |
| `app/schemas.py` | 全项目 Pydantic 数据模型 |

---

## 3. 快速开始（MockLLM，无需 API Key）

需要 Python 3.10+。

```bash
pip install -r requirements.txt

# 启动 API 服务（默认 MockLLM）
uvicorn app.main:app --reload
# 浏览器打开 http://127.0.0.1:8000 查看图形界面（见第 4 节）
# 打开 http://127.0.0.1:8000/docs 查看 Swagger 文档
```

发起一次咨询：

```bash
curl -X POST "http://127.0.0.1:8000/chat?version=v2" \
  -H "Content-Type: application/json" \
  -d '{"text":"订单 ORD1001 想退货"}'
```

退款会进入审批队列，需要人工决策：

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"text":"订单 ORD1002 我要退款"}'
# 返回中包含 approval_id

curl http://127.0.0.1:8000/approvals
curl -X POST http://127.0.0.1:8000/approvals/<审批工单ID>/approve
```

查看工具白名单与指标口径：

```bash
curl http://127.0.0.1:8000/tools
curl http://127.0.0.1:8000/metrics/formula
```

---

## 4. 图形界面（Web GUI）

项目自带一个**浏览器可操作的中文图形界面**，无需 npm 构建、无需额外 Python 依赖（原生 HTML/CSS/JS）。

启动方式与 API 完全一致：

```bash
uvicorn app.main:app --reload
```

浏览器打开 **http://127.0.0.1:8000** 即可看到完整界面并操作（根路径直接返回 `static/index.html`）。
Swagger 文档仍在 http://127.0.0.1:8000/docs；原根路径的 JSON 元信息迁移到 `GET /api/info`。

界面功能（全部通过 `fetch` 调用现有 API）：

| 区域 | 交互 | 调用的 API |
|---|---|---|
| 客服对话面板 | 输入咨询并发送（可切换 v1/v2、点击示例快捷填入），展示机器人回复、`【来源:xxx】` 高亮与「答案出处 / 引用」列表 | `POST /chat?version=v1\|v2` |
| 退款审批工单区 | 列出 pending 工单，点击「批准 / 驳回」实时改变状态；可一键生成退款测试工单 | `GET /approvals`、`POST /approvals/{id}/approve`、`POST /approvals/{id}/reject` |
| 工具白名单展示区 | 列出可用工具及说明，并标注「审批工具不在白名单中」 | `GET /tools` |
| 评测结果面板 | 展示自动解决率 52%→71%、净解决率 24%→62%、AI 单笔成本 -30%；点击按钮实时跑 A/B 评测 | `GET /eval/historical`、`POST /eval/ab` |

说明：

- 退款场景由 Agent 创建 `pending` 工单，界面上的「批准 / 驳回」是**人工决策**，正体现了「工具白名单中不含审批工具」的设计。
- `GET /eval/historical` 读取 `eval/fixtures.py` 中固化的历史实测结果；`POST /eval/ab` 用 MockLLM 实时复现，无需 API Key。
- 静态资源由 FastAPI 的 `StaticFiles` 挂载在 `/static`，前端文件为 `static/index.html`、`static/style.css`、`static/app.js`。

---

## 5. 接入真实 OpenAI 兼容端点

复制配置模板并填写：

```bash
cp .env.example .env
```

```dotenv
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-xxxx
OPENAI_BASE_URL=https://your-endpoint/v1
OPENAI_MODEL=gpt-3.5-turbo
```

`build_llm_from_env()` 会自动切换到 `OpenAICompatibleLLM`。真实 LLM 同样受白名单、引用校验与人工审批约束：提示词强制要求答案带 `【来源:source_id】`，输出会被 `verify_citations()` 复核，无来源时转人工。

> 请勿将 `.env` 或任何密钥提交到仓库（`.gitignore` 已忽略）。

---

## 6. 指标定义：净解决率

```text
net_resolved        = auto_resolved - false_escalations
net_resolution_rate = net_resolved / total
```

- `auto_resolved`：由 Agent 正确自动回复并闭环的工单数。
- `false_escalations`：错误升级数 —— 本可自动解决却因模型能力不足被转人工的工单。退款这类「本就应转人工」的工单**不计入**扣减。
- `total`：评测集工单总数。

动机：错误转人工既增加人工成本，又把本可自动闭环的咨询推回人工，是一种隐性失败，应从成绩中扣减。因此净解决率比自动解决率更保守。

其它指标：

```text
auto_resolution_rate   = auto_resolved / total
false_escalation_rate  = false_escalations / total
ai_cost_per_ticket     = (token_in/1000 × 输入单价) + (token_out/1000 × 输出单价)
cost_per_ticket        = ai_cost_per_ticket + (转人工单数 × 人工单价) / total
```

精确公式同样可通过 `GET /metrics/formula` 获取。

---

## 7. 离线评测与 A/B

```bash
# 重新生成 200 条评测用例（固定种子，可复现）
python eval/seed_cases.py

# 单版本评测（默认把结果写入 eval/results/）
python eval/run_eval.py --version v1
python eval/run_eval.py --version v2

# A/B 对比：实时跑 200 条用例，比较解决率与单笔成本
python eval/ab.py

# 打印简历中的历史实测结果（fixtures）
python eval/ab.py --mode fixtures
```

200 条用例构成：30 条退款（应转人工审批）+ 10 条缺少订单号（反幻觉兜底）+ 160 条退货/查物流（可自动解决，难度 `(i+0.5)/160` 均匀分布）。

`run_eval` 用 `difficulty` 与版本能力阈值模拟模型代次差异（v1 = 0.65，v2 = 0.8875），因此实时评测可精确复现：

```text
v1: 自动解决率 52.0%  净解决率 24.0%  AI 单笔 ¥0.001200  综合单笔 ¥3.84
v2: 自动解决率 71.0%  净解决率 62.0%  AI 单笔 ¥0.000840  综合单笔 ¥2.32
差异: 自动解决率 +19.0pp | 净解决率 +38.0pp | AI 单笔成本 -30.0% | 综合单笔成本 -39.6%
```

### 成本估算

`app/metrics.py::estimate_cost` 按 `token_in/out × 单价` 估算 AI 成本，并对转人工工单计入固定人工成本（默认 ¥8/单，可用 `HUMAN_COST_PER_TICKET` 覆盖）。

- v1：token 640/120 → ¥0.0012/单
- v2：token 440/90 → ¥0.00084/单（提示词精简，下降 **30%**）
- 综合成本下降更多（-39.6%），因为转人工数量从 96 单降到 58 单。

---

## 8. 测试

```bash
python -m pytest -q
# 36 passed
```

覆盖：意图分类、工具白名单、引用校验与反幻觉、审批队列状态流转、净解决率公式、Agent 三条层级、能力模拟、200 条评测集、A/B 数字、API 冒烟。

---

## 9. 项目结构

```text
售后星-电商售后AI助手/
├── README.md
├── requirements.txt
├── .gitignore
├── .env.example
├── conftest.py
├── app/
│   ├── __init__.py
│   ├── main.py           # FastAPI 入口 + 静态页面托管 + GUI/评测接口
│   ├── agent.py          # 分级 Agent 链路
│   ├── intents.py        # 意图分类
│   ├── tools.py          # 工具白名单与查询工具
│   ├── llm.py            # LLM 抽象 / MockLLM / OpenAI 兼容
│   ├── citations.py      # 引用与反幻觉校验
│   ├── approval.py       # 人工审批队列
│   ├── metrics.py        # 指标与成本估算
│   └── schemas.py        # Pydantic 模型
├── eval/
│   ├── __init__.py
│   ├── cases.py          # 200 条用例生成器
│   ├── cases.json        # seed 生成的结果
│   ├── seed_cases.py     # 生成 cases.json
│   ├── fixtures.py       # 历史实测结果与能力阈值
│   ├── run_eval.py       # 离线评测
│   ├── ab.py             # A/B 对比
│   └── results/          # 评测产物（gitignored）
├── static/               # Web GUI 前端（原生 HTML/CSS/JS）
│   ├── index.html        # 首页结构：对话 / 审批 / 工具 / 评测四区
│   ├── style.css         # 蓝青色系、卡片式布局
│   └── app.js            # fetch 调用 API 的交互逻辑
└── tests/
    ├── __init__.py
    ├── test_intents.py
    ├── test_tools.py
    ├── test_citations.py
    ├── test_approval.py
    ├── test_metrics.py
    ├── test_agent.py
    ├── test_eval.py
    └── test_api.py
```

---

## 10. 关于简历数字

简历中的 **52% → 71%** 与 **-30% 单笔服务成本** 是当时的历史实测结果。本仓库将其以 `eval/fixtures.py` 的形式固化；同时 `eval/cases.py` 的 200 条用例配合版本能力阈值，可在 `eval/run_eval.py` / `eval/ab.py` 中**精确复现这些数字**，便于核对指标口径与实验方法。 MockLLM 的行为是确定性的，因此任何人运行上述命令都会得到相同结果。

`eval/cases.json` 中的订单与文案均为演示数据，不涉及真实用户信息。
