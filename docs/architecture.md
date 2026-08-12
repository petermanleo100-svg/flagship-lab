# Phase 3架构

## 边界

`flagship_lab` 采用模块化单体：四个领域模块共享 SQLite 事务、规范化 JSON、SHA-256 审计链和同一 HTTP 入口，但领域表、服务类和规则保持隔离。第一阶段选择零第三方依赖，是为了让测试、面试演示和复现不依赖网络或容器环境。

```text
HTTP / CLI
    |
    +-- TaxFlowService ------ 发票、规则运行、异常发现
    +-- RegIntelService ----- 文档版本、检索、引用与拒答
    +-- ControlPulseService - 事件、控制策略、缺陷案件
    +-- RiskGraphService ---- 实体、关系、风险解释
    |
SQLite + append-only hash-chained audit_events
```

## 已实现的工程属性

- 事务提交/回滚和外键约束。
- 规范化 JSON 哈希，避免字段顺序影响证据摘要。
- 跨模块追加式审计链，可逐事件验证前序哈希和内容哈希。
- TaxFlow 规则版本与规则运行记录分离。
- RegIntel 文档按内容哈希版本化，回答必须带引用或明确拒答。
- ControlPulse 策略结果保留控制编号、严重性和证据哈希。
- RiskGraph 发现同时返回风险代码、分数、实体、解释和证据。
- CLI、JSON HTTP API、单元测试和可复现基准命令。
- FastAPI应用工厂、OpenAPI、Pydantic输入边界和统一HTTP状态码。
- 生产 OIDC/JWKS（RS256/ES256）与本地开发 HS256 JWT；读取、分析、复核和管理员操作分离，并绑定租户声明。
- TaxFlow JSON规则DSL；规则包版本与内容哈希进入审计事件。
- 证据ZIP包含运行、发现与审计事件，清单使用SHA-256逐文件校验并检测篡改。
- RegIntel融合词项检索与字符TF-IDF余弦相似度，并提供Recall@K/MRR评测器。
- RiskGraph使用NetworkX生成图特征，按月份严格划分训练/测试并输出模型卡。
- ControlPulse提供带偏移量和哈希链的JSONL事件流、原子检查点、幂等消费及回放。
- TaxFlow运行工作流强制发起人与复核人分离；只有`APPROVED`运行可以导出签名证据。
- 证据清单在逐文件 SHA-256 和清单哈希之外支持 Ed25519 非对称签名与公钥验签；HMAC-SHA256 仅为兼容路径。
- ControlPulse缺陷状态机拒绝非法跳转与责任人自关闭，转换历史同时进入审计哈希链。
- RiskGraph除时间外留出外，增加实体隔离留出和逐特征PSI漂移报告，避免同一实体跨集合泄漏。

## 后续拆分方向

1. `StoragePort`：SQLite/PostgreSQL 双实现，迁移到 Alembic。
2. `RuleEnginePort`：TaxFlow JSON DSL已实现；继续增加YAML加载和ControlPulse OPA/Rego。
3. `EvidenceStorePort`：本地ZIP与哈希清单已实现；继续增加MinIO和非对称签名。
4. `SearchPort`：当前词项+字符TF-IDF升级为BM25 + embedding + reranker。
5. `GraphPort`：当前NetworkX时间图特征升级为Neo4j，并增加SHAP解释和对抗漂移测试。
6. FastAPI/OpenAPI、JWT/RBAC与请求关联头已实现；继续增加异步任务、指标导出及OpenTelemetry。
