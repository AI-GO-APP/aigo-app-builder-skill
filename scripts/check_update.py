"""
check_update.py — Skill 自我更新（多安裝感知、發現新版即強制同步）

比對本地 `VERSION` 與 GitHub 上的遠端 `VERSION`；遠端較新時，**不詢問、直接把本機
所有已註冊安裝強制同步到遠端 main**，本地修改一律被覆蓋。

設計約束（改動前請先讀）：
- **零相依**：只用標準函式庫，不經 uv／httpx。SessionStart hook 會在任何專案裡跑，
  不能假設 `scripts/.venv` 已建好。
- **永不阻斷**：網路失敗、逾時、遠端格式異常一律靜默跳過並 exit 0。
- **節流管網路、不管比對**：遠端 VERSION 抓一次後快取 3 小時（`remote_cache`），
  但「本地 vs 遠端」的比對**每次都做**——這是多安裝情境的關鍵：任何一份安裝
  刷新快取後，其他安裝（即使在節流窗內）也能立即發現自己落後。
  同步失敗另以「同一份安裝、同一個遠端版本 3 小時內只重試一次」抑制，
  避免離線時每個 session 都重打一次網路。同步成功後本地＝遠端，自然不再觸發。
- **多安裝註冊表**：每次執行把自身路徑登記進 `installs`，累積成本機安裝清單；
  發現新版時據此一次同步所有落後的安裝。只認得「跑過本腳本」的安裝，
  沒跑過的副本無從發現。路徑消失時自動剔除。
- **強制覆蓋，不徵詢**：
  - git 安裝：`git fetch origin main` → `git reset --hard FETCH_HEAD`。分岔、髒工作區、
    本地 commit 全部被遠端 main 取代。git 指令失敗（例如沒裝 git）時退回 zip 鏡像。
  - 複製式安裝（skills CLI）：下載遠端 `main.zip`，鏡像覆蓋到安裝目錄——遠端有的檔案
    全部寫入，本地多出來的檔案刪除（`PRESERVE_NAMES` 例外）。
- **唯一不碰的是開發用副本**：本地版本**高於**遠端、或 git 安裝**不在 main／master 分支**，
  代表這是正在改 skill 的工作區而不是安裝——強制同步會毀掉未合併的工作，一律略過並標示。
  這不是給使用者保留本地修改的後門：要改 skill 內容，走 repo 的 PR。
- **與舊版共存**：狀態檔頂層的 `last_check`／`local`／`remote` 是 1.16.x 以前的
  腳本在維護的鍵，本版不讀不寫也不刪——尚未更新的舊副本仍靠它們自行節流。

狀態檔 `~/.aigo/update_check.json`（可用環境變數 `AIGO_UPDATE_STATE_FILE` 改位置，
測試用；多 session 併發寫入為 last-writer-wins，偶爾丟一筆註冊可接受，下次執行會補回）：
    {
      "remote_cache": {"version": "1.28.0", "fetched_at": 1788...},
      "installs": {
        "<安裝絕對路徑>": {"local": "1.27.0", "last_seen": 1788...,
                            "last_sync": {"remote": "1.28.0", "ok": false, "at": 1788...}}
      }
    }

用法：
    python check_update.py               # 檢查（含節流）；有新版就同步所有安裝，有動作才輸出
    python check_update.py --force       # 忽略節流
    python check_update.py --json        # 機器可讀輸出
    python check_update.py --check-only  # 只報告不同步（維護者／CI 用，不是給使用者跳過更新的）
    （--apply／--apply-all 仍接受，等同預設行為，保留給舊文件相容）
"""

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

# === 常數 ===
REPO = "AI-GO-APP/aigo-app-builder-skill"
REPO_GIT_URL = f"https://github.com/{REPO}.git"
RAW_BASE = f"https://raw.githubusercontent.com/{REPO}/main"
REMOTE_VERSION_URL = f"{RAW_BASE}/VERSION"
REMOTE_CHANGELOG_URL = f"{RAW_BASE}/CHANGELOG.md"
REMOTE_ARCHIVE_URL = f"https://github.com/{REPO}/archive/refs/heads/main.zip"

SKILL_DIR = Path(__file__).resolve().parent.parent
STATE_FILE = Path(
    os.environ.get("AIGO_UPDATE_STATE_FILE") or (Path.home() / ".aigo" / "update_check.json")
)

