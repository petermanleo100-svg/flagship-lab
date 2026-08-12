# Flagship Lab

面向税务科技、法规检索、IT 控制与关系风险调查的可审计工作流平台。项目以“代码、API、文档和自动化证据一致”为发布原则；准确能力边界以 [`docs/capability-evidence-matrix.md`](docs/capability-evidence-matrix.md) 为准。

## 已实现能力

- **TaxFlow Nexus**：Decimal/Numeric 财务精度、版本化规则包、异常发现、写请求幂等、四眼复核、租户隔离。
- **RegIntel Copilot**：法规版本留存、词项与字符 TF-IDF 混合检索、引用回答、证据不足拒答和固定评测集。
- **ControlPulse**：控制事件幂等接入、缺陷案例生命周期、四眼关闭、乐观并发控制和可追溯转换历史。
- **RiskGraph Investigator**：租户级实体图、共享账户与三节点闭环检测、可解释证据。
- **平台治理**：SQLAlchemy 单一运行路径、PostgreSQL CI、冻结的 Alembic 迁移链、租户哈希审计链、事务 Outbox 与重试发布器。
- **安全与证据**：OIDC/JWKS 或本地开发 JWT、角色权限、Ed25519 公钥可验签证据包、请求追踪、安全响应头。
- **运维接口**：`/health/live`、数据库就绪探针 `/health/ready`、Prometheus 文本指标 `/metrics`。
- **生产硬化**：资源级授权、S3 Object Lock/KMS 适配、Kafka Outbox/DLQ、OpenTelemetry、加密逻辑备份与验证恢复。

本仓库不会把路线图当作现有功能。对象锁定存储、KMS 密钥托管、完整资源级 ABAC、生产消息代理适配器、OpenTelemetry collector 与大图数据库仍在能力矩阵中标为限制或路线图。

## 本地开发

```powershell
python -m pip install -e ".[test]"
$env:FLAGSHIP_JWT_SECRET="replace-with-a-random-secret-of-at-least-32-characters"
python -m flagship_lab.cli api --db work/api.db --port 8000 --allow-dev-tokens
```

打开 `http://127.0.0.1:8000/docs` 使用 OpenAPI 页面。`--allow-dev-tokens` 只能用于本地开发，生产环境必须关闭。

运行验证：

```powershell
pytest -q
$env:FLAGSHIP_DATABASE_URL="postgresql+psycopg://user:password@host:5432/flagship"
alembic upgrade head
```

## 容器部署基线

```powershell
$env:POSTGRES_OWNER_PASSWORD="use-a-secret-manager-owner-value"
$env:POSTGRES_APP_PASSWORD="use-a-distinct-runtime-value"
$env:FLAGSHIP_OIDC_ISSUER="https://identity.example.com"
$env:FLAGSHIP_OIDC_JWKS_URL="https://identity.example.com/.well-known/jwks.json"
$env:FLAGSHIP_BACKUP_KEY_BASE64="base64-encoded-32-byte-key"
$env:FLAGSHIP_JWT_SECRET="local-compose-only-secret-at-least-32-characters"
docker compose up --build
```

Compose uses a migration owner only for Alembic and a separate `NOSUPERUSER NOBYPASSRLS` runtime role. Before accepting traffic, the API preflight verifies the exact migration revision, table ownership, forced RLS, production OIDC configuration and backup key; CI boots this complete topology on every commit.

容器以非 root 用户运行，API 文件系统只读、移除 Linux capabilities，并在 API 启动前执行迁移任务。生产部署应使用 OIDC/JWKS 和外部密钥管理，而不是 Compose 示例中的本地 JWT 密钥。

OIDC 生产变量：

- `FLAGSHIP_OIDC_ISSUER`
- `FLAGSHIP_OIDC_AUDIENCE`
- `FLAGSHIP_OIDC_JWKS_URL`
- `FLAGSHIP_EVIDENCE_PRIVATE_KEY_FILE`（挂载的 Ed25519 私钥；生产建议改为 KMS/HSM 适配器）

## API 主路径

- 税务：`POST /tax/transactions`、`POST /tax/runs`、`POST /tax/runs/{run_id}/review`、`GET /tax/findings`
- 证据：`GET /evidence/tax/{run_id}`
- 法规：`POST /reg/documents`、`POST /reg/answer`
- 控制：`POST /controls/events`、`GET /controls/cases`、案例转换与历史接口
- 图谱：`POST /graph/entities`、`POST /graph/edges`、`GET /graph/findings`
- 治理：`GET /audit/verify`、健康探针与指标接口

税务导入与规则运行支持 `Idempotency-Key` 请求头。同一个租户和操作内，相同键与相同请求会重放原结果；同一个键配不同请求会返回冲突。

## 验证与真实性

CI 包含 Python 全量测试、PostgreSQL 17 真实服务测试和 React 构建。迁移测试覆盖空库创建以及从 `20260811_0002` 带数据升级。性能数字只允许引用带环境说明的基准报告，不从合成数据推导生产 SLA 或真实风险识别效果。

仓库发布治理包含 Python 与 JavaScript/TypeScript CodeQL、每周依赖更新、安全路径 CODEOWNERS 和逐项发布清单。GitHub `main` 已要求 PR、严格 CI/CodeQL 检查、线性历史和讨论解决，管理员同样受约束，并禁止强推和删除；这些外部设置必须在每次正式发布前重新取证。

CI 还使用 `promtool` 校验版本化告警规则，为构建后的容器生成 SPDX JSON SBOM，并阻断已有修复的 Critical 漏洞；普通 CI 镜像不冒充已发布或已签名的生产镜像。

手动 `release-image` 运行会生成候选镜像归档、SHA-256、SBOM 和 GitHub attestations，但不会发布镜像；只有经批准的 `vX.Y.Z` 标签才可生成带不可变摘要、来源证明与 SBOM 证明的 GHCR 镜像。

PostgreSQL CI 还覆盖同一幂等键并发写入、租户审计链并发串行化，以及加密备份恢复到独立 schema。Compose 提供独立 Outbox worker 和 OpenTelemetry Collector；生产环境仍需配置真实 Kafka、遥测后端、KMS、S3 Object Lock、WAL/PITR 与告警路由。

生产 PostgreSQL 必须分离迁移所有者、请求服务与运维 worker 角色。请求服务使用 `NOSUPERUSER NOBYPASSRLS`；备份和跨租户 Outbox worker 的 `BYPASSRLS` 角色只能由独立密钥和审计策略控制。CI 会用非 owner 角色验证无 tenant context 返回零行、跨租户读写被 RLS 拒绝。

详细索引见 [`docs/portfolio-evidence-index.md`](docs/portfolio-evidence-index.md)。
