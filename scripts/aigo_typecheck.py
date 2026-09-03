"""
aigo_typecheck.py — 發布前的 TypeScript 語意檢查（tsc --noEmit）

平台 compile 走 esbuild，**只轉譯不驗型別**：`const` 在宣告前被使用（TDZ、TS2448）、
重複宣告、用到未定義名稱……這些 compile 全綠，發布後 runtime 直接白畫面，
而錯誤堆疊只有 minified 變數名與 esm.sh 的 React 排程呼叫鏈（repo issue #35）。
平台的 Builder AI 有 `check_types` 工具做同一件事，但沒有 REST 端點可讓腳本呼叫，
所以這裡在本機重做一次：把 src 落到臨時目錄、補上 esbuild loader 涵蓋的資產宣告、
用 `npx tsc --noEmit` 跑，只把**會炸 runtime 的語意錯誤**列為阻擋。

用法：
    uv run --project scripts python scripts/aigo_typecheck.py [專案目錄] [--strict] [--json]

- 預設**只阻擋**「宣告前使用」「重複宣告」「找不到名稱」這類必炸 runtime 的錯誤（見 BLOCKING）；
  缺 `@types/react` 等造成的 TS2307／TS7026 視為環境噪音只列不擋
- `--strict`：所有 tsc 錯誤都阻擋（本機有完整 node_modules 時用）
- 需要 Node ≥ 18 與 npx；沒有就印提示並回 0（不擋流程，但 SKILL Phase 4 會要求用戶知情）
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TSC_VERSION = "typescript@5"
TIMEOUT = 120

# esbuild loader 涵蓋的資產匯入（對齊平台 typecheck.py）——tsc 需要 ambient 宣告
ASSET_DECLARATIONS = """\
declare module '*.css';
declare module '*.scss';
declare module '*.svg' { const src: string; export default src; }
declare module '*.png' { const src: string; export default src; }
declare module '*.jpg' { const src: string; export default src; }
declare module '*.jpeg' { const src: string; export default src; }
declare module '*.gif' { const src: string; export default src; }
declare module '*.webp' { const src: string; export default src; }
declare module '*.json' { const value: any; export default value; }
"""

# 對齊平台 esbuild 參數：target es2020 / jsx automatic / bundler 解析
TSCONFIG = {
    "compilerOptions": {
        "target": "ES2020",
        "module": "ESNext",
        "moduleResolution": "bundler",
        "jsx": "react-jsx",
        "noEmit": True,
        "skipLibCheck": True,
        "esModuleInterop": True,
        "resolveJsonModule": True,
        "allowJs": True,
        "strict": False,
        "noImplicitAny": False,
        "forceConsistentCasingInFileNames": True,
    },
    "include": ["**/*.ts", "**/*.tsx"],
    "exclude": ["node_modules", "dist"],
}

# 一定會在 runtime 炸的語意錯誤——不論環境有沒有型別套件都成立
BLOCKING: dict[str, str] = {
    "TS2448": "宣告前使用（TDZ）——runtime 會 ReferenceError: Cannot access 'X' before initialization",
    "TS2454": "變數在賦值前被使用",
    "TS2451": "同一區塊重複宣告 let/const",
    "TS2300": "重複識別字",
    "TS2304": "找不到名稱（未 import 或打錯字）——runtime ReferenceError",
    "TS2552": "找不到名稱（有相似名稱建議）——runtime ReferenceError",
    "TS1005": "語法錯誤",
    "TS1128": "語法錯誤（缺少宣告或陳述）",
    "TS1109": "語法錯誤（缺少運算式）",
}
# 缺型別套件時的預期噪音（沒有 node_modules 就一定會出現）
NOISE = {"TS2307", "TS2875", "TS7026", "TS7016", "TS2792", "TS6142", "TS7006", "TS7031"}

ERR_RE = re.compile(r"^(.+?)\((\d+),(\d+)\): error (TS\d+): (.*)$")
GLOBAL_RE = re.compile(r"^error (TS\d+): (.*)$")

SRC_EXT = (".ts", ".tsx")
SKIP_DIRS = {"node_modules", "dist", ".aigo", ".git", "__pycache__", "actions"}


def collect_sources(project: Path) -> list[Path]:
    out = []
    for p in project.rglob("*"):
        if any(part in SKIP_DIRS for part in p.relative_to(project).parts):
            continue
        if p.is_file() and p.suffix in SRC_EXT:
            out.append(p)
    return out


def _npx() -> str | None:
    return shutil.which("npx") or shutil.which("npx.cmd")


def run_typecheck(project: str = ".", strict: bool = False) -> dict:
    """回 {available, blocking:[…], other:[…], noise:[…], raw}。"""
    project_path = Path(project).resolve()
    sources = collect_sources(project_path)
    if not sources:
        return {"available": True, "blocking": [], "other": [], "noise": [], "raw": "", "note": "沒有 .ts/.tsx 檔"}
    npx = _npx()
    if not npx or not shutil.which("node"):
        return {"available": False, "blocking": [], "other": [], "noise": [], "raw": "",
                "note": "找不到 node／npx——裝 Node.js ≥ 18 後再跑；或改用 Builder AI 的 check_types"}

    with tempfile.TemporaryDirectory(prefix="aigo-tsc-") as tmp:
        tmpdir = Path(tmp)
        for src in sources:
            rel = src.relative_to(project_path)
            dst = tmpdir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
        (tmpdir / "aigo-assets.d.ts").write_text(ASSET_DECLARATIONS, encoding="utf-8")
        (tmpdir / "tsconfig.json").write_text(json.dumps(TSCONFIG, indent=2), encoding="utf-8")
        # 若專案自己有 node_modules（本機開發），借用它的型別套件
        local_nm = project_path / "node_modules"
        if local_nm.is_dir():
            try:
                os.symlink(local_nm, tmpdir / "node_modules", target_is_directory=True)
            except OSError:
                pass
        cmd = [npx, "-y", "-p", TSC_VERSION, "tsc", "-p", "tsconfig.json", "--pretty", "false"]
        try:
            proc = subprocess.run(cmd, cwd=tmpdir, capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", timeout=TIMEOUT, shell=(os.name == "nt"))
        except subprocess.TimeoutExpired:
            return {"available": True, "blocking": [], "other": [], "noise": [], "raw": "",
                    "note": f"tsc 超過 {TIMEOUT} 秒未完成"}
        raw = (proc.stdout or "") + (proc.stderr or "")

    blocking, other, noise = [], [], []
    for line in raw.splitlines():
        line = line.strip()
        m = ERR_RE.match(line)
        if m:
            item = {"file": m.group(1).replace("\\", "/"), "line": int(m.group(2)), "col": int(m.group(3)),
                    "code": m.group(4), "message": m.group(5)}
        else:
            g = GLOBAL_RE.match(line)
            if not g:
                continue
            item = {"file": "", "line": 0, "col": 0, "code": g.group(1), "message": g.group(2)}
        code = item["code"]
        if code in BLOCKING:
            item["why"] = BLOCKING[code]
            blocking.append(item)
        elif code in NOISE and not strict:
            noise.append(item)
        else:
            (blocking if strict else other).append(item)
    return {"available": True, "blocking": blocking, "other": other, "noise": noise, "raw": raw[:20000]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="發布前 TypeScript 語意檢查（tsc --noEmit）")
    ap.add_argument("project", nargs="?", default=".")
    ap.add_argument("--strict", action="store_true", help="所有 tsc 錯誤都阻擋（需完整 node_modules）")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    res = run_typecheck(a.project, strict=a.strict)
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 1 if res["blocking"] else 0
    if not res["available"]:
        print(f"ℹ️  typecheck 略過：{res['note']}")
        return 0
    if res.get("note"):
        print(f"ℹ️  {res['note']}")
    if res["blocking"]:
        head = ("個 tsc 錯誤（--strict：全部阻擋）" if a.strict
                else "個會炸 runtime 的語意錯誤（compile 不會擋，發布後白畫面）")
        print(f"❌ {len(res['blocking'])} {head}：")
        for e in res["blocking"]:
            loc = f"{e['file']}:{e['line']}:{e['col']}" if e["file"] else "(全域)"
            print(f"   {loc}  {e['code']}  {e['message']}")
            if e.get("why"):
                print(f"      → {e['why']}")
    else:
        print("✅ 沒有會炸 runtime 的語意錯誤")
    if res["other"]:
        print(f"⚠️  另有 {len(res['other'])} 個型別錯誤（不擋發布，建議修）：")
        for e in res["other"][:20]:
            print(f"   {e['file']}:{e['line']}:{e['col']}  {e['code']}  {e['message'][:120]}")
    if res["noise"]:
        codes = sorted({e["code"] for e in res["noise"]})
        print(f"ℹ️  {len(res['noise'])} 筆環境噪音已忽略（{', '.join(codes)}：本機無 @types/react 等套件所致）")
    return 1 if res["blocking"] else 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    sys.exit(main())
