#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_claims.py — GOVERNANCE §7 主张登记簿机械校验（claims-register linter）。

用途
----
把 GOVERNANCE.md §7「主张登记簿」的人眼纪律变成可机械执行的 lint（可挂 CI）：
扫描对外主张面 README 中的数字主张（百分比、分数/计数），逐条判定其是否
① 已登记于 §7（allowlist），或 ② 行内/表格上下文带出处标注。两者皆无 → 违规。

为什么需要
----------
GOVERNANCE §7：「本表是对外数字主张的唯一合法来源。任何 README、文档、PR 描述
中出现的数字主张，若不在本表（或其指向的产物文件）中，即违规。」§3 门禁第 3 条：
「一切文档 → 禁止未实测的提升主张。数字只能来自脚本产物，能被一键复算。」
此前该纪律只靠 code review 人眼维持；本脚本把它机械化：有违规 exit 1，CI 直接红。

判定规则（逐行，仅扫描代码围栏外的正文/表格/HTML）
--------------------------------------------------
1. 主张识别：行内含百分比（``96.0%``，含徽章 URL 编码形式 ``96.0%25``）或
   分数/计数（``480/500``）即视为数字主张行。
2. 合规当且仅当（满足其一）：
   a. 行内数字全部登记于 §7 表格（数值等价比较：96 与 96.0 等同）；
   b. 该行带出处标注：markdown 链接 ``[..](http..)``、非本机 URL、HTML href、
      或「出处」字样；
   c. 该行是 markdown 表格行，且行内出现第三方系统名（Mem0/Zep/MemPalace 等
      对比目标）——引用第三方评测数字的对比行本身就是引用；
   d. 该行所在表格块的相邻（±2 行）脚注/引言含链接（根 README 的 benchmark
      对比表即此形态：表尾 ``> Honest comparisons only — see [..](..)``）。
3. 豁免（有意为之，非放松）：
   - 代码围栏内（```` ``` ````）的行：ASCII 渲染的基准产物输出、示例命令/配置，
     不是作者行文主张；证据本体是 §7 产物列指向的文件（results_*.json、
     FIRST_HOP_NONREGRESSION.md）。--verbose 会列出围栏内识别到的数字以供审计。
   - 行内代码 span（`` `...` ``）与 HTML 布局属性（width/height/style，
     如 ``width="100%"``）：非主张载体。
   - §7 产物/依据列指向的文件本身整体豁免（它们就是证据），若将来加入扫描列表。
4. 退出码：0 = 全部合规；1 = 存在未登记且无出处的数字主张；2 = GOVERNANCE.md
   缺失，或 §7 标题/登记表不存在。

如何登记新主张
--------------
改 GOVERNANCE.md §7 表格，新增一行「主张 | 状态 | 复现命令 | 产物/依据」：
表格行内的百分比、``a/b`` 分数与独立数值（如 96.0、95.8、500Q 的 500）会被本
脚本自动并入 allowlist；产物列里的文件路径自动获得整体豁免。反向不可行：
只改 README 不登记 → 本脚本 exit 1。单字符数字（R@5 的 5、版本号、日期）不进
allowlist（碰撞面太大）；若确需登记请在表中写成百分比或分数形式。

用法
----
    python3 scripts/check_claims.py [--verbose] [--root PATH]

纯标准库，无第三方依赖。新增对外 README 时请同步加进 SCAN_TARGETS。
"""

from __future__ import annotations

import argparse
import fnmatch
import re
import sys
from pathlib import Path

# --------------------------------------------------------------- configuration

GOVERNANCE_FILENAME = "GOVERNANCE.md"

# 对外主张面（存在才扫）。新增对外 README 时在此登记。
SCAN_TARGETS = (
    "README.md",
    "python/README.md",
    "local/README.md",
    "typescript/README.md",
    "openclaw/README.md",
    "setup-cli/README.md",
    "claudecode/README.md",
    "opencode/README.md",
    "browser-extension/README.md",
)

# 第三方对比目标：markdown 表格行内出现这些名字时，行内数字视为已标注出处
# （对比第三方评测数字的行本身就是引用；出处的完整义务由表格脚注/对比文档承担）。
THIRD_PARTY_MARKERS = (
    "Mem0",
    "MemPalace",
    "Zep",
    "Graphiti",
    "OMEGA",
    "Mastra",
    "Supermemory",
    "GPT-4",
    "GPT-5",
)

# 主张模式：百分比（含徽章 URL 编码 96.0%25 中的 "96.0%"）与分数/计数。
PCT_RE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*%")
FRAC_RE = re.compile(r"(?<![\w./%])(\d+)\s*/\s*(\d+)(?![\w./])")

# 出处标记。
MD_LINK_RE = re.compile(r"\[[^\]]*\]\(\s*(https?://[^)\s]+)")
BARE_URL_RE = re.compile(r"(?<![(\[])https?://\S+")
LOCAL_URL_RE = re.compile(r"https?://(?:localhost|127\.0\.0\.1)\S*", re.IGNORECASE)
CITE_WORD = "出处"

# 提取 allowlist 前的清洗。
DATE_RE = re.compile(r"\d{4}-\d{1,2}-\d{1,2}")  # 2026-09-06 之类日期不是主张
TABLE_SEP_RE = re.compile(r"^\s*\|[\s:\-|]*\|\s*$")
STANDALONE_NUM_RE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)*)(?:[a-zA-Z]{1,3})?(?![\w.])")
PATHLIKE_RE = re.compile(r"[A-Za-z0-9_\-\./\*]+\.(?:md|json|jsonl|mjs|txt|log)")

# 扫描前剔除的非主张载体。
LAYOUT_ATTR_RE = re.compile(r"(?i)\b(?:width|height|style)\s*=\s*(?:\"[^\"]*\"|'[^']*')")
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
FENCE_RE = re.compile(r"^\s*(?:```|~~~)")

