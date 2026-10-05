"""
aigo_cron_health.py — App 排程（App Cron）健康檢查（★ 唯讀：只打 GET）

用法：
    # 單一 app（App 開發面，builder.access 即可讀）
    uv run --project scripts python scripts/aigo_cron_health.py --app <app-id>
    # 斷言某個 action 有排程
    uv run --project scripts python scripts/aigo_cron_health.py --app <app-id> --expect-action <action_name>
    # 全租戶（租戶營運面，需 settings.read）
    uv run --project scripts python scripts/aigo_cron_health.py --all

端點與欄位見 references/event-triggers.md §2。本工具**絕不**呼叫 run-now、toggle、
PATCH、POST、DELETE——要重啟或手動觸發請人到 Builder 該 App「排程」分頁處理。

`--expect-action` 的適用對象：**切換後的新 app（新的 prod）**，或**負責人明確確認要跑排程的 UAT**。
UAT 預設應該**零排程**（uat-environment.md §3 步驟 9）——不要對一般 UAT 用它，
UAT 有排程反而要確認是不是誤建。

每條排程檢查（error 的判定規則：last_status=error 時看 consecutive_errors——
< 5 是 🟡（偶發，觀察），≥ 5 是 🔴（逼近 10 次自動暫停）；timeout 一律 🔴）：
  🔴 暫停原因為 consecutive_403／consecutive_errors／tier（平台自動暫停），或任何未知原因
     ——不會自動恢復，要人工重啟（§2.8）
  🔴 last_status 為 timeout；或 error 且 consecutive_errors ≥ 5
  🔴 lastcall 超過 2 倍間隔沒動（stale），且 nextcall 不在未來
  🔴 consecutive_errors ≥ 5（10 次自動暫停）、consecutive_403 ≥ 1（2 次自動暫停）
  🔴 --expect-action 指定的 action 沒有排程
  🟡 暫停原因為 manual 或沒有原因——確認是否刻意
  🟡 last_status 為 skipped（重疊被跳過，§2.7；大量出現代表間隔比執行時間短）
  🟡 last_status 為 error 且 consecutive_errors < 5
  🟡 stale 但 nextcall 在未來（可能剛重啟）；間隔算不出來（無法判斷 stale）
  🟡 consecutive_errors 1–4、從未執行過、nextcall 空（新建 5 分鐘內屬正常）

結束碼：0＝沒有紅燈；1＝**只**代表有紅燈（含 --expect-action 缺排程）；
2＝其他一切意外（登入失敗、讀不到排程、回應形狀不符）＝無法判斷，不等於沒有排程。
加 `--json` 輸出機器可讀結果。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))

NOTE = "平台的 success 只代表 action 有回應，工作本身的結果要看 app 自己的執行結果表"
ERROR_PAUSE_AT = 10   # event-triggers.md §2.8
ERROR_WARN_AT = 5
FORBIDDEN_403_PAUSE_AT = 2
AUTO_PAUSE_REASONS = {"consecutive_403", "consecutive_errors", "tier"}
OPERATOR_PAUSE_REASONS = {"manual", None}
# 每種 schedule_kind 的最長間隔（分鐘）；monthly 取 31 天
WEEKDAYS = dict(enumerate("日一二三四五六"))  # 0=週日（§2.3）
KIND_MINUTES = {"hourly": 60, "daily": 1440, "weekly": 10080, "monthly": 44640}


def fetch_crons(base_url: str, token: str, app_id: str | None) -> list[dict]:
    """有 app_id 走 App 開發面，否則走租戶營運面。失敗時 raise。

    不沿用 `aigo_review.fetch_app_crons`：那支失敗時回 None、讓 review 繼續跑；
    這裡是閘門，要分得出「讀不到」（結束碼 2）與「真的沒有排程」（--expect-action 判紅），
    也要拿到 HTTP 狀態碼給 403／404 的處置提示。

    分頁：`GET /api/v1/app-crons` 實查回傳整個 list、不吃 limit／page／skip 參數、
    沒有 total／next 欄位或分頁 header，所以不翻頁。若日後改成帶 total／next 的物件，
    這裡會當成形狀不符（結束碼 2），不會默默少算。
    """
    import httpx
    url = (f"{base_url.rstrip('/')}/api/v1/builder/apps/{app_id}/crons" if app_id
           else f"{base_url.rstrip('/')}/api/v1/app-crons")
    resp = httpx.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict):
        items = data.get("items")
        more = data.get("next") or data.get("next_page") or data.get("has_more")
        total = data.get("total")
        if more or (isinstance(total, int) and isinstance(items, list) and total > len(items)):
            raise ValueError("排程列表是分頁回應，本工具尚未支援翻頁")
        data = items
    if not isinstance(data, list):
        raise ValueError("排程列表回應形狀不符")
    if app_id:
        data = [c for c in data if str(c.get("app_id", app_id)) == str(app_id)]
    return data


def interval_minutes(cron: dict) -> int | None:
    kind = cron.get("schedule_kind")
    if kind == "every_n_minutes":
        fields = cron.get("schedule_fields")
        n = fields.get("n") if isinstance(fields, dict) else None
        return n if isinstance(n, int) and not isinstance(n, bool) and n > 0 else None
    return KIND_MINUTES.get(kind)


def _parse_time(value) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _count(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def assess(cron: dict, now: datetime) -> list[dict]:
    """回傳這條排程的發現項：[{level: red|yellow, code, message}]。"""
    findings: list[dict] = []

    def add(level: str, code: str, message: str) -> None:
        findings.append({"level": level, "code": code, "message": message})

    active = cron.get("active")
    reason = cron.get("paused_reason")
    errors = _count(cron.get("consecutive_errors"))
    forbidden = _count(cron.get("consecutive_403"))
    status = cron.get("last_status")

    if active is False:
        if reason in AUTO_PAUSE_REASONS:
            add("red", "paused", f"已被平台自動暫停（{reason}），不會自動恢復，修好原因後要人工重啟")
        elif reason in OPERATOR_PAUSE_REASONS:
            add("yellow", "paused", f"已暫停（{reason or '未註明原因'}），不會自動恢復；確認是否刻意")
        else:
            add("red", "paused", f"已暫停（{reason}：未知原因，視為需處理），不會自動恢復")

    if status == "timeout":
        add("red", "last_status", "最後一次 timeout")
    elif status == "error":
        level = "red" if errors >= ERROR_WARN_AT else "yellow"
        add(level, "last_status", f"最後一次 error（連續 {errors} 次）")
    elif status == "skipped":
        add("yellow", "last_status", "最後一次 skipped（上一發還在跑，重疊被跳過）")
    elif status not in (None, "success"):
        add("yellow", "last_status", f"最後一次狀態 {status}")

    if errors >= ERROR_WARN_AT:
        add("red", "consecutive_errors", f"連續錯誤 {errors} 次（{ERROR_PAUSE_AT} 次自動暫停）")
    elif errors > 0:
        add("yellow", "consecutive_errors", f"連續錯誤 {errors} 次（{ERROR_PAUSE_AT} 次自動暫停）")
    if forbidden > 0:
        add("red", "consecutive_403",
            f"連續 403 {forbidden} 次（{FORBIDDEN_403_PAUSE_AT} 次自動暫停；app 下架或 action 消失／停用）")

    if active is not False:
        last = _parse_time(cron.get("lastcall"))
        interval = interval_minutes(cron)
        if last is None:
            add("yellow", "never_ran", "尚未執行過")
        elif interval is None:
            add("yellow", "interval_unknown",
                f"算不出間隔（schedule_kind={cron.get('schedule_kind')}），無法判斷是否 stale")
        else:
            age_min = (now - last).total_seconds() / 60
            if age_min > 2 * interval:
                nxt = _parse_time(cron.get("nextcall"))
                msg = f"上次執行已 {age_min:.0f} 分鐘前，超過 2 倍間隔（{interval} 分鐘）"
                if nxt is not None and nxt > now:
                    add("yellow", "stale", msg + "；nextcall 在未來，可能剛重啟")
                else:
                    add("red", "stale", msg)
        if not cron.get("nextcall"):
            add("yellow", "nextcall_empty", "nextcall 空（新建或剛改時程 5 分鐘內屬正常，勿重建）")
    return findings


def check(crons: list[dict], now: datetime, app_id: str | None = None,
          expect_actions: list[str] | None = None) -> dict:
    items = []
    for c in crons:
        items.append({
            "id": c.get("id"),
            "app_id": c.get("app_id"),
            "name": c.get("name"),
            "action": c.get("action_name"),
            "schedule": {"kind": c.get("schedule_kind"), "fields": c.get("schedule_fields"),
                         "timezone": c.get("timezone")},
            "active": c.get("active"),
            "paused_reason": c.get("paused_reason"),
            "last_status": c.get("last_status"),
            "lastcall": c.get("lastcall"),
            "nextcall": c.get("nextcall"),
            "consecutive_errors": c.get("consecutive_errors"),
            "consecutive_403": c.get("consecutive_403"),
            "warnings": c.get("warnings") or [],
            "findings": assess(c, now),
        })
    missing = []
    for action in expect_actions or []:
        if not any(i["action"] == action for i in items):
            missing.append(action)
    red = bool(missing) or any(f["level"] == "red" for i in items for f in i["findings"])
    return {"app_id": app_id, "checked_at": now.isoformat(), "items": items,
            "missing_actions": missing, "red": red, "note": NOTE}


def _two(v) -> str:
    """hh／mm 補零；不是數字就原樣印，None 印 ?，絕不 crash。"""
    if v is None:
        return "?"
    try:
        return f"{int(v):02}"
    except (TypeError, ValueError):
        return str(v)


def _schedule_text(s: dict) -> str:
    fields = s.get("fields") if isinstance(s.get("fields"), dict) else {}
    kind = s.get("kind")
    if kind == "every_n_minutes":
        txt = f"每 {fields.get('n')} 分"
    elif kind == "hourly":
        txt = f"每小時第 {fields.get('minute')} 分"
    elif kind in ("daily", "weekly", "monthly"):
        prefix = {"daily": "每天", "weekly": f"每週{WEEKDAYS.get(fields.get('weekday'), fields.get('weekday'))}", "monthly": f"每月{fields.get('day')}日"}[kind]
        txt = f"{prefix} {_two(fields.get('hh'))}:{_two(fields.get('mm'))}"
    else:
        txt = f"{kind} {fields}"
    return f"{txt} {s.get('timezone') or ''}".strip()


def format_text(result: dict) -> str:
    out = []
    scope = f"app {result['app_id']}" if result["app_id"] else "全租戶"
    out.append(f"排程健康檢查：{scope}（{len(result['items'])} 條）")
    for i in result["items"]:
        levels = {f["level"] for f in i["findings"]}
        mark = "🔴" if "red" in levels else "🟡" if "yellow" in levels else "🟢"
        app = "" if result["app_id"] else f"app={str(i['app_id'])[:8]} "
        out.append(f"{mark} {app}{i['action']}（{i['name']}）  {_schedule_text(i['schedule'])}  "
                   f"active={i['active']}  last={i['last_status']}  lastcall={i['lastcall']}  "
                   f"nextcall={i['nextcall']}  errors={i['consecutive_errors']}  403={i['consecutive_403']}")
        for f in i["findings"]:
            out.append(f"     {'🔴' if f['level'] == 'red' else '🟡'} {f['message']}")
        for w in i["warnings"]:
            out.append(f"     ⚠️ 平台警告：{str(w)[:200]}")
    for action in result["missing_actions"]:
        out.append(f"🔴 找不到 action「{action}」的排程——排程是後台資料、不在 VFS 裡（event-triggers.md §2.1），"
                   "新 app 要另建；UAT 預設不建（uat-environment.md §3 步驟 9）")
    if not result["items"] and not result["missing_actions"]:
        out.append("（沒有排程）")
    out.append("")
    out.append(f"註：{NOTE}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="aigo_cron_health.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=os.environ.get("AIGO_PROJECT_ROOT", "."), help="工作區（預設從目前目錄往上找）")
    scope = ap.add_mutually_exclusive_group(required=True)
    scope.add_argument("--app", help="Custom App id（App 開發面端點）")
    scope.add_argument("--all", action="store_true", help="全租戶排程（需 settings.read）")
    ap.add_argument("--expect-action", action="append", default=[],
                    help="斷言此 action 有排程（可重複；需搭配 --app）。用於切換後的新 app（新 prod）"
                         "或負責人明確確認要跑排程的 UAT；UAT 預設零排程")
    ap.add_argument("--json", action="store_true", help="輸出 JSON")
    a = ap.parse_args(argv)
    if a.expect_action and not a.app:
        ap.error("--expect-action 需要搭配 --app")

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
        crons = fetch_crons(base_url, token, a.app)
    except httpx.HTTPStatusError as e:
        code = e.response.status_code
        hint = ""
        if code == 403 and not a.app:
            hint = "（全租戶列表需要 settings.read；開發者請改用 --app）"
        elif code == 404:
            hint = "（app 不存在或你不在它的 access_role_ids 內）"
        print(f"❌ 讀不到排程：HTTP {code}{hint}——無法判斷，不等於沒有排程", file=sys.stderr)
        return 2
    except (httpx.HTTPError, OSError, ValueError) as e:
        print(f"❌ 讀不到排程（{type(e).__name__}）——無法判斷，不等於沒有排程", file=sys.stderr)
        return 2

    result = check(crons, datetime.now(timezone.utc), a.app, a.expect_action)
    print(json.dumps(result, ensure_ascii=False, indent=2) if a.json else format_text(result))
    return 1 if result["red"] else 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    try:
        sys.exit(main())
    except Exception as e:  # 任何意外都是「無法判斷」（2），不能和紅燈的 1 混在一起
        print(f"❌ 意外錯誤（{type(e).__name__}；無法判斷）", file=sys.stderr)
        sys.exit(2)
