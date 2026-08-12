# Flagship Lab 可核验成果索引

核验日期：2026-08-11

本页只记录已经实现并由本地命令验证的成果。所有业务数据、法规语料和标签均为合成或演示数据，不代表生产部署、客户项目或真实业务效果。

## 一页摘要

| 方向 | 已完成成果 | 可核验结果 | 主要证据 |
|---|---|---|---|
| TaxFlow Nexus | Decimal 规则 DSL、租户隔离、幂等写入、四眼复核、审计链、Ed25519 签名证据 ZIP | 10 万条合成交易历史基准；未批准运行禁止导出；跨租户攻击测试通过 | `capability-evidence-matrix.md`、`benchmark-2026-08-11-phase2.md` |
| RegIntel Copilot | 中英文法规切片、词项与字符 TF-IDF 混合检索、引用式回答和无证据拒答 | 12 条合成查询：Recall@3=1.0000、MRR=1.0000 | `analytics-evidence-2026-08-11.md` |
| ControlPulse | JSONL事件流、幂等回放、篡改检测、受约束的缺陷整改生命周期 | 测试覆盖回放、非法跳转、责任人自关闭拒绝和转换审计 | `tests/test_analytics.py`、`tests/test_phase3_governance.py` |
| RiskGraph Investigator | NetworkX图特征、时间切分、实体隔离验证、PSI漂移、模型卡 | 标准PR-AUC 0.862674；实体隔离PR-AUC 0.869943；299/101实体零交叉 | `phase3-governance-evidence-2026-08-11.md`、`artifacts/risk-model-v1/` |
| 工程化底座 | FastAPI/OpenAPI、OIDC/JWKS、SQLAlchemy、Alembic、PostgreSQL、事务 Outbox、React/Vite 工作台、非 root 容器 | 30 项本地测试通过；GitHub backend/frontend/PostgreSQL/container 检查通过 | `capability-evidence-matrix.md`、PR #2 CI |

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
| `artifacts/risk-model-v1/riskgraph-model-card.json` | `ca616ec55e4c1518cd8041d5d6a8769aa7a13a7547540e01569c9664b8d4052d` |
| `artifacts/risk-model-v1/manifest.json` | `183266382bb3319ebac30867ae47cfb2c62f4e86c204eeaf06443def82f5e9a2` |
| `frontend/dist/index.html` | `7bbda52daa013e598fe18983350a436c25646c4d7df182c49a11604e6d6c9402` |
| `frontend/dist/assets/index-BG4Dn2YI.js` | `7cf4320ee43cb1462cca792b7002e9c401d560d367019e7735c0827d76dcd756` |
| `frontend/dist/assets/index-Cx4CTLTD.css` | `d390e104367e36bdff844be8cdbb8e9f62acffc5b1e37a4b158e6b51d035519b` |

## 投递时可使用的诚信表述

- “独立开发面向税务科技、法规检索、IT 控制和关联风险分析的四模块原型，并完成 API、权限、迁移、测试和前端演示。”
- “在合成数据上完成可复现基准；指标及实验限制随代码和证据文档提供。”
- “项目为个人工程作品，不是事务所客户项目，也未在真实生产环境验证。”

公开仓库地址、在线演示地址和个人联系方式必须由项目所有者确认后再写入简历。
