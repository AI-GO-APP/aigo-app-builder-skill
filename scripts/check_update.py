"""
check_update.py — Skill 自我更新檢查（多安裝感知）

比對本地 `VERSION` 與 GitHub 上的遠端 `VERSION`，有新版時提示更新指令。

設計約束（改動前請先讀）：
- **零相依**：只用標準函式庫，不經 uv／httpx。SessionStart hook 會在任何專案裡跑，
  不能假設 `scripts/.venv` 已建好。
- **永不阻斷**：網路失敗、逾時、遠端格式異常一律靜默跳過並 exit 0。
- **節流管網路、不管比對**：遠端 VERSION 抓一次後快取 3 小時（`remote_cache`），
  但「本地 vs 遠端」的比對**每次都做**——這是多安裝情境的關鍵：任何一份安裝
  刷新快取後，其他安裝（即使在節流窗內）也能立即發現自己落後。
  重複提示另以「同一組 (local, remote) 3 小時內只報一次」抑制，且抑制計時
  只在實際報告時刷新，避免高頻觸發把過期時間無限往後推。
- **多安裝註冊表**：每次執行把自身路徑登記進 `installs`，累積成本機安裝清單；
  `--apply-all` 據此一次更新所有 git 安裝。只認得「跑過本腳本」的安裝，
  沒跑過的副本無從發現。路徑消失時自動剔除。
- **不自動覆寫**：`--apply`／`--apply-all` 只對 git 安裝做 `pull --ff-only`
  （分岔或髒工作區會安全失敗）；複製式安裝（skills CLI）只印出指令，由使用者決定。
- **與舊版共存**：狀態檔頂層的 `last_check`／`local`／`remote` 是 1.16.x 以前的
  腳本在維護的鍵，本版不讀不寫也不刪——尚未更新的舊副本仍靠它們自行節流。

狀態檔 `~/.aigo/update_check.json`（多 session 併發寫入為 last-writer-wins，
偶爾丟一筆註冊可接受，下次執行會補回）：
    {
      "remote_cache": {"version": "1.17.0", "fetched_at": 1788...},
      "installs": {
        "<安裝絕對路徑>": {"local": "1.16.0", "last_seen": 1788...,
                            "last_result": {"local": "...", "remote": "...", "at": ...}}
      }
    }

用法：
    python check_update.py              # 檢查（含節流），有更新才輸出
    python check_update.py --force      # 忽略節流
    python check_update.py --json       # 機器可讀輸出
    python check_update.py --apply      # 有新版時就地更新本安裝（git 安裝才會實際執行）
    python check_update.py --apply-all  # 更新註冊表裡所有落後的 git 安裝
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
THROTTLE_SECONDS = 3 * 60 * 60

# ⚠️ 舊版使用者機器上跑的是**他們那一版**的 check_update.py，唯一會被讀到的新內容是
# 遠端 CHANGELOG 的新版那一節、**只取前 CHANGELOG_MAX_LINES 行**。破壞性變更的警語
# 因此必須寫在該節的最前面幾行，不能埋在機制說明後面。改動這個數字前先想清楚這件事。
CHANGELOG_MAX_LINES = 20

# 新版節裡出現這些字樣就視為破壞性變更 → 提示升級為「必須」而非「可選」。
# 用字串比對而非額外的中繼檔案，是為了讓判斷跟著 CHANGELOG 走：寫 changelog 的人
# 不會忘記同步一個他不知道存在的檔案。
BREAKING_MARKERS = ("破壞性", "BREAKING")


def _read_version_at(skill_dir: Path) -> str | None:
    """讀取指定安裝的 VERSION（第一行）。檔案不存在或空白回傳 None。"""
    try:
        # utf-8-sig：Windows 編輯器常帶 BOM，混進版本字串會毀掉 semver 比對
        text = (skill_dir / "VERSION").read_text(encoding="utf-8-sig").strip()
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
        state = json.loads(STATE_FILE.read_text(encoding="utf-8-sig"))
        return state if isinstance(state, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_state(state: dict) -> None:
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except OSError:
        pass  # 狀態寫不進去只是失去節流與註冊，不該影響流程


def _installs(state: dict) -> dict:
    installs = state.get("installs")
    if not isinstance(installs, dict):
        installs = {}
        state["installs"] = installs
    return installs


def _register_install(state: dict, local: str) -> None:
    """登記自身並剔除已消失的安裝。last_result 保留（報告抑制要用）。"""
    installs = _installs(state)
    for path in list(installs):
        if not Path(path).exists():
            del installs[path]
    entry = installs.setdefault(str(SKILL_DIR), {})
    entry["local"] = local
    entry["last_seen"] = time.time()


def _resolve_remote(state: dict, force: bool) -> str | None:
    """
    取得遠端版本：快取未過期（3 小時）直接用；否則抓網路並刷新快取。

    抓取失敗時退回**過期**快取——版本號只會前進，舊快取頂多漏報更新，
    不會誤報；離線時能靠它維持多安裝偵測。
    """
    cache = state.get("remote_cache")
    cached_version = None
    if isinstance(cache, dict):
        v, at = cache.get("version"), cache.get("fetched_at")
        if isinstance(v, str) and v:
            cached_version = v
            if (
                not force
                and isinstance(at, (int, float))
                and (time.time() - at) < THROTTLE_SECONDS
            ):
                return v
    fetched = _fetch(REMOTE_VERSION_URL)
    if fetched:
        remote = fetched.strip().splitlines()[0].strip()
        if remote:
            state["remote_cache"] = {"version": remote, "fetched_at": time.time()}
            return remote
    return cached_version


def _already_reported(state: dict, local: str, remote: str) -> bool:
    rec = _installs(state).get(str(SKILL_DIR), {}).get("last_result")
    if not isinstance(rec, dict):
        return False
    at = rec.get("at")
    return (
        rec.get("local") == local
        and rec.get("remote") == remote
        and isinstance(at, (int, float))
        and (time.time() - at) < THROTTLE_SECONDS
    )


def _install_method(skill_dir: Path = SKILL_DIR) -> str:
    """'git'（可就地 pull）或 'copy'（skills CLI 複製安裝）。"""
    return "git" if (skill_dir / ".git").exists() else "copy"


def _update_command(method: str, skill_dir: Path = SKILL_DIR) -> str:
    if method == "git":
        return f'git -C "{skill_dir}" pull --ff-only'
    return "npx skills update"


def _apply_all_command() -> str:
    return f'python "{Path(__file__).resolve()}" --apply-all'


def _survey_other_installs(state: dict, remote: str) -> list[dict]:
    """回報註冊表裡**其他**安裝的即時狀態（版本從磁碟現讀，不信任登記值）。"""
    out = []
    for path in _installs(state):
        if path == str(SKILL_DIR):
            continue
        skill_dir = Path(path)
        local = _read_version_at(skill_dir)
        if local is None:
            continue
        out.append(
            {
                "path": path,
                "local": local,
                "install_method": _install_method(skill_dir),
                "outdated": _is_newer(remote, local),
            }
        )
    return out


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


def _pull(skill_dir: Path) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(skill_dir), "pull", "--ff-only"],
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


def _apply_update(method: str) -> tuple[bool, str]:
    """就地更新本安裝。回傳 (是否成功, 訊息)。"""
    if method != "git":
        return False, (
            "此 Skill 非 git 安裝（skills CLI 複製安裝），無法就地 pull。"
            f"請由使用者執行：{_update_command(method)}"
        )
    return _pull(SKILL_DIR)


def _apply_all(state: dict, remote: str) -> list[dict]:
    """
    更新註冊表裡所有落後的安裝（含本安裝）。

    每筆：{"path", "local", "action": updated|manual|up-to-date|failed, "message"}
    """
    results = []
    for path in sorted(_installs(state)):
        skill_dir = Path(path)
        local = _read_version_at(skill_dir)
        if local is None:
            continue
        if not _is_newer(remote, local):
            results.append({"path": path, "local": local, "action": "up-to-date", "message": ""})
            continue
        method = _install_method(skill_dir)
        if method != "git":
            results.append(
                {
                    "path": path,
                    "local": local,
                    "action": "manual",
                    "message": f"複製式安裝，請由使用者執行：{_update_command(method, skill_dir)}",
                }
            )
            continue
        ok, message = _pull(skill_dir)
        results.append(
            {"path": path, "local": local, "action": "updated" if ok else "failed", "message": message}
        )
    return results


def check(force: bool = False) -> dict:
    """
    執行檢查，回傳結果字典。

    status: 'skipped'（同一組版本差 3 小時內已報過）｜'unknown'（本地無 VERSION
            或遠端不可得）｜'current'（已是最新）｜'outdated'（有新版）
    """
    local = _read_version_at(SKILL_DIR)
    if local is None:
        return {"status": "unknown", "reason": "本地找不到 VERSION 檔"}

    state = _load_state()
    _register_install(state, local)

    remote = _resolve_remote(state, force)
    if remote is None:
        _save_state(state)  # 註冊仍要留下
        return {"status": "unknown", "local": local, "reason": "無法取得遠端 VERSION"}

    if not force and _already_reported(state, local, remote):
        _save_state(state)
        return {"status": "skipped", "local": local, "remote": remote}

    # 只在實際報告時刷新抑制計時，高頻觸發才不會把過期時間無限往後推
    _installs(state)[str(SKILL_DIR)]["last_result"] = {
        "local": local,
        "remote": remote,
        "at": time.time(),
    }
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
        "apply_all_command": _apply_all_command(),
        "other_installs": _survey_other_installs(state, remote),
        "install_count": len(_installs(state)),
        "changelog": changelog,
        "breaking": bool(changelog and any(m in changelog for m in BREAKING_MARKERS)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="檢查 aigo-builder Skill 是否有新版")
    parser.add_argument("--force", action="store_true", help="忽略 3 小時節流")
    parser.add_argument("--json", action="store_true", help="輸出 JSON")
    parser.add_argument("--apply", action="store_true", help="有新版時就地更新本安裝")
    parser.add_argument(
        "--apply-all", action="store_true", help="更新註冊表裡所有落後的 git 安裝"
    )
    args = parser.parse_args()

    result = check(force=args.force or args.apply or args.apply_all)

    if args.apply_all:
        # 本安裝已是最新、但其他註冊安裝落後的情況也要處理，所以不看 status
        if result.get("remote"):
            result["apply_all_results"] = _apply_all(_load_state(), result["remote"])
        else:
            result["apply_all_results"] = []
            result.setdefault("reason", "無法取得遠端 VERSION，略過更新")
    elif args.apply and result["status"] == "outdated":
        ok, message = _apply_update(result["install_method"])
        result["applied"] = ok
        result["apply_message"] = message

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.apply_all:
        for r in result.get("apply_all_results", []):
            label = {
                "updated": "已更新",
                "up-to-date": "已是最新",
                "manual": "需手動",
                "failed": "失敗",
            }[r["action"]]
            line = f"[{label}] {r['path']}（{r['local']}）"
            if r["message"]:
                line += f"：{r['message']}"
            print(line)
        if any(r["action"] == "updated" for r in result.get("apply_all_results", [])):
            print("請重新讀取 SKILL.md 以套用新版指令。")
        elif result.get("reason"):
            print(result["reason"])
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
        print(f"更新指令（本安裝）：{result['update_command']}")
        outdated_others = [i for i in result["other_installs"] if i["outdated"]]
        if outdated_others:
            print("本機另有其他已註冊安裝同樣落後：")
            for i in outdated_others:
                print(f"  - {i['path']}（{i['local']}，{i['install_method']} 安裝）")
            print(f"一次更新本機所有 git 安裝：{result['apply_all_command']}")
        if result.get("install_count", 1) > 1:
            print(
                f"ℹ️ 本機註冊了 {result['install_count']} 份 skill 安裝。"
                "建議只留 user scope 一份（租戶與 app 都在各工作區的 .aigo/ 裡，不需要多份 skill）。"
            )
        print("請先告知使用者版本落差並取得同意，不要逕自覆寫本地檔案。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