FETCH_TIMEOUT = 3.0  # 秒；VERSION／CHANGELOG 這種小檔，hook 情境下寧可放棄也不要卡住啟動
ARCHIVE_TIMEOUT = 30.0  # 秒；main.zip 較大，只在確定要同步時才抓
GIT_TIMEOUT = 90  # 秒
THROTTLE_SECONDS = 3 * 60 * 60

# 分支名在這裡面的 git 安裝才會被強制同步；其他分支＝開發用副本
SYNC_BRANCHES = ("main", "master")

# 鏡像覆蓋時不刪、不寫的名字（任一路徑片段命中即保留）：
# .git／.venv 是安裝本身的基礎設施，.aigo／.env 是使用者的憑證與設定
PRESERVE_NAMES = frozenset(
    {".git", ".venv", "__pycache__", ".aigo", ".claude", ".env", "node_modules"}
)

# ⚠️ 舊版使用者機器上跑的是**他們那一版**的 check_update.py，唯一會被讀到的新內容是
# 遠端 CHANGELOG 的新版那一節、**只取前 CHANGELOG_MAX_LINES 行**。破壞性變更的警語
# 因此必須寫在該節的最前面幾行，不能埋在機制說明後面。改動這個數字前先想清楚這件事。
CHANGELOG_MAX_LINES = 20

# 新版節裡出現這些字樣就視為破壞性變更。1.28.0 起發現新版會直接同步，這個旗標只在
# 同步**失敗**時還有意義——提醒 agent 不能把失敗輕描淡寫成可選更新。
BREAKING_MARKERS = ("破壞性", "BREAKING")


# ---------------------------------------------------------------------------
# 基礎 I/O
# ---------------------------------------------------------------------------


def _read_version_at(skill_dir: Path) -> str | None:
    """讀取指定安裝的 VERSION（第一行）。檔案不存在或空白回傳 None。"""
    try:
        # utf-8-sig：Windows 編輯器常帶 BOM，混進版本字串會毀掉 semver 比對
        text = (skill_dir / "VERSION").read_text(encoding="utf-8-sig").strip()
    except OSError:
        return None
    return text.splitlines()[0].strip() if text else None


