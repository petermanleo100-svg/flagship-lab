# Phase 2演示指南

## 1. 安装与启动

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
$env:FLAGSHIP_JWT_SECRET="demo-secret-change-me-32-characters-minimum"
.\.venv\Scripts\python.exe -m flagship_lab.cli api --db work/api-demo.db --port 8000 --allow-dev-tokens
```

打开 `http://127.0.0.1:8000/docs`。

## 2. 角色演示

调用 `POST /auth/dev-token` 分别生成：

- `analyst`：上传交易、执行规则；不能下载证据包。
- `reviewer`：查看发现、验证审计链、下载证据包；不能运行规则。
- `admin`：全部权限并能访问配置检查。

不带令牌调用 `POST /tax/runs` 应返回401；viewer调用应返回403。

## 3. TaxFlow端到端

1. analyst调用 `POST /tax/transactions`，上传一条缺失税号和一条税额不一致交易。
2. analyst调用 `POST /tax/runs`，返回规则包版本、规则包哈希和run_id。
3. reviewer调用 `GET /tax/findings?run_id=...`，看到`TAX_ID_REQUIRED`和`VAT_RECALC`。
4. analyst调用 `GET /evidence/tax/{run_id}`应返回403。
5. reviewer下载ZIP；用`verify_evidence_package`验证应为有效。
6. 修改`findings.json`后重打包，验证器应返回`hash_mismatch:findings.json`。

## 4. 面试讲解重点

- 为什么规则版本和规则内容哈希都要进入审计事件。
- 为什么分析员不能下载最终证据包，以及复核职责如何分离。
- 证据包哈希只能证明完整性，下一阶段为何仍需非对称签名和可信时间戳。
- SQLite基准的适用边界，以及迁移PostgreSQL时如何重新建立性能与事务证据。

