# F-073 · 主张-证据显式映射文件（CLAIMS.md 模式）

- **状态**: Proposed（待上游裁决）
- **日期**: 2026-09-07
- **提案**: 在 GOVERNANCE §7 之外引入机读的 `CLAIMS.md` 主张-证据映射
- **执行状态**: 纯提案，未动任何代码与 §7 文本

## 背景

`scripts/check_claims.py`（F-070）以正则启发式扫描 README 数字并对照 §7 登记
簿——能抓住"未登记数字"，但有结构性局限：

1. **数字等价匹配有灰区**：`480/500` 与 `96.0` 指同一主张，靠数值集合匹配
   无法表达"这两个数字是同一条主张的两种写法"；
2. **主张无生命周期**：被撤回的主张（M1 RESULTS.md 的 RETRACTED 纪律）在
   登记簿里只能靠文字备注，机读时无法区分"active / retracted / superseded"；
3. **证据锚点粒度粗**：§7 产物列指向整个文件，无法指向"文件中的哪张表"。

业界先例：eslint 仓库的 `CLAIMS.md` 把每条营销/基准主张显式映射到证据文件，
作为可 lint 的仓库工件（2026-09-07 S7 轮搜索发现）。

## 建议决议（待上游采纳，未实施）

1. **新增 `CLAIMS.md`**（仓库根），每条对外主张一行：
   `| claim-id | 文案 | 数字 | 证据锚点（文件#锚） | 复现命令 | 状态 active/retracted/superseded | 起止日期 |`
2. **check_claims.py 升级**：README 数字主张必须映射到 CLAIMS.md 的 active
   行（等价关系显式声明，如 `480/500 == 96.0%`）；retracted 行的数字出现在
   README → 违规（撤回纪律的机械化，对标 M1 RESULTS.md）。
3. **§7 与 CLAIMS.md 的关系**：§7 保留为治理登记簿（人读 + 决策记录），
   CLAIMS.md 为其机读证据映射（lint 消费）；两者以 claim-id 对账，
   `check_claims.py` 增加 §7↔CLAIMS 一致性检查。
4. **迁移**：现有 §7 各行批量导入 CLAIMS.md（含 2026-09-06/07 门禁复测的
   全部主张），一次性对账。

## 后果（若上游采纳）

- 主张获得显式生命周期（active/retracted/superseded）——M1 RESULTS.md 的
  撤回纪律在 SDK 侧可机读执行
- lint 从启发式升级为声明式（零误报空间）
- 代价：主张登记从一处变两处（以 claim-id 对账缓解）；表格式变更属治理
  修订，故本提案以 ADR 形式交上游
- **若上游不采纳**：维持 F-070 的正则启发式 lint 现状，本文件归档
  Discontinued

## 与既有决策的关系

- F-070（主张校验脚本）：本法是其声明式升级路线
- M1 RESULTS.md：RETRACTED 纪律的 SDK 侧对标来源