# §7 标题定位。
SECTION_HEADING_RE = re.compile(r"^#{1,6}\s+7\.\s+")
SECTION_HEADING_KEYWORD = "主张登记簿"


# ------------------------------------------------------------------- §7 解析

def extract_section7(text: str) -> list[str] | None:
    """返回 §7 小节的行列表；找不到标题返回 None。"""
    lines = text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if SECTION_HEADING_RE.match(ln) and SECTION_HEADING_KEYWORD in ln:
            start = i
            break
        if ln.startswith("#") and SECTION_HEADING_KEYWORD in ln:
            start = i
            break
    if start is None:
        return None
    body: list[str] = []
    for ln in lines[start + 1 :]:
        if re.match(r"^#{1,6}\s", ln) or re.match(r"^-{3,}\s*$", ln):
            break
        body.append(ln)
    return body


def extract_table_rows(section: list[str]) -> list[str]:
    rows = [ln for ln in section if ln.lstrip().startswith("|")]
    return [ln for ln in rows if not TABLE_SEP_RE.match(ln)]


def extract_allowlist(rows: list[str]) -> set[float]:
    """从 §7 表格行提取已登记数字（数值等价集合）。

    覆盖三类：百分比、a/b 分数（两侧分别登记）、独立数值（如 96.0 / 95.8 /
    500Q 的 500 / 0.2pp 的 0.2）。日期、版本号（两点以上）、前导零 ID（053/09）、
    单字符整数（R@5 的 5、差 1 题的 1）一律不入集，避免 allowlist 被稀释。
    """
    values: set[float] = set()
    for row in rows:
        cleaned = DATE_RE.sub(" ", row)
        for m in PCT_RE.finditer(cleaned):
            values.add(float(m.group(1)))
        for m in FRAC_RE.finditer(cleaned):
            values.add(float(m.group(1)))
            values.add(float(m.group(2)))
        for m in STANDALONE_NUM_RE.finditer(cleaned):
            tok = m.group(1)
            if "." in tok:
                if tok.count(".") >= 2:  # 版本号，如 transformers.js 3.8.1
                    continue
                values.add(float(tok))
            else:
                if len(tok) > 1 and tok.startswith("0"):  # 前导零 ID，如 f053 / 09
                    continue
                if float(tok) < 10:  # 单字符整数碰撞面太大（R@5、差 1 题）
                    continue
                values.add(float(tok))
    return values


def extract_product_paths(rows: list[str]) -> set[str]:
    """§7「产物/依据」列（第 4 列）指向的文件路径 → 整体豁免对象。"""
    paths: set[str] = set()
    for row in rows:
        cells = [c.strip() for c in row.split("|")]
        # split 后 cells[0] 为空串，产物列为第 4 列即 index 4。
        evidence = cells[4] if len(cells) > 4 else (cells[-1] if cells else "")
        for tok in PATHLIKE_RE.findall(evidence):
            paths.add(tok.strip("./"))
    return paths