def _fetch_bytes(url: str, timeout: float) -> bytes | None:
    """抓取原始內容。任何失敗都回 None（呼叫端負責靜默處理）。"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "aigo-builder-skill"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            return resp.read()
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return None


def _fetch(url: str) -> str | None:
    data = _fetch_bytes(url, FETCH_TIMEOUT)
    return None if data is None else data.decode("utf-8", errors="replace")


def _parse_version(v: str) -> tuple:
    """
    把 '1.2.3' 轉成可比較的鍵。

    pre-release（如 '1.2.0-rc1'）排在同版號正式版之前，符合 semver 語義。
    """
    base, _, pre = v.partition("-")
    nums = tuple(int(c) if c.isdigit() else 0 for c in base.split("."))
    return (nums, 0 if pre else 1, pre)


def _is_newer(a: str, b: str) -> bool:
    """a 是否嚴格新於 b。無法解析時退回字串不相等判斷。"""
    try:
        return _parse_version(a) > _parse_version(b)
    except TypeError:
        return a != b


# ---------------------------------------------------------------------------
# 狀態檔
# ---------------------------------------------------------------------------


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
    """登記自身並剔除已消失的安裝。last_sync 保留（失敗重試抑制要用）。"""
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


def _recently_failed(state: dict, path: str, remote: str) -> bool:
    """這份安裝對同一個遠端版本是否在 3 小時內同步失敗過（避免離線時每個 session 重打網路）。"""
    rec = _installs(state).get(path, {}).get("last_sync")
    if not isinstance(rec, dict) or rec.get("ok"):
        return False
    at = rec.get("at")
    return (
        rec.get("remote") == remote
        and isinstance(at, (int, float))
        and (time.time() - at) < THROTTLE_SECONDS
    )


def _record_sync(state: dict, path: str, remote: str, ok: bool) -> None:
    _installs(state).setdefault(path, {})["last_sync"] = {
        "remote": remote,
        "ok": ok,
        "at": time.time(),
    }


# ---------------------------------------------------------------------------
# 安裝型態判斷
# ---------------------------------------------------------------------------


def _install_method(skill_dir: Path = SKILL_DIR) -> str:
    """'git'（可就地 reset）或 'copy'（skills CLI 複製安裝）。"""
    return "git" if (skill_dir / ".git").exists() else "copy"


def _git(skill_dir: Path, *args: str) -> tuple[int, str, str]:
    """執行 git 指令。git 不存在或逾時視為非零回傳。"""
    try:
        result = subprocess.run(
            ["git", "-C", str(skill_dir), *args],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, "", f"執行 git 失敗：{exc}"
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def _git_branch(skill_dir: Path) -> str | None:
    """目前分支名；detached HEAD 或 git 不可用回 None。"""
    rc, out, _ = _git(skill_dir, "symbolic-ref", "--short", "-q", "HEAD")
    return out if rc == 0 and out else None


def _dev_checkout_reason(skill_dir: Path, local: str, remote: str) -> str | None:
    """
    判斷這份副本是不是「開發用」而非「安裝」。是 → 回傳原因字串；否 → None。

    兩個訊號：本地版本高於遠端（維護者已 bump 但尚未發布），或 git 副本不在 main／master
    （功能分支、worktree、detached HEAD）。命中任一就不強制同步，否則會毀掉未合併的工作。
    """
    if _is_newer(local, remote):
        return f"本地 {local} 高於遠端 {remote}，視為開發用副本"
    if _install_method(skill_dir) == "git":
        branch = _git_branch(skill_dir)
        if branch not in SYNC_BRANCHES:
            shown = branch or "detached HEAD"
            return f"git 分支為 {shown}（不在 {'/'.join(SYNC_BRANCHES)}），視為開發用副本"
    return None


# ---------------------------------------------------------------------------
# 強制同步
# ---------------------------------------------------------------------------


def _force_sync_git(skill_dir: Path) -> tuple[bool, str]:
    """
    git 安裝：fetch 遠端 main 後 reset --hard。

    先試 `origin main`；origin 不存在或指向別處時直接用官方 URL fetch。
    reset --hard 只動已追蹤檔案，未追蹤檔（.venv、.aigo 等 gitignore 項目）不受影響。
    """
    rc, _, err = _git(skill_dir, "fetch", "--quiet", "origin", "main")
    if rc != 0:
        rc, _, err2 = _git(skill_dir, "fetch", "--quiet", REPO_GIT_URL, "main")
        if rc != 0:
            return False, f"git fetch 失敗：{err2 or err}"
    rc, _, err = _git(skill_dir, "reset", "--hard", "--quiet", "FETCH_HEAD")
    if rc != 0:
        return False, f"git reset --hard 失敗：{err}"
    # 未追蹤檔也清掉，與 zip 鏡像同義；不加 -x 所以 gitignore 的 .venv 等留著，
    # PRESERVE_NAMES 再額外排除（.claude/ 沒被 gitignore，裡面可能有 worktree）
    excludes = [arg for name in sorted(PRESERVE_NAMES) for arg in ("-e", name)]
    rc, _, err = _git(skill_dir, "clean", "-fdq", *excludes)
    if rc != 0:
        return True, f"git reset --hard 至遠端 main（未追蹤檔清理失敗：{err}）"
    return True, "git reset --hard 至遠端 main"


def _archive_entries(data: bytes) -> dict[str, bytes] | None:
    """
    把 GitHub archive zip 攤成 {相對路徑: 內容}。

    GitHub 的 zip 外層固定多一層 `<repo>-main/`，這裡剝掉；目錄項目與 PRESERVE_NAMES
    命中的路徑不收。格式異常回 None。
    """
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return None
    entries: dict[str, bytes] = {}
    for info in zf.infolist():
        if info.is_dir():
            continue
        parts = Path(info.filename).parts
        if len(parts) < 2:  # 頂層沒有 <repo>-main/ 包裹，不是 GitHub archive
            return None
        rel = Path(*parts[1:])
        if any(p in PRESERVE_NAMES for p in rel.parts):
            continue
        entries[rel.as_posix()] = zf.read(info)
    return entries or None


def _mirror_into(skill_dir: Path, entries: dict[str, bytes]) -> int:
    """
    把 entries 鏡像到 skill_dir：遠端有的全部寫入，本地多出來的刪掉（PRESERVE_NAMES 例外）。

    先寫後刪，中途失敗最多留下多餘檔案，不會少檔。回傳寫入的檔案數。
    """
    written = 0
    for rel, content in entries.items():
        target = skill_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        written += 1

    keep = set(entries)
    for root, dirs, files in os.walk(skill_dir, topdown=True):
        dirs[:] = [d for d in dirs if d not in PRESERVE_NAMES]
        root_path = Path(root)
        for name in files:
            if name in PRESERVE_NAMES:
                continue
            rel = (root_path / name).relative_to(skill_dir).as_posix()
            if rel not in keep:
                try:
                    (root_path / name).unlink()
                except OSError:
                    pass
    # 清掉刪空的目錄（由深到淺）
    for root, dirs, files in os.walk(skill_dir, topdown=False):
        root_path = Path(root)
        if root_path == skill_dir or any(p in PRESERVE_NAMES for p in root_path.relative_to(skill_dir).parts):
            continue
        try:
            root_path.rmdir()  # 非空會丟 OSError，正好跳過
        except OSError:
            pass
    return written


def _force_sync_zip(skill_dir: Path) -> tuple[bool, str]:
    """複製式安裝（或 git 指令失敗時的退路）：下載遠端 main.zip 鏡像覆蓋。"""
    data = _fetch_bytes(REMOTE_ARCHIVE_URL, ARCHIVE_TIMEOUT)
    if data is None:
        return False, "下載遠端 main.zip 失敗（離線或逾時）"
    entries = _archive_entries(data)
    if entries is None:
        return False, "遠端 main.zip 格式異常"
    # 先在暫存目錄驗證能整包寫出，再動真正的安裝目錄，避免半套覆蓋
    with tempfile.TemporaryDirectory(prefix="aigo-skill-") as tmp:
        try:
            _mirror_into(Path(tmp), entries)
        except OSError as exc:
            return False, f"展開 main.zip 失敗：{exc}"
    try:
        n = _mirror_into(skill_dir, entries)
    except OSError as exc:
        return False, f"覆寫安裝目錄失敗：{exc}"
    return True, f"以遠端 main.zip 鏡像覆蓋（{n} 個檔案）"


def _force_sync(skill_dir: Path) -> tuple[bool, str]:
    """就地強制同步一份安裝。回傳 (是否成功, 訊息)。"""
    if _install_method(skill_dir) == "git":
        ok, message = _force_sync_git(skill_dir)
        if ok:
            return True, message
        ok2, message2 = _force_sync_zip(skill_dir)
        return ok2, f"{message}；改用 zip 鏡像→{message2}"
    return _force_sync_zip(skill_dir)


def _sync_all(state: dict, remote: str, force: bool) -> list[dict]:
    """
    同步註冊表裡所有落後的安裝（含本安裝）。

    每筆：{"path", "local", "install_method", "action", "message"}
    action：synced｜up-to-date｜dev-skip｜throttled｜failed
    """
    results = []
    for path in sorted(_installs(state)):
        skill_dir = Path(path)
        local = _read_version_at(skill_dir)
        if local is None:
            continue
        method = _install_method(skill_dir)
        entry = {"path": path, "local": local, "install_method": method}

        reason = _dev_checkout_reason(skill_dir, local, remote)
        if reason:
            results.append({**entry, "action": "dev-skip", "message": reason})
            continue
        if not _is_newer(remote, local):
            results.append({**entry, "action": "up-to-date", "message": ""})
            continue
        if not force and _recently_failed(state, path, remote):
            results.append(
                {**entry, "action": "throttled", "message": "3 小時內已失敗過一次，暫不重試"}
            )
            continue

        ok, message = _force_sync(skill_dir)
        _record_sync(state, path, remote, ok)
        if ok:
            _installs(state)[path]["local"] = _read_version_at(skill_dir) or remote
        results.append({**entry, "action": "synced" if ok else "failed", "message": message})
    return results


# ---------------------------------------------------------------------------
# 檢查與報告
# ---------------------------------------------------------------------------


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


def check(force: bool = False) -> dict:
    """
    比對版本並登記安裝，回傳結果字典（不做同步）。

    status: 'unknown'（本地無 VERSION 或遠端不可得）｜'current'（已是最新）｜
            'outdated'（有新版）｜'dev'（本地高於遠端，開發用副本）
    """
    local = _read_version_at(SKILL_DIR)
    if local is None:
        return {"status": "unknown", "reason": "本地找不到 VERSION 檔"}

    state = _load_state()
    _register_install(state, local)
    remote = _resolve_remote(state, force)
    _save_state(state)  # 註冊與快取無論如何都要留下

    if remote is None:
        return {"status": "unknown", "local": local, "reason": "無法取得遠端 VERSION"}

    base = {"local": local, "remote": remote, "skill_dir": str(SKILL_DIR)}
    if _is_newer(local, remote):
        return {"status": "dev", **base}
    if not _is_newer(remote, local):
        return {"status": "current", **base}

    changelog = _changelog_excerpt(remote)
    return {
        "status": "outdated",
        **base,
        "install_method": _install_method(),
        "changelog": changelog,
        "breaking": bool(changelog and any(m in changelog for m in BREAKING_MARKERS)),
    }


def _manual_command(path: str, method: str) -> str:
    if method == "git":
        return f'git -C "{path}" fetch origin main && git -C "{path}" reset --hard FETCH_HEAD'
    return "npx skills update"


def _configure_stdout() -> None:
    """
    Windows 主控台預設 cp950，CHANGELOG 裡的 ≤／→ 之類字元會讓 print 直接炸掉——
    而且炸在同步完成之後，使用者看不到「已同步」。導向管線（hook 情境）時改用 UTF-8，
    終端機保持原編碼；兩者都把編不出來的字元換成 ?，絕不因為輸出而失敗。
    """
    try:
        if sys.stdout.isatty():
            sys.stdout.reconfigure(errors="replace")
        else:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass


def main() -> int:
    _configure_stdout()
    parser = argparse.ArgumentParser(
        description="檢查 aigo-builder Skill 是否有新版；有就強制同步本機所有安裝"
    )
    parser.add_argument("--force", action="store_true", help="忽略 3 小時節流（含失敗重試抑制）")
    parser.add_argument("--json", action="store_true", help="輸出 JSON")
    parser.add_argument(
        "--check-only", action="store_true", help="只報告不同步（維護者／CI 用）"
    )
    # 1.27.x 以前的文件寫的是這兩個旗標；現在預設就是同步全部，保留只為相容
    parser.add_argument("--apply", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--apply-all", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    force = args.force or args.apply or args.apply_all
    result = check(force=force)

    sync_results: list[dict] = []
    if not args.check_only and result.get("remote"):
        # 本安裝已是最新、但其他註冊安裝落後的情況也要處理，所以不看 status
        state = _load_state()
        sync_results = _sync_all(state, result["remote"], force)
        _save_state(state)
        result["sync_results"] = sync_results

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    # 人類／agent 可讀輸出：只有「有動作」才出聲，其餘保持安靜
    acted = [r for r in sync_results if r["action"] in ("synced", "failed", "dev-skip")]
    # dev-skip 單獨出現（沒有任何安裝需要同步）時也不吵——維護者每個 session 都會看到
    if not any(r["action"] in ("synced", "failed") for r in acted):
        if args.check_only and result["status"] == "outdated":
            print(
                f"[aigo-builder] 有新版：本地 {result['local']} → 遠端 {result['remote']}"
                "（--check-only，未同步）"
            )
        return 0

    print(f"[aigo-builder] 遠端 {result['remote']} 較新，已強制同步本機安裝：")
    labels = {"synced": "已同步", "failed": "失敗", "dev-skip": "開發副本，略過"}
    for r in acted:
        line = f"  [{labels[r['action']]}] {r['path']}（原 {r['local']}，{r['install_method']} 安裝）"
        if r["message"]:
            line += f"：{r['message']}"
        print(line)

    failed = [r for r in acted if r["action"] == "failed"]
    if failed:
        print("\n以下安裝同步失敗，請告知使用者並請他們手動執行：")
        for r in failed:
            print(f"  {_manual_command(r['path'], r['install_method'])}")
        if result.get("breaking"):
            print(
                "\n⚠️ 這一版含**破壞性變更**：仍停在舊版會讓平台呼叫直接失敗，"
                "而失敗訊息通常不會指向真正的原因。請明確告知使用者，不要當成可選更新。"
            )

    if result.get("changelog"):
        print(f"\n變更摘要：\n{result['changelog']}\n")

    if any(r["action"] == "synced" for r in acted):
        print("已同步的安裝請重新讀取 SKILL.md 以套用新版指令。更新已完成，只需告知使用者，不必徵詢。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
