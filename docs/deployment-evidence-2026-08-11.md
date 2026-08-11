# 数据库与前端交付证据

## PostgreSQL在线迁移

- PostgreSQL：18.3，Windows x86_64。
- 隔离集群：工作区临时目录，端口55439，测试结束后已停止。
- Alembic修订：`20260811_0001`。
- 升级后：9张业务表加`alembic_version`，共10张public表。
- 数据写入：成功插入并查询1条`audit_events`记录。
- 降级：除Alembic版本管理外业务表数量为0。
- 再升级：成功恢复至head。

SQLite同样完成upgrade→downgrade→upgrade，并加入自动化测试。上述证据证明首版迁移在SQLite和本机PostgreSQL 18.3可执行，不代表高可用、备份恢复或生产负载验证。

## React生产构建与页面检查

- React：19.2.8；Vite：8.2.1；`pnpm-lock.yaml`已生成。
- 生产构建：成功，16个模块完成转换。
- 构建产物：HTML 0.51 kB；CSS 3.01 kB；JS 194.73 kB（gzip 61.80 kB）。
- 浏览器检查：标题正确，四个模块全部可见，API状态显示`API 0.2.0`。
- 页面宽度：clientWidth=1265，scrollWidth=1265，无横向溢出。
- 控制台：0条warning/error。

页面明确说明所有指标来自合成数据，不代表生产税务、法律或舞弊识别准确率。