# -------------------------------------------------------------- 主张识别与判定

def detect_claims(line: str) -> list[dict]:
    claims: list[dict] = []
    for m in PCT_RE.finditer(line):
        claims.append({"kind": "percent", "text": m.group(0), "numbers": [float(m.group(1))]})
    for m in FRAC_RE.finditer(line):
        claims.append(
            {
                "kind": "fraction",
                "text": m.group(0),
                "numbers": [float(m.group(1)), float(m.group(2))],
            }
        )
    return claims


def has_citation(line: str) -> bool:
    """出处标记：markdown 链接（非本机）、裸 URL（非本机）、HTML href、「出处」。"""
    if CITE_WORD in line:
        return True
    for m in MD_LINK_RE.finditer(line):
        if not LOCAL_URL_RE.match(m.group(1)):
            return True
    without_local = LOCAL_URL_RE.sub(" ", line)
    if BARE_URL_RE.search(without_local):
        return True
    return False


def is_third_party_row(line: str) -> bool:
    return any(marker in line for marker in THIRD_PARTY_MARKERS)


def table_blocks(lines: list[str]) -> list[tuple[int, int]]:
    """连续的以 | 开头的行组成一个表格块（0-based 闭区间）。"""
    row_idx = [i for i, ln in enumerate(lines) if ln.lstrip().startswith("|")]
    blocks: list[tuple[int, int]] = []
    start = prev = None
    for i in row_idx:
        if prev is not None and i == prev + 1:
            prev = i
            continue
        if start is not None:
            blocks.append((start, prev))
        start = prev = i
    if start is not None:
        blocks.append((start, prev))
    return blocks


def block_is_sourced(lines: list[str], s: int, e: int) -> bool:
    """表格块自身或相邻 ±2 行（脚注/引言）含出处标记。"""
    for i in list(range(s, e + 1)) + [s - 1, s - 2, e + 1, e + 2]:
        if 0 <= i < len(lines) and has_citation(lines[i]):
            return True
    return False


def is_product_file(rel: str, products: set[str]) -> bool:
    rel_norm = rel.replace("\\", "/")
    for p in products:
        if rel_norm == p or rel_norm.endswith("/" + p):
            return True
        if "*" in p and (fnmatch.fnmatch(rel_norm, p) or fnmatch.fnmatch(rel_norm, "*/" + p)):
            return True
    return False


# --------------------------------------------------------------------- 扫描

def scan_file(path: Path, rel: str, allowlist: set[float], products: set[str]) -> dict:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    blocks = table_blocks(lines)
    block_of: dict[int, tuple[int, int]] = {}
    for s, e in blocks:
        for i in range(s, e + 1):
            block_of[i] = (s, e)
    sourced = {bi: block_is_sourced(lines, s, e) for bi, (s, e) in enumerate(blocks)}
    block_index_of = {block: bi for bi, block in enumerate(blocks)}

    violations: list[dict] = []
    ledger: list[dict] = []  # 全部识别到的主张（--verbose 用）
    fenced_claims = 0

    in_fence = False
    for idx, raw in enumerate(lines):
        if FENCE_RE.match(raw):
            in_fence = not in_fence
            continue

        work = LAYOUT_ATTR_RE.sub(" ", raw)
        work = INLINE_CODE_RE.sub(" ", work)
        claims = detect_claims(work)

        if in_fence:
            fenced_claims += len(claims)
            for c in claims:
                ledger.append(
                    {
                        "file": rel,
                        "lineno": idx + 1,
                        "raw": raw,
                        "claim": c,
                        "status": "SKIP-FENCE",
                        "reasons": ["代码围栏内（产物渲染/示例，按设计豁免）"],
                    }
                )
            continue

        if not claims:
            continue

        cited = has_citation(raw)
        third_party = is_third_party_row(raw)
        blk = block_of.get(idx)
        blk_sourced = sourced[block_index_of[blk]] if blk is not None else False
        is_table_row = blk is not None

        for c in claims:
            unregistered = [n for n in c["numbers"] if n not in allowlist]
            allowlisted = not unregistered
            reasons = []
            if allowlisted:
                reasons.append("已登记于 §7")
            if cited:
                reasons.append("行内出处（链接/出处标记）")
            if third_party:
                reasons.append("第三方对比行")
            if blk_sourced:
                reasons.append("表格脚注出处")
            ok = allowlisted or cited or third_party or blk_sourced
            status = "OK" if ok else "FAIL"
            if not ok:
                violations.append(
                    {
                        "file": rel,
                        "lineno": idx + 1,
                        "raw": raw,
                        "claim": c,
                        "unregistered": unregistered,
                    }
                )
            ledger.append(
                {
                    "file": rel,
                    "lineno": idx + 1,
                    "raw": raw,
                    "claim": c,
                    "status": status,
                    "reasons": reasons,
                    "unregistered": unregistered,
                }
            )

    return {
        "file": rel,
        "violations": violations,
        "ledger": ledger,
        "fenced_claims": fenced_claims,
    }


