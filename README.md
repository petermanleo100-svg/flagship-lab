# Flagship Lab

四个面向四大实习岗位的可审计软件工程项目。第二阶段已覆盖 FastAPI/OpenAPI、JWT角色权限、版本化规则DSL、可验证证据包、混合检索、时间切分风险模型和可重放控制事件流。

## 当前可运行模块

- **TaxFlow Nexus**：合成发票生成、批量入库、版本化税务规则、异常发现、哈希审计链。
- **RegIntel Copilot**：法规文档版本化、中文/英文词项检索、带原文引用的证据型回答、无证据拒答。
- **ControlPulse**：IT控制事件接入、策略即代码检测、控制缺陷案件、证据哈希。
- **RiskGraph Investigator**：企业/账户交易图、共享账户与循环交易检测、可解释风险评分。

新增可核验能力：

- RegIntel：词项分数与字符TF-IDF混合排序，固定评测集输出Recall@K和MRR。
- RiskGraph：NetworkX图特征、严格月份切分、随机森林基线、模型卡和模型制品。
- ControlPulse：JSONL追加式事件流、偏移量、流哈希链、检查点、幂等消费和回放。

## 快速开始

```powershell
$env:PYTHONPATH="src"
python -m flagship_lab.cli demo --db work/demo.db
python -m unittest discover -s tests -v
python -m flagship_lab.cli serve --db work/server.db --port 8080
```

第二阶段 FastAPI：

```powershell
python -m pip install -e ".[test]"
$env:FLAGSHIP_JWT_SECRET="replace-with-a-random-secret-of-at-least-32-characters"
python -m flagship_lab.cli api --db work/api.db --port 8000 --allow-dev-tokens
```

浏览 `http://127.0.0.1:8000/docs` 查看 OpenAPI 交互文档。`--allow-dev-tokens` 仅供本地演示；默认关闭。

生成更大规模的 TaxFlow 基准数据：

```powershell
$env:PYTHONPATH="src"
python -m flagship_lab.cli benchmark --db work/benchmark.db --rows 100000
python -m flagship_lab.cli reg-eval --db work/reg-eval.db --k 3
python -m flagship_lab.cli risk-benchmark --entities 400 --months 12 --train-through 8 --output-dir artifacts/risk-model
python -m flagship_lab.cli control-stream-demo --db work/control.db --stream work/events.jsonl --checkpoint work/checkpoint.json
```

服务启动后可访问 `GET /health`、`POST /tax/transactions`、`POST /tax/runs`、`GET /tax/findings?run_id=...`、`POST /reg/documents`、`POST /reg/answer`、`POST /controls/events`、`GET /controls/cases`、`POST /graph/entities`、`POST /graph/edges`、`GET /graph/findings` 和 `GET /audit/verify`。

## 真实性规则

README 与简历中的性能、召回率等数字必须来自 `benchmark` 或测试输出。不应把未来规划当成已实现功能。

第二阶段 DSL 实测：10万条合成交易端到端吞吐 `43,324.53 条/秒`；详细环境限制见 [`docs/benchmark-2026-08-11-phase2.md`](docs/benchmark-2026-08-11-phase2.md)。架构边界见 [`docs/architecture.md`](docs/architecture.md)，演示步骤见 [`docs/demo-guide.md`](docs/demo-guide.md)。

## 已完成的第二阶段能力

1. FastAPI/OpenAPI 和 Pydantic 输入校验。
2. HS256 JWT，包含 `viewer`、`analyst`、`reviewer`、`admin` 四类角色。
3. 税务规则 JSON DSL、规则包版本与内容哈希。
4. TaxFlow 证据 ZIP：运行、发现、审计事件和 SHA-256 清单；支持篡改检测。
5. 16项自动化测试，覆盖401/403、规则包校验、证据下载权限、事件流、篡改检测和数据库迁移往返。
6. RegIntel混合检索评测、RiskGraph时间切分模型和ControlPulse事件流回放。

## 下一阶段

1. 增加刷新令牌、密钥轮换、用户目录和更细粒度资源权限。
2. TaxFlow 增加字段级血缘、异常审批流和证据包非对称签名。
3. RegIntel将当前词项+字符TF-IDF升级为BM25+embedding+rereanker，并扩展公开数据评测集。
4. ControlPulse将JSONL适配器升级为Redpanda/Kafka、OPA和对象存储证据湖。
5. RiskGraph增加SHAP、实体隔离验证和Neo4j适配。
6. 增加 OpenTelemetry 可观测性，并把当前 React 演示端扩展为完整管理工作台。

## 部署与演示证据

- Alembic首版迁移已在SQLite和本机PostgreSQL 18.3完成升级、降级、再升级验证。
- React/Vite演示端已完成生产构建与浏览器检查；详见[`docs/deployment-evidence-2026-08-11.md`](docs/deployment-evidence-2026-08-11.md)。
- 基准、模型制品、测试和诚信表述汇总见[`docs/portfolio-evidence-index.md`](docs/portfolio-evidence-index.md)。
