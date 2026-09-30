"""aigo_template.py — 模板盤點與「模板當素材」下載（Phase 1.5 §1.0.5／模板起手動線）

模板在本 skill 的動線上是**素材**，不是安裝來源：唯讀取回模板全碼到本機參考目錄，
盤出效果清單拿去拷問，app 一律用 starter 建殼後自行 provision（`references/template-workflow.md`）。
本檔只打**唯讀**端點，不建 app、不建表、不碰外部服務與金鑰。

端點（v1.15.4 核對）：
  GET /api/v1/templates                 清單（builder.access；含 access_mode／setup_schema，不含各 schema）
  GET /api/v1/templates/{slug}          詳情（builder.access；含 data_center_schema／data_references_schema）
  GET /api/v1/templates/{slug}/preview  全碼唯讀預覽（僅需登入；只含 UTF-8 文字檔；不含 `_template.json`）

用法（在工作區內執行，base_url／token 走 aigo_auth）：
    uv run --project scripts python scripts/aigo_template.py list [--suite cnst] [--category operations]
    uv run --project scripts python scripts/aigo_template.py suites
    uv run --project scripts python scripts/aigo_template.py effects <slug>
    uv run --project scripts python scripts/aigo_template.py preview <slug> <本機參考目錄>
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from pathlib import Path, PurePosixPath
from typing import Any

# ctx 暴露的效果面（平台 action_context；`response`／`params` 不是 I/O 效果，不列）
CTX_EFFECT_SURFACES = ("db", "erp", "http", "secrets", "approval", "knowledge", "messaging", "crypto", "csv")

# 預設 starter 兩支是空白腳手架，不是業務模板；盤點時排除
STARTER_SLUGS = frozenset({"starter-internal", "starter-external"})


# ---------------------------------------------------------------------------
# 純函式（離線可測）
# ---------------------------------------------------------------------------

def suite_of(slug: str) -> str:
    """slug 前綴＝產業套組（`cnst-billing` → `cnst`）；沒有連字號的回整個 slug。

    官方 `category` 分類失衡（單一類吃掉大量不同產業），找「有沒有人做過」要看前綴。
    """
    return slug.split("-", 1)[0] if "-" in slug else slug


def group_by_suite(templates: list[dict]) -> dict[str, list[dict]]:
    """依 slug 前綴分組（排除 starter），組內依 slug 排序；組依模板數多到少、同數依前綴。"""
    groups: dict[str, list[dict]] = {}
    for t in templates or []:
        slug = t.get("slug") if isinstance(t, dict) else None
        if not isinstance(slug, str) or not slug or slug in STARTER_SLUGS:
            continue
        groups.setdefault(suite_of(slug), []).append(t)
    for items in groups.values():
        items.sort(key=lambda t: t["slug"])
    return dict(sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])))


def safe_relpath(path: str) -> str | None:
    """VFS 路徑轉成可安全寫入本機的相對路徑；絕對路徑、跳出根目錄或空路徑回 None。"""
    if not isinstance(path, str) or not path or path.startswith("/") or "\\" in path:
        return None
    parts = PurePosixPath(path).parts
    if not parts or any(p in ("..", "") for p in parts):
        return None
    return str(PurePosixPath(*[p for p in parts if p != "."])) or None


def scan_ctx_effects(vfs: dict) -> dict[str, dict[str, list[str]]]:
    """掃 `actions/**/*.py` 的 `ctx.<surface>.<method>(...)` 呼叫。

    回 {surface: {method: [path:line, ...]}}；`ctx.http.call` 的字面 slug 另見 `scan_http_slugs`。
    """
    found: dict[str, dict[str, list[str]]] = {}
    for path, code in sorted((vfs or {}).items()):
        if not (path.startswith("actions/") and path.endswith(".py")) or not isinstance(code, str):
            continue
        try:
            tree = ast.parse(code)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            if (isinstance(f, ast.Attribute) and isinstance(f.value, ast.Attribute)
                    and isinstance(f.value.value, ast.Name) and f.value.value.id == "ctx"
                    and f.value.attr in CTX_EFFECT_SURFACES):
                found.setdefault(f.value.attr, {}).setdefault(f.attr, []).append(f"{path}:{node.lineno}")
    return found


def scan_http_slugs(vfs: dict) -> dict[str, list[str]]:
    """`ctx.http.call("<slug>", ...)` 的字面 slug → 出現位置。與發布閘門同一判定（aigo_publish）。"""
    from aigo_publish import scan_literal_egress_slugs
    literal, _dynamic = scan_literal_egress_slugs(vfs)
    return literal


def declared_effects(vfs: dict) -> list[dict] | None:
    """讀 `_template_meta.json` 的 `effects`（Template Protocol）；沒有或壞掉回 None。"""
    raw = (vfs or {}).get("_template_meta.json")
    if not isinstance(raw, str):
        return None
    try:
        meta = json.loads(raw)
    except ValueError:
        return None
    effects = meta.get("effects") if isinstance(meta, dict) else None
    return effects if isinstance(effects, list) else None


def inventory_effects(vfs: dict, detail: dict | None = None) -> dict[str, Any]:
    """盤出拿去拷問的效果清單。

    有 `effects` 宣告就以宣告為準（source=declared）；沒有就從 schema 與 code 推斷（source=inferred）。
    推斷的來源：詳情的 `data_center_schema`（自建表）、`data_references_schema`（引用）、
    `setup_schema`（金鑰／參數）、actions 裡的 `ctx.*` 呼叫與 `ctx.http.call` 字面 slug。
    `required_egress` 沒有唯讀端點看得到（建 app 時才寫進 `_template.json`），只能靠字面 slug 推。
    """
    detail = detail or {}
    dcs = detail.get("data_center_schema") or {}
    tables = []
    if isinstance(dcs, dict):
        raw_tables = dcs.get("tables", dcs)
        if isinstance(raw_tables, list):
            tables = [t.get("key") or t.get("name") for t in raw_tables if isinstance(t, dict)]
        elif isinstance(raw_tables, dict):
            tables = list(raw_tables.keys())
    refs = []
    for r in detail.get("data_references_schema") or []:
        if isinstance(r, dict):
            refs.append(r.get("table_name") or r.get("table") or r.get("object") or json.dumps(r, ensure_ascii=False))
    setup = detail.get("setup_schema") or {}
    setup_keys = sorted(setup.get("properties", setup).keys()) if isinstance(setup, dict) else []
    declared = declared_effects(vfs)
    return {
        "source": "declared" if declared is not None else "inferred",
        "declared_effects": declared,
        "owned_tables": [t for t in tables if t],
        "data_references": [r for r in refs if r],
        "setup_keys": setup_keys,
        "http_slugs": scan_http_slugs(vfs),
        "ctx_calls": scan_ctx_effects(vfs),
        "has_ports_layer": any(p.startswith("src/ports/") or p == "actions/_shared/ports.py" for p in (vfs or {})),
        "access_mode": detail.get("access_mode"),
    }


def format_inventory(slug: str, inv: dict) -> str:
    lines = [f"模板 {slug}（access_mode={inv.get('access_mode')}；效果來源："
             f"{'_template_meta.json effects 宣告' if inv['source'] == 'declared' else '推斷（模板尚無 effects 宣告）'}）"]
    if inv["declared_effects"]:
        for e in inv["declared_effects"]:
            if isinstance(e, dict):
                lines.append(f"  - {e.get('id')} [{e.get('kind')}] 預設 {e.get('default_binding')}"
                             f"；可替換 {e.get('alternatives') or '—'}")
    if inv["owned_tables"]:
        lines.append(f"  自建表（預設繫結 owned_table）：{', '.join(inv['owned_tables'])}")
    if inv["data_references"]:
        lines.append(f"  預設表引用（platform_table）：{', '.join(inv['data_references'])}")
    if inv["http_slugs"]:
        lines.append("  對外呼叫（http）：" + "; ".join(f"{s}（{', '.join(w)}）" for s, w in inv["http_slugs"].items()))
    if inv["setup_keys"]:
        lines.append(f"  setup_schema 參數／金鑰：{', '.join(inv['setup_keys'])}")
    for surface, methods in inv["ctx_calls"].items():
        lines.append(f"  ctx.{surface}：" + "; ".join(f"{m}×{len(w)}" for m, w in sorted(methods.items())))
    lines.append("  ports 層：" + ("有（非預設繫結＝換 ports 函式實作）" if inv["has_ports_layer"]
                                   else "無（非預設繫結要自己找出所有呼叫點改寫）"))
    return "\n".join(lines)


def write_preview(files: dict, dest: str | os.PathLike) -> list[str]:
    """把 preview 的 files 寫到本機參考目錄。目錄須不存在或為空（不覆蓋任何東西）。

    回寫入的相對路徑；不安全路徑略過。參考目錄**不是** app 專案目錄——app 由 starter 建殼，
    這裡的碼是抄回去改造的素材（`template-workflow.md`）。
    """
    root = Path(dest)
    if root.exists() and any(root.iterdir()):
        raise FileExistsError(f"{root} 已存在且非空——模板素材請放新的空目錄，不要覆蓋 app 專案")
    written = []
    for path, content in sorted((files or {}).items()):
        rel = safe_relpath(path)
        if rel is None or not isinstance(content, str):
            continue
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        written.append(rel)
    return written


# ---------------------------------------------------------------------------
# 網路（唯讀）
# ---------------------------------------------------------------------------

def _get(base_url: str, token: str, path: str, params: dict | None = None) -> Any:
    import httpx
    resp = httpx.get(f"{base_url.rstrip('/')}/api/v1{path}", params=params,
                     headers={"Authorization": f"Bearer {token}"}, timeout=60)
    resp.raise_for_status()
    return resp.json()


def list_templates(base_url: str, token: str, category: str | None = None) -> list[dict]:
    data = _get(base_url, token, "/templates", {"category": category} if category else None)
    return data if isinstance(data, list) else []


def get_template(base_url: str, token: str, slug: str) -> dict:
    return _get(base_url, token, f"/templates/{slug}")


def fetch_template_preview(base_url: str, token: str, slug: str) -> dict[str, str]:
    data = _get(base_url, token, f"/templates/{slug}/preview")
    files = data.get("files") if isinstance(data, dict) else None
    if not isinstance(files, dict):
        raise ValueError(f"preview 回應沒有 files：{slug}")
    return files


def download_template_preview(base_url: str, token: str, slug: str, dest: str) -> list[str]:
    return write_preview(fetch_template_preview(base_url, token, slug), dest)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="aigo_template.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list", help="列出上架模板（可依套組前綴或官方 category 過濾）")
    p.add_argument("--suite")
    p.add_argument("--category")
    sub.add_parser("suites", help="依 slug 前綴列產業套組與模板數")
    p = sub.add_parser("effects", help="盤出某支模板的效果清單（拷問用）")
    p.add_argument("slug")
    p = sub.add_parser("preview", help="把模板全碼下載到本機參考目錄（須不存在或為空）")
    p.add_argument("slug")
    p.add_argument("dest")
    args = ap.parse_args(argv)

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from aigo_auth import find_workspace, get_token, resolve_base_url
    root = str(find_workspace() or ".")
    base_url, token = resolve_base_url(root), get_token(root)

    if args.cmd in ("list", "suites"):
        tpls = list_templates(base_url, token, getattr(args, "category", None))
        groups = group_by_suite(tpls)
        if args.cmd == "suites":
            for suite, items in groups.items():
                print(f"{suite}-\t{len(items)}")
            return 0
        for suite, items in groups.items():
            if args.suite and suite != args.suite:
                continue
            for t in items:
                print(f"{t['slug']}\t{t.get('access_mode')}\t{t.get('category')}\t{t.get('name')}\t{t.get('description') or ''}")
        return 0
    if args.cmd == "effects":
        detail = get_template(base_url, token, args.slug)
        vfs = fetch_template_preview(base_url, token, args.slug)
        print(format_inventory(args.slug, inventory_effects(vfs, detail)))
        return 0
    written = download_template_preview(base_url, token, args.slug, args.dest)
    print(f"已寫入 {len(written)} 個檔案到 {args.dest}（素材，不是 app 專案目錄；非 UTF-8 檔 preview 不回）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