# --------------------------------------------------------------------- 输出

def fmt_nums(nums: list[float]) -> str:
    out = []
    for n in nums:
        out.append(str(int(n)) if float(n).is_integer() else str(n))
    return ",".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="GOVERNANCE §7 主张登记簿机械校验：README 数字主张必须已登记或带出处。"
    )
    ap.add_argument("--verbose", action="store_true", help="列出全部识别到的主张及判定依据")
    ap.add_argument("--root", default=None, help="仓库根目录（默认：脚本所在目录的上一级）")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parent.parent
    gov_path = root / GOVERNANCE_FILENAME

    # ---- exit 2 分支：GOVERNANCE.md 缺失 / §7 表不存在
    if not gov_path.is_file():
        print(f"[FATAL] {gov_path} 不存在：无主张登记簿可校验", file=sys.stderr)
        return 2
    section = extract_section7(gov_path.read_text(encoding="utf-8"))
    if section is None:
        print("[FATAL] GOVERNANCE.md 中未找到 §7 主张登记簿标题", file=sys.stderr)
        return 2
    rows = extract_table_rows(section)
    if not rows:
        print("[FATAL] §7 主张登记簿下没有登记表格行", file=sys.stderr)
        return 2

    allowlist = extract_allowlist(rows)
    products = extract_product_paths(rows)

    print("check_claims — GOVERNANCE §7 主张登记簿机械校验")
    print(f"  登记簿: {gov_path} （{len(rows)} 行登记）")
    print(f"  §7 allowlist: {sorted(allowlist)}")
    if products:
        print(f"  §7 产物豁免: {sorted(products)}")

    results = []
    for rel in SCAN_TARGETS:
        f = root / rel
        if not f.is_file():
            print(f"  [skip] {rel}（不存在）")
            continue
        if is_product_file(rel, products):
            print(f"  [skip] {rel}（§7 产物/依据指向的文件，整体豁免）")
            continue
        results.append(scan_file(f, rel, allowlist, products))

    total_claims = sum(len(r["ledger"]) for r in results)
    total_fail = sum(len(r["violations"]) for r in results)
    total_fenced = sum(r["fenced_claims"] for r in results)

    if args.verbose:
        print("\n-- 主张明细（--verbose）--")
        for r in results:
            for item in r["ledger"]:
                c = item["claim"]
                head = f"{item['file']}:{item['lineno']}  {c['kind']} \"{c['text']}\""
                if item["status"] == "SKIP-FENCE":
                    print(f"  [SKIP-FENCE] {head}  {'; '.join(item['reasons'])}")
                elif item["status"] == "OK":
                    print(f"  [OK]         {head}  → {'; '.join(item['reasons'])}")
                else:
                    missed = fmt_nums(item["unregistered"])
                    print(f"  [FAIL]       {head}  → 未登记数字 {missed}，且无出处标注")
        print(f"  （另有 {total_fenced} 条数字位于代码围栏内，按设计豁免，已列入审计明细）")

    print(f"\n扫描 {len(results)} 个主张面文件，识别主张 {total_claims} 条。")

    if total_fail:
        print(f"\n违规 {total_fail} 条（未登记于 §7 且无出处）：")
        for r in results:
            for v in r["violations"]:
                c = v["claim"]
                print(f"  {v['file']}:{v['lineno']}  {c['kind']} \"{c['text']}\""
                      f"（未登记数字: {fmt_nums(v['unregistered'])}）")
                print(f"      | {v['raw'].strip()[:120]}")
        print("\n处理方式：将数字登记进 GOVERNANCE.md §7（附复现命令与产物），"
              "或删除该主张，或补充出处链接。")
        return 1

    print("PASS: 全部数字主张已登记于 §7 或带出处标注。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
