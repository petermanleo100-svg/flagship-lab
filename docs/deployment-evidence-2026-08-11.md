# 数据库与前端交付证据

## PostgreSQL在线迁移

- PostgreSQL：18.3，Windows x86_64。
- 隔离集群：工作区临时目录，端口55439，测试结束后已停止。
- Alembic head：`20260811_0002`；独立Phase 3迁移兼容从`20260811_0001`升级。
- 当前元数据：11张业务表加`alembic_version`，其中新增复核工作流与案件转换历史表。
- 数据写入：成功插入并查询1条`audit_events`记录。
- 降级：除Alembic版本管理外业务表数量为0。
- 再升级：成功恢复至head。

SQLite完成`head → 0001 → head → base`迁移往返并加入自动化测试；此前首版迁移已在本机PostgreSQL 18.3执行。Phase 3增量迁移尚未另行在PostgreSQL复测，不代表高可用、备份恢复或生产负载验证。

## React生产构建与页面检查

- React：19.2.8；Vite：8.2.1；`pnpm-lock.yaml`已生成。
- 生产构建：成功，16个模块完成转换。
- 构建产物：HTML 0.51 kB；CSS 3.01 kB；JS 194.77 kB（gzip 61.79 kB）。
- 浏览器复核：Phase 3治理指标与四个模块全部可见；未启动API时按设计显示`Offline evidence mode`。
- 页面宽度：clientWidth=1265，scrollWidth=1265，无横向溢出。
- 控制台：0条warning/error。

页面明确说明所有指标来自合成数据，不代表生产税务、法律或舞弊识别准确率。

## API可观测性与密钥边界

- 每个HTTP响应返回`X-Request-ID`，并通过`Server-Timing`暴露应用处理耗时；调用方也可传入请求ID完成链路关联。
- JWT与证据签名支持使用`FLAGSHIP_JWT_SECRET`、`FLAGSHIP_EVIDENCE_SIGNING_SECRET`两把独立密钥；管理检查接口会报告是否完成密钥分离。
