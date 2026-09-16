"""
check_docs.py — Skill 文件結構自檢（零相依、離線可跑）

驗的是「文件結構」而不是內容對錯：
1. SKILL.md 行數 ≤ MAX_SKILL_LINES（Anthropic skill 規範建議 500 行）
2. 被引用的 references/ 與 resources/ 檔案都存在（斷鏈會讓 agent 讀不到規則）
3. 超過 TOC_THRESHOLD 行的 reference 都有目錄
   （Claude 預覽長檔時可能只讀開頭，沒目錄就看不到全貌）
3.5 每份 reference 都能從 SKILL.md 直接找到
   （官方建議引用只保持一層：只能靠別的 reference 才發現的檔案，Claude 常只讀開頭）
3.6 文件裡的 `xxx.md §N` 指向真的存在
   （章節重編號時最容易斷，斷了 agent 會讀到錯的地方或放棄）
4. 搬移不掉東西：與 git 基準版（預設 main）比，SKILL.md 移除的實質行必須能在
   新版主檔或任何 reference 裡找到；找不到的列出來讓人逐條判斷

用法：
    python scripts/check_docs.py              # 全部檢查（第 4 項需要 git）
    python scripts/check_docs.py --base HEAD~1
    python scripts/check_docs.py --skip-moved # 只跑 1–3

退出碼：0 全過；1 有硬失敗（1–3 項）；第 4 項只警告不擋——搬移時刻意刪掉重複內容是合法的。
"""

from __future__ import annotations

import argparse
import glob
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# 500 來自 Anthropic 的 skill authoring best practices（"Keep SKILL.md under 500 lines"）
MAX_SKILL_LINES = 500
# 100 同一份文件的 table-of-contents 建議門檻
TOC_THRESHOLD = 100
# 25 字以下的行多是標題、表格分隔線、單詞清單，比對會有大量假警報
MIN_MEANINGFUL_CHARS = 25


def _norm(s: str) -> str:
    """去掉清單符號與所有空白，只留實質文字——排版變動不該算內容遺失。"""
    return re.sub(r"\s+", "", re.sub(r"^[\s\->*\d.|#]+", "", s))


def check_skill_length() -> list[str]:
    n = len((ROOT / "SKILL.md").read_text(encoding="utf-8").splitlines())
    if n > MAX_SKILL_LINES:
        return [f"SKILL.md {n} 行，超過建議上限 {MAX_SKILL_LINES}——把細節搬到 references/"]
    print(f"✅ SKILL.md {n} 行（上限 {MAX_SKILL_LINES}）")
    return []


def check_links() -> list[str]:
    errs = []
    pattern = re.compile(r"(?:references|resources)/[A-Za-z0-9_.-]+\.(?:md|json)")
    for src in ["SKILL.md", "CONTEXT.md", *glob.glob("references/*.md", root_dir=ROOT)]:
        text = (ROOT / src).read_text(encoding="utf-8")
        for target in sorted(set(pattern.findall(text))):
            if not (ROOT / target).exists():
                errs.append(f"{src} 指向不存在的檔案：{target}")
    if not errs:
        print("✅ 文件引用無斷鏈")
    return errs


def check_toc() -> list[str]:
    errs = []
    for path in sorted((ROOT / "references").glob("*.md")):
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) <= TOC_THRESHOLD:
            continue
        # 目錄要在開頭附近才有用（預覽只讀前面）
        if not any(l.strip().startswith("## 目錄") for l in lines[:40]):
            errs.append(f"{path.relative_to(ROOT)} 有 {len(lines)} 行但開頭沒有『## 目錄』")
    if not errs:
        print(f"✅ 超過 {TOC_THRESHOLD} 行的 reference 都有目錄")
    return errs


ALIAS = {"dev-guide": "custom-app-dev-guide.md", "dev guide": "custom-app-dev-guide.md"}
SECTION_REF = re.compile(r"`?([a-z-]+(?:\.md)?)`?\s*(?:的\s*)?§\s*(\d+(?:\.\d+)*)")


def _docs() -> dict[str, str]:
    docs = {p.name: p.read_text(encoding="utf-8") for p in (ROOT / "references").glob("*.md")}
    for extra in ("SKILL.md", "CONTEXT.md"):
        docs[extra] = (ROOT / extra).read_text(encoding="utf-8")
    return docs


def check_orphan_refs() -> list[str]:
    """每份 reference 都要從 SKILL.md 直接指到——一層深。"""
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    errs = []
    for path in sorted((ROOT / "references").glob("*.md")):
        name = path.name
        if not re.search(rf"(references/)?{re.escape(name)}|`{re.escape(name[:-3])}`", skill):
            errs.append(f"{name} 在 SKILL.md 裡找不到——只能靠別的 reference 發現，加進參考文件表")
    if not errs:
        print("✅ 每份 reference 都能從 SKILL.md 直接找到")
    return errs


def check_section_refs() -> list[str]:
    """`xxx.md §N` 指到的章節必須存在。"""
    docs = _docs()
    sections = {}
    for name, text in docs.items():
        found = set()
        for m in re.finditer(r"^#{2,4}\s*§?(\d+(?:\.\d+)*)", text, re.M):
            found.add(m.group(1))
        sections[name] = found

    errs, total = [], 0
    for src, text in docs.items():
        for m in SECTION_REF.finditer(text):
            raw, num = m.group(1), m.group(2)
            target = ALIAS.get(raw, raw if raw.endswith(".md") else raw + ".md")
            if target not in docs:
                continue  # 不是文件名（例如 `§25` 前面接的是別的詞）
            total += 1
            if num not in sections[target]:
                errs.append(f"{src} 指向 {target} §{num}，但該章節不存在")
    if not errs:
        print(f"✅ {total} 個 `檔名 §章節` 指向都存在")
    return errs


def check_moved_content(base: str) -> list[str]:
    try:
        old = subprocess.run(
            ["git", "show", f"{base}:SKILL.md"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout.splitlines()
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"⚠️  跳過搬移檢查（讀不到基準版 {base}）：{e}")
        return []

    haystack = _norm(
        (ROOT / "SKILL.md").read_text(encoding="utf-8")
        + "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "references").glob("*.md"))
    )
    missing = [l.strip() for l in old
               if len(_norm(l)) >= MIN_MEANINGFUL_CHARS and _norm(l) not in haystack]
    if missing:
        print(f"⚠️  與 {base} 相比，{len(missing)} 行實質內容不在新版主檔或任何 reference 裡。")
        print("    刻意刪掉的重複內容不算問題——逐條確認那些事實在別處還找得到：")
        for line in missing[:40]:
            print(f"      ✗ {line[:110]}")
        if len(missing) > 40:
            print(f"      …另外 {len(missing) - 40} 行")
    else:
        print(f"✅ 與 {base} 相比沒有內容遺失")
    return []


def main() -> int:
    ap = argparse.ArgumentParser(description="Skill 文件結構自檢")
    ap.add_argument("--base", default="main", help="搬移檢查的比對基準（預設 main）")
    ap.add_argument("--skip-moved", action="store_true", help="不跑搬移檢查")
    args = ap.parse_args()

    errs = check_skill_length() + check_links() + check_toc() + check_orphan_refs() + check_section_refs()
    if not args.skip_moved:
        errs += check_moved_content(args.base)

    if errs:
        print("\n❌ 未通過：")
        for e in errs:
            print(f"   - {e}")
        return 1
    print("\n✅ 全部通過")
    return 0


if __name__ == "__main__":
    sys.exit(main())
