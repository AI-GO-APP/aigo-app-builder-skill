"""
check_update.py — Skill 自我更新檢查

比對本地 `VERSION` 與 GitHub 上的遠端 `VERSION`，有新版時提示更新指令。

設計約束（改動前請先讀）：
- **零相依**：只用標準函式庫，不經 uv／httpx。SessionStart hook 會在任何專案裡跑，
  不能假設 `scripts/.venv` 已建好。
- **永不阻斷**：網路失敗、逾時、遠端格式異常一律靜默跳過並 exit 0。
- **節流**：預設 24 小時內只檢查一次，狀態存在 `~/.aigo/update_check.json`。
- **不自動覆寫**：`--apply` 只在 skill 目錄是 git repo 時做 `pull --ff-only`；
  其餘情況只印出指令，由使用者決定。

用法：
    python check_update.py              # 檢查（含節流），有更新才輸出
    python check_update.py --force      # 忽略節流
    python check_update.py --json       # 機器可讀輸出
    python check_update.py --apply      # 檢查後嘗試就地更新（git 安裝才會實際執行）
"""

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# === 常數 ===
REPO = "AI-GO-APP/aigo-app-builder-skill"
RAW_BASE = f"https://raw.githubusercontent.com/{REPO}/main"
REMOTE_VERSION_URL = f"{RAW_BASE}/VERSION"
REMOTE_CHANGELOG_URL = f"{RAW_BASE}/CHANGELOG.md"

SKILL_DIR = Path(__file__).resolve().parent.parent
STATE_FILE = Path.home() / ".aigo" / "update_check.json"

FETCH_TIMEOUT = 3.0  # 秒；hook 情境下寧可放棄也不要卡住啟動
THROTTLE_SECONDS = 24 * 60 * 60

# ⚠️ 舊版使用者機器上跑的是**他們那一版**的 check_update.py，唯一會被讀到的新內容是
# 遠端 CHANGELOG 的新版那一節、**只取前 CHANGELOG_MAX_LINES 行**。破壞性變更的警語
# 因此必須寫在該節的最前面幾行，不能埋在機制說明後面。改動這個數字前先想清楚這件事。
CHANGELOG_MAX_LINES = 20

# 新版節裡出現這些字樣就視為破壞性變更 → 提示升級為「必須」而非「可選」。
# 用字串比對而非額外的中繼檔案，是為了讓判斷跟著 CHANGELOG 走：寫 changelog 的人
# 不會忘記同步一個他不知道存在的檔案。
BREAKING_MARKERS = ("破壞性", "BREAKING")


def _read_local_version() -> str | None:
    """讀取本地 VERSION（第一行）。檔案不存在或空白回傳 None。"""
    version_file = SKILL_DIR / "VERSION"
    try:
        text = version_file.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text.splitlines()[0].strip() if text else None


