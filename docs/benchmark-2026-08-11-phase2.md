# TaxFlow Phase 2 DSL 100K基准

运行日期：2026-08-11  
规则包：`cn-tax-demo/2026.08.2`  
规则包SHA-256：`16af595bd753c81a1105e8cd64b21320595684190cec3163b843aea808780e51`

运行命令：

```powershell
python -m flagship_lab.cli benchmark --db work/benchmark-100k-dsl-v2.db --rows 100000
```

| 指标 | 实测值 |
|---|---:|
| 合成交易 | 100,000条 |
| 规则发现 | 5,889条 |
| 数据生成 | 0.4975秒 |
| SQLite批量入库 | 1.2980秒 |
| DSL规则扫描与结果落库 | 0.5127秒 |
| 端到端吞吐 | 43,324.53条/秒 |

结果仅适用于当前本地环境、SQLite WAL、固定随机种子、四项演示规则和单进程执行。它证明当前实现的可复现基线，不代表生产SLA。

质量门：`11 passed`；另以旧版`unittest`入口复核6项核心测试；`compileall`通过。

