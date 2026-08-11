# Flagship Lab 可核验成果索引

核验日期：2026-08-11

本页只记录已经实现并由本地命令验证的成果。所有业务数据、法规语料和标签均为合成或演示数据，不代表生产部署、客户项目或真实业务效果。

## 一页摘要

| 方向 | 已完成成果 | 可核验结果 | 主要证据 |
|---|---|---|---|
| TaxFlow Nexus | 版本化税务规则 DSL、批量处理、审计哈希链、可验证证据 ZIP | 10 万条合成交易端到端吞吐 43,324.53 条/秒 | `benchmark-2026-08-11-phase2.md` |
| RegIntel Copilot | 中英文法规切片、词项与字符 TF-IDF 混合检索、引用式回答和无证据拒答 | 12 条合成查询：Recall@3=1.0000、MRR=1.0000 | `analytics-evidence-2026-08-11.md` |
| ControlPulse | JSONL 追加事件流、偏移量、检查点、幂等回放、哈希链篡改检测 | 自动化测试覆盖回放、重复消费和篡改检测 | `tests/test_analytics.py`、`tests/test_phase2.py` |
| RiskGraph Investigator | NetworkX 图特征、严格时间切分、随机森林基线、模型卡和制品 | 测试集 1,600 行；PR-AUC 0.862674、ROC-AUC 0.922464、Recall@Top5%=0.837209 | `analytics-evidence-2026-08-11.md`、`artifacts/risk-model-v1/` |
| 工程化底座 | FastAPI/OpenAPI、JWT 角色权限、SQLAlchemy 模型、Alembic、React/Vite 演示端 | 16 项测试通过；SQLite 与 PostgreSQL 18.3 迁移往返通过；前端生产构建通过 | `deployment-evidence-2026-08-11.md` |

## 复核命令

在项目根目录执行：

```powershell
$env:PYTHONPATH="src"
python -m pytest -q
python -m flagship_lab.cli benchmark --db work/benchmark.db --rows 100000
python -m flagship_lab.cli reg-eval --db work/reg-eval.db --k 3
python -m flagship_lab.cli risk-benchmark --entities 400 --months 12 --train-through 8 --output-dir artifacts/risk-model-v1
python -m flagship_lab.cli control-stream-demo --db work/control.db --stream work/events.jsonl --checkpoint work/checkpoint.json
Set-Location frontend
pnpm install --frozen-lockfile
pnpm run build
```

数据库迁移验证：

```powershell
alembic upgrade head
alembic downgrade base
alembic upgrade head
```

PostgreSQL 环境需通过 `FLAGSHIP_DATABASE_URL` 或 Alembic 的 `sqlalchemy.url` 指定连接串；不要把口令提交到仓库。

## 关键制品 SHA-256

| 文件 | SHA-256 |
|---|---|
| `artifacts/risk-model-v1/riskgraph-baseline.joblib` | `dcbf90d0c4ba3f55fe4198053a40b32361b2c22eec394df7bad37a1adb12ecef` |
| `artifacts/risk-model-v1/riskgraph-model-card.json` | `aebd45cd766481da265c34cd2d14c12028444e593726d9f15b9c7458bac46a75` |
| `artifacts/risk-model-v1/manifest.json` | `4df96f0c8d2c0c56f82d346c6887551117e7d977aa84e380df2c35db3cf7f5d0` |
| `frontend/dist/index.html` | `16339b38dfc01047a48154db2778144a4ff24f575f1627f9fa705ebebea87d04` |
| `frontend/dist/assets/index-BqxOcETD.js` | `90771217e8755fc0b5cbd57dff12429d9c791d5a9273dc7af3a4f89a666f7222` |
| `frontend/dist/assets/index-Cx4CTLTD.css` | `d390e104367e36bdff844be8cdbb8e9f62acffc5b1e37a4b158e6b51d035519b` |

## 投递时可使用的诚信表述

- “独立开发面向税务科技、法规检索、IT 控制和关联风险分析的四模块原型，并完成 API、权限、迁移、测试和前端演示。”
- “在合成数据上完成可复现基准；指标及实验限制随代码和证据文档提供。”
- “项目为个人工程作品，不是事务所客户项目，也未在真实生产环境验证。”

公开仓库地址、在线演示地址和个人联系方式必须由项目所有者确认后再写入简历。