def _fetch(url: str) -> str | None:
    """抓取純文字內容。任何失敗都回 None（呼叫端負責靜默處理）。"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "aigo-builder-skill"})
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
            if resp.status != 200:
                return None
            return resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return None


def _parse_version(v: str) -> tuple:
    """
    把 '1.2.3' 轉成可比較的鍵。

    pre-release（如 '1.2.0-rc1'）排在同版號正式版之前，符合 semver 語義。
    """
    base, _, pre = v.partition("-")
    nums = tuple(int(c) if c.isdigit() else 0 for c in base.split("."))
    return (nums, 0 if pre else 1, pre)


def _is_newer(remote: str, local: str) -> bool:
    """遠端是否嚴格新於本地。無法解析時退回字串不相等判斷。"""
    try:
        return _parse_version(remote) > _parse_version(local)
    except TypeError:
        return remote != local


def _load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_state(state: dict) -> None:
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except OSError:
        pass  # 狀態寫不進去只是失去節流，不該影響流程


def _throttled(state: dict) -> bool:
    last = state.get("last_check", 0)
    return isinstance(last, (int, float)) and (time.time() - last) < THROTTLE_SECONDS


def _install_method() -> str:
    """'git'（可就地 pull）或 'copy'（skills CLI 複製安裝）。"""
    return "git" if (SKILL_DIR / ".git").exists() else "copy"


def _update_command(method: str) -> str:
    if method == "git":
        return f'git -C "{SKILL_DIR}" pull --ff-only'
    return "npx skills update"


def _changelog_excerpt(remote_version: str) -> str | None:
    """取遠端 CHANGELOG 中新版那一節，作為變更摘要。"""
    text = _fetch(REMOTE_CHANGELOG_URL)
    if not text:
        return None
    lines = text.splitlines()
    start = next(
        (i for i, ln in enumerate(lines) if ln.startswith("## ") and remote_version in ln),
        None,
    )
    if start is None:
        return None
    excerpt = [lines[start]]
    for ln in lines[start + 1 :]:
        if ln.startswith("## "):
            break
        excerpt.append(ln)
    return "\n".join(excerpt[:CHANGELOG_MAX_LINES]).strip()


def _apply_update(method: str) -> tuple[bool, str]:
    """就地更新。回傳 (是否成功, 訊息)。"""
    if method != "git":
        return False, (
            "此 Skill 非 git 安裝（skills CLI 複製安裝），無法就地 pull。"
            f"請由使用者執行：{_update_command(method)}"
        )
    try:
        result = subprocess.run(
            ["git", "-C", str(SKILL_DIR), "pull", "--ff-only"],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"執行 git pull 失敗：{exc}"
    if result.returncode != 0:
        return False, (
            "git pull --ff-only 失敗（本地可能有未提交的修改或分支已分岔）：\n"
            f"{result.stderr.strip()}"
        )
    return True, result.stdout.strip() or "已更新。"


def check(force: bool = False) -> dict:
    """
    執行檢查，回傳結果字典。

    status: 'skipped'（節流）｜'unknown'（本地無 VERSION 或抓不到遠端）｜
            'current'（已是最新）｜'outdated'（有新版）
    """
    local = _read_local_version()
    if local is None:
        return {"status": "unknown", "reason": "本地找不到 VERSION 檔"}

    state = _load_state()
    if not force and _throttled(state):
        return {"status": "skipped", "local": local}

    remote = _fetch(REMOTE_VERSION_URL)
    if not remote:
        # 離線／GitHub 不可用：不寫入 last_check，下次仍會嘗試
        return {"status": "unknown", "local": local, "reason": "無法取得遠端 VERSION"}
    remote = remote.strip().splitlines()[0].strip()

    state["last_check"] = time.time()
    state["local"] = local
    state["remote"] = remote
    _save_state(state)

    if not _is_newer(remote, local):
        return {"status": "current", "local": local, "remote": remote}

    method = _install_method()
    changelog = _changelog_excerpt(remote)
    return {
        "status": "outdated",
        "local": local,
        "remote": remote,
        "skill_dir": str(SKILL_DIR),
        "install_method": method,
        "update_command": _update_command(method),
        "changelog": changelog,
        "breaking": bool(changelog and any(m in changelog for m in BREAKING_MARKERS)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="檢查 aigo-builder Skill 是否有新版")
    parser.add_argument("--force", action="store_true", help="忽略 24 小時節流")
    parser.add_argument("--json", action="store_true", help="輸出 JSON")
    parser.add_argument("--apply", action="store_true", help="有新版時嘗試就地更新")
    args = parser.parse_args()

    result = check(force=args.force or args.apply)

    if args.apply and result["status"] == "outdated":
        ok, message = _apply_update(result["install_method"])
        result["applied"] = ok
        result["apply_message"] = message

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    # 人類／agent 可讀輸出：只有「有新版」才出聲，其餘保持安靜
    if result["status"] != "outdated":
        return 0

    print(
        f"[aigo-builder] 有新版可用：本地 {result['local']} → 遠端 {result['remote']}"
    )
    if result.get("breaking"):
        print(
            "\n⚠️ 這是**破壞性變更**：不更新會讓平台呼叫直接失敗，"
            "而失敗訊息通常不會指向真正的原因。\n"
            "   請務必告知使用者這一點，不要只當成一般的可選更新。"
        )
    if result.get("changelog"):
        print(f"\n變更摘要：\n{result['changelog']}\n")
    if "applied" in result:
        print(("已更新：" if result["applied"] else "更新未完成：") + result["apply_message"])
        if result["applied"]:
            print("請重新讀取 SKILL.md 以套用新版指令。")
    else:
        print(f"更新指令：{result['update_command']}")
        print("請先告知使用者版本落差並取得同意，不要逕自覆寫本地檔案。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
