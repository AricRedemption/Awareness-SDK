# 决策记录（Architecture Decision Records）

格式：MADR-lite（状态 / 日期 / 背景 / 决策 / 后果），一决策一文件。
编号续接本仓 F-xxx 体系（F-061 起 = 参数化集成线）。

状态取值：`Proposed` / `Accepted` / `Superseded by F-xxx` / `Deprecated`。

| 编号 | 标题 | 状态 | 日期 |
|---|---|---|---|
| [F-061](F-061-dependency-direction.md) | 依赖方向 SDK→M1 单向，只经 memory_broker 包 | Accepted | 2026-09-06 |
| [F-062](F-062-broker-graceful-degradation.md) | broker 不可达时优雅降级，不硬依赖 | Accepted | 2026-09-06 |
| [F-063](F-063-first-hop-pure-prepend.md) | 召回首跳纯前插、默认关 | Accepted | 2026-09-06 |
| [F-064](F-064-relative-zero-threshold.md) | 首跳命中判据沿用 M1 相对零阈值 | Accepted | 2026-09-06 |
| [F-065](F-065-hook-switches-independent-default-off.md) | 事件钩子双开关独立、默认 False | Accepted | 2026-09-06 |
| [F-066](F-066-conflict-decision-stays-local.md) | 冲突判定权留在本仓，参数层只执行 | Accepted | 2026-09-06 |
| [F-067](F-067-migration-zip-jsonl.md) | 会话迁移沿用 export_reader 的 zip+JSONL 格式 | Accepted | 2026-09-06 |
| [F-068](F-068-bit-exact-parametric-only.md) | bit-exact 保证只覆盖参数化层 | Accepted | 2026-09-06 |
| [F-069](F-069-sdk-trace-design.md) | SDK 级 trace：M1 信封 + OTel 字段映射 + opt-in hash-only；设立本治理体系 | Accepted | 2026-09-06 |
| [F-070](F-070-governance-execution-infrastructure.md) | 治理与 trace 的工程化执行设施：CI / trace 分析器 / A-B 一键化 / 主张校验 | Accepted | 2026-09-06 |

新决策：复制任一文件的五节骨架，编号递增，同步更新本表。
