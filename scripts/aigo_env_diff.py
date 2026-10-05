"""
aigo_env_diff.py — 比對 Hosted App 的 runtime-settings 環境變數（★ 唯讀，絕不印值）

兩種用法：
  1. 兩個 Hosted App 互比（例如 prod 對 UAT）：
       uv run --project scripts python scripts/aigo_env_diff.py --a <hosted-id> --b <hosted-id>
  2. 單一 app 對「必要 key 清單」（一行一顆 key，`#` 之後是註解）：
       uv run --project scripts python scripts/aigo_env_diff.py --app <hosted-id> --expect required-env.txt

     清單來源是 hosted-apps.md §4 的 env 對帳表，**只放**「目標位置＝Hosted runtime-settings」且
     處置**不是**「不搬」「退役」的列。`AIGO_*` 與 `PORT` 是平台注入、不在 runtime-settings 裡，
     不要列；清單裡出現時會警告並略過，不算缺席。

只打 `GET /api/v1/hosted-apps/{id}/runtime-settings`。這支 GET 回的是**明文值**——
本工具只輸出 key 名、有無、是否為空、`env_availability`、兩邊值是否相同；
「是否相同」以記憶體內雜湊比對，雜湊本身與任何前綴都**不輸出、不落檔、不記 log**。

另列兩邊的 `always_on`／`persistent_disk`。

摘要：只在 A／只在 B／A 為空／B 為空／兩邊值相同。
★ 「兩邊值相同」是發現項不是好消息：prod 與 UAT 共用同一把密鑰，UAT 出事就是 prod 出事
（uat-environment.md）。網址、開關這類值相同可能合理，要逐顆判斷。

結束碼：0＝正常；1＝**只**代表 `--expect` 有 key 缺席或為空（可當交付閘門）；
2＝其他一切意外（登入失敗、清單檔讀不到、讀不到設定、回應形狀不符）＝無法判斷。
加 `--json` 輸出機器可讀結果（同樣不含值與雜湊）。
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


def _platform_injected(key: str) -> bool:
    """平台注入、不在 runtime-settings 裡的 key（hosted-apps.md §4 保留清單）。"""
    return key == "PORT" or key.startswith("AIGO_")


def fetch_runtime_settings(base_url: str, token: str, hosted_id: str) -> dict:
    """讀 Hosted App 的 runtime-settings。回傳原始 dict（含明文值，**呼叫端不得輸出**）。"""
    import httpx
    resp = httpx.get(
        f"{base_url.rstrip('/')}/api/v1/hosted-apps/{hosted_id}/runtime-settings",
        headers={"Authorization": f"Bearer {token}"}, timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    # env_vars 整個缺席＝形狀不符（無法判斷），不能當成「沒有 env」；null 也一樣
    if not isinstance(data, dict) or not isinstance(data.get("env_vars"), dict):
        raise ValueError("runtime-settings 回應形狀不符（缺 env_vars 或不是物件）")
    return data


def _is_empty(value) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _digest(value) -> bytes:
    """只在記憶體內比對用；回傳值不得輸出。"""
    raw = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).digest()


def _availability(settings: dict, key: str) -> str:
    avail = settings.get("env_availability") or {}
    return avail.get(key) or "runtime"  # 缺漏視為 runtime（hosted-apps.md §4）


def _app_flags(settings: dict) -> dict:
    return {"always_on": settings.get("always_on"), "persistent_disk": settings.get("persistent_disk")}


def diff_settings(a: dict, b: dict) -> dict:
    """兩個 runtime-settings 互比。結果不含任何值或雜湊。"""
    env_a = a.get("env_vars") or {}
    env_b = b.get("env_vars") or {}
    rows = []
    for key in sorted(set(env_a) | set(env_b)):
        in_a, in_b = key in env_a, key in env_b
        row = {
            "key": key,
            "a": {"present": in_a, "empty": in_a and _is_empty(env_a[key]),
                  "availability": _availability(a, key) if in_a else None},
            "b": {"present": in_b, "empty": in_b and _is_empty(env_b[key]),
                  "availability": _availability(b, key) if in_b else None},
            "same_value": None,
        }
        if in_a and in_b and not row["a"]["empty"] and not row["b"]["empty"]:
            row["same_value"] = hmac.compare_digest(_digest(env_a[key]), _digest(env_b[key]))
        rows.append(row)
    summary = {
        "only_in_a": [r["key"] for r in rows if r["a"]["present"] and not r["b"]["present"]],
        "only_in_b": [r["key"] for r in rows if r["b"]["present"] and not r["a"]["present"]],
        "empty_in_a": [r["key"] for r in rows if r["a"]["empty"]],
        "empty_in_b": [r["key"] for r in rows if r["b"]["empty"]],
        "same_value": [r["key"] for r in rows if r["same_value"] is True],
        "availability_differs": [r["key"] for r in rows if r["a"]["present"] and r["b"]["present"]
                                 and r["a"]["availability"] != r["b"]["availability"]],
    }
    return {"mode": "diff", "apps": {"a": _app_flags(a), "b": _app_flags(b)}, "rows": rows, "summary": summary}


def parse_expect(text: str) -> tuple[list[str], list[str], list[str]]:
    """解析必要 key 清單：一行一顆，`#` 之後是註解。

    回傳 (keys, 格式不合的行, 平台注入而略過的 key)。
    """
    keys, invalid, injected = [], [], []
    for line in text.splitlines():
        token = line.split("#", 1)[0].strip()
        if not token:
            continue
        token = token.split()[0]
        if KEY_RE.match(token) and _platform_injected(token):
            if token not in injected:
                injected.append(token)
        elif KEY_RE.match(token):
            if token not in keys:
                keys.append(token)
        else:
            invalid.append(token)
    return keys, invalid, injected


def check_expect(settings: dict, expected: list[str]) -> dict:
    """單一 app 對必要 key 清單。結果不含任何值。"""
    env = settings.get("env_vars") or {}
    rows = []
    for key in expected:
        present = key in env
        rows.append({"key": key, "present": present, "empty": present and _is_empty(env[key]),
                     "availability": _availability(settings, key) if present else None})
    summary = {
        "missing": [r["key"] for r in rows if not r["present"]],
        "empty": [r["key"] for r in rows if r["empty"]],
        "not_in_list": sorted(set(env) - set(expected)),
    }
    return {"mode": "expect", "apps": {"app": _app_flags(settings)}, "rows": rows, "summary": summary}


def _flag(v) -> str:
    return "?" if v is None else ("true" if v else "false")


def _side(s: dict) -> str:
    if not s["present"]:
        return "缺席"
    return f"{'空值' if s['empty'] else '有值'}/{s['availability']}"


def format_text(result: dict, labels: dict[str, str]) -> str:
    out = []
    for side, flags in result["apps"].items():
        out.append(f"[{side}] {labels.get(side, '')}  always_on={_flag(flags['always_on'])}  "
                   f"persistent_disk={_flag(flags['persistent_disk'])}")
    out.append("")
    s = result["summary"]
    if result["mode"] == "diff":
        width = max([len(r["key"]) for r in result["rows"]] + [3])
        out.append(f"{'KEY':<{width}}  {'A':<14} {'B':<14} 比對")
        for r in result["rows"]:
            if r["same_value"] is True:
                cmp = "相同 ⚠️"
            elif r["same_value"] is False:
                cmp = "不同"
            else:
                cmp = "-"
            out.append(f"{r['key']:<{width}}  {_side(r['a']):<14} {_side(r['b']):<14} {cmp}")
        out.append("")
        out.append("摘要")
        for name, label in (("only_in_a", "只在 A"), ("only_in_b", "只在 B"), ("empty_in_a", "A 為空"),
                            ("empty_in_b", "B 為空"), ("same_value", "兩邊值相同"),
                            ("availability_differs", "env_availability 不同")):
            out.append(f"  {label}（{len(s[name])}）：{', '.join(s[name]) or '—'}")
        if s["same_value"]:
            out.append("  ⚠️ 兩邊值相同的 key 逐顆判斷：密鑰類（token、secret、password、私鑰、DB 連線）"
                       "在 prod 與 UAT 共用是發現項，UAT 應換一把；網址或開關相同可能合理。")
    else:
        width = max([len(r["key"]) for r in result["rows"]] + [3])
        for r in result["rows"]:
            mark = "❌" if (not r["present"] or r["empty"]) else "✅"
            out.append(f"{mark} {r['key']:<{width}}  {_side(r)}")
        out.append("")
        out.append(f"缺席（{len(s['missing'])}）：{', '.join(s['missing']) or '—'}")
        out.append(f"空值（{len(s['empty'])}）：{', '.join(s['empty']) or '—'}")
        out.append(f"app 有、清單沒列（{len(s['not_in_list'])}）：{', '.join(s['not_in_list']) or '—'}"
                   "（確認是否該補進對帳表或該退役）")
        if s["missing"] or s["empty"]:
            out.append("❌ 尚缺未清空：不得對外交付（hosted-apps.md §4）。請負責人到「環境變數」tab 設定，值不要貼進對話。")
    out.append("")
    out.append("註：本工具不輸出任何值；build／both 的 key 改值後要重新建置部署才生效。")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="aigo_env_diff.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=os.environ.get("AIGO_PROJECT_ROOT", "."), help="工作區（預設從目前目錄往上找）")
    ap.add_argument("--a", help="Hosted App id（A，例如 prod）")
    ap.add_argument("--b", help="Hosted App id（B，例如 UAT）")
    ap.add_argument("--app", help="Hosted App id（搭配 --expect）")
    ap.add_argument("--expect", help="必要 key 清單檔（一行一顆，# 註解）。只放對帳表中目標位置＝Hosted "
                    "runtime-settings、處置不是「不搬」「退役」的列；AIGO_*／PORT 是平台注入，會警告並略過")
    ap.add_argument("--json", action="store_true", help="輸出 JSON（不含值與雜湊）")
    a = ap.parse_args(argv)

    if a.a and a.b and not (a.app or a.expect):
        mode = "diff"
    elif a.app and a.expect and not (a.a or a.b):
        mode = "expect"
    else:
        ap.error("用法擇一：--a <id> --b <id>，或 --app <id> --expect <file>")

    expected: list[str] = []
    if mode == "expect":
        try:
            text = Path(a.expect).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            print(f"❌ 讀不到清單檔（{type(e).__name__}）", file=sys.stderr)
            return 2
        expected, invalid, injected = parse_expect(text)
        if injected:
            print(f"⚠️ 平台注入的 key 不在 runtime-settings 裡，已略過（不算缺席）：{', '.join(injected)}",
                  file=sys.stderr)
        if invalid:
            print(f"⚠️ 清單中有不合 key 格式的行（已略過）：{', '.join(invalid)}", file=sys.stderr)
        if not expected:
            print("❌ 清單裡沒有任何 key", file=sys.stderr)
            return 2

    import httpx
    from aigo_auth import get_token, resolve_base_url
    try:
        token = get_token(a.root)
        base_url = resolve_base_url(a.root)
    except (httpx.HTTPError, OSError, RuntimeError) as e:
        code = getattr(getattr(e, "response", None), "status_code", None)
        print(f"❌ 登入／取得 token 失敗（{f'HTTP {code}' if code else type(e).__name__}；無法判斷）"
              "——用 aigo_auth.py status 檢查租戶與憑證設定", file=sys.stderr)
        return 2
    try:
        if mode == "diff":
            result = diff_settings(fetch_runtime_settings(base_url, token, a.a),
                                   fetch_runtime_settings(base_url, token, a.b))
            labels = {"a": a.a, "b": a.b}
        else:
            result = check_expect(fetch_runtime_settings(base_url, token, a.app), expected)
            labels = {"app": a.app}
    except httpx.HTTPStatusError as e:
        # 只印狀態碼：錯誤回應不轉印，避免任何設定內容外流
        print(f"❌ 讀不到 runtime-settings：HTTP {e.response.status_code}（無法判斷，不是「沒有 env」）",
              file=sys.stderr)
        return 2
    except (httpx.HTTPError, OSError, ValueError) as e:
        print(f"❌ 讀不到 runtime-settings（{type(e).__name__}；無法判斷）", file=sys.stderr)
        return 2

    if a.json:
        result["ids"] = labels
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_text(result, labels))
    if mode == "expect" and (result["summary"]["missing"] or result["summary"]["empty"]):
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    try:
        sys.exit(main())
    except Exception as e:  # 任何意外都是「無法判斷」（2），不能和缺 key 的 1 混在一起
        print(f"❌ 意外錯誤（{type(e).__name__}；無法判斷）", file=sys.stderr)
        sys.exit(2)
