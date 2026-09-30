"""
aigo_cli_check.py — `aigo` CLI 相容性檢查（瀏覽器登入最低版本 ＋ 最新版提示）

跑任何 `aigo` 指令之前先跑本腳本。它回答三件事：

1. 機器上找不找得到 `aigo`（PATH，其次 `~/.local/bin`）
2. 版本是否 ≥ MIN_BROWSER_LOGIN_VERSION（0.5.0）——**瀏覽器登入**（`aigo login` 不帶 `--token`）
   在此版之前打的是 apex `https://ai-go.app/auth/cli`，平台自 2026-08-05 起 apex 登入一律
   401「帳號或密碼錯誤」（與密碼錯完全同形），所以舊版怎麼登都失敗。
   0.5.0 起 `aigo login --workspace <NAME>`／環境變數 `AIGO_WORKSPACE` 改開租戶子網域。
   **Deploy Token 路徑（`aigo login --token`、`AIGO_DEPLOY_TOKEN`）不受影響**——舊版仍能部署。
3. 是否落後 GitHub 上的最新 release（只提示，不擋）

設計約束（改動前請先讀）：
- **零相依**：只用標準函式庫，不經 uv。
- **fail-open**：抓不到最新版（離線、逾時、rate limit、格式異常）＝「最新版未知」，
  不是「禁止部署」。只有「找不到 aigo」與「版本低於最低版」才回非零，且那兩個判定不靠網路。
- **有界**：`aigo --version` 子行程與 HTTP 各自有 timeout，掛住的 binary 不會卡住 agent。
- **不要建議 `aigo update`**：到 0.6.0 為止所有版本的 `aigo update` 都抓一個私有 repo
  的 install.sh，沒有該 repo 權限（一般使用者都沒有）一律
  `gh: Not Found (HTTP 404)`／exit 127（2026-09-26 實測）。更新一律重跑公開 installer。

exit code：0 ＝ 瀏覽器登入可用（含「最新版未知」與「落後最新版但已達最低版」）；
          1 ＝ 找不到 aigo、版本讀不出來、或版本低於最低版。

用法：
    python3 scripts/aigo_cli_check.py            # 人讀輸出；沒事就一行
    python3 scripts/aigo_cli_check.py --json     # 機器可讀
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

# === 常數 ===
MIN_BROWSER_LOGIN_VERSION = "0.5.0"
RELEASES_REPO = "AI-GO-APP/aigo-cli-releases"
LATEST_API_URL = f"https://api.github.com/repos/{RELEASES_REPO}/releases/latest"
INSTALL_CMD = (
    f"curl -fsSL https://raw.githubusercontent.com/{RELEASES_REPO}/main/install.sh | bash"
)
VERSION_TIMEOUT = 5.0  # 秒；`aigo --version` 不該超過這個
FETCH_TIMEOUT = 3.0  # 秒；GitHub API，抓不到就算了

_SEMVER = re.compile(r"\bv?(\d+)\.(\d+)\.(\d+)\b")


# ---------------------------------------------------------------------------
# 純函式
# ---------------------------------------------------------------------------


def parse_version_output(text: str) -> str | None:
    """從 `aigo --version` 的輸出取出 X.Y.Z；抓不到三段 semver 回 None。"""
    m = _SEMVER.search(text or "")
    return ".".join(m.groups()) if m else None


def parse_latest_tag(body: str) -> str | None:
    """從 GitHub releases/latest 的 JSON 取 tag 的 X.Y.Z；任何異常回 None。"""
    try:
        data = json.loads(body)
    except (TypeError, ValueError):
        return None
    tag = data.get("tag_name") if isinstance(data, dict) else None
    if not isinstance(tag, str):
        return None
    m = _SEMVER.fullmatch(tag.strip())
    return ".".join(m.groups()) if m else None


def version_key(v: str) -> tuple[int, int, int]:
    """嚴格三段 semver 比較鍵。呼叫端保證輸入已通過 parse_*（否則 ValueError）。"""
    a, b, c = v.split(".")
    return (int(a), int(b), int(c))


def evaluate(*, local: str | None, latest: str | None, found: bool) -> dict:
    """給 (本地版本, 最新版本, 找不找得到) → 結論字典。不碰網路、不碰子行程。"""
    result = {
        "found": found,
        "local": local,
        "latest": latest,
        "latest_unknown": latest is None,
        "min_browser_login": MIN_BROWSER_LOGIN_VERSION,
        "install_cmd": INSTALL_CMD,
    }
    reinstall = (
        f"重裝（不要用 `aigo update`，它抓私有 repo 會 404）：\n    {INSTALL_CMD}\n"
        f"    裝完跑 `aigo --version` 確認 ≥ {MIN_BROWSER_LOGIN_VERSION}"
        "（若 `aigo` 不在 PATH，installer 裝在 ~/.local/bin）"
    )
    if not found:
        result.update(
            status="missing",
            browser_login_blocked=True,
            message=(
                "❌ 找不到 `aigo` CLI（PATH 與 ~/.local/bin 都沒有）。安裝：\n    " + INSTALL_CMD
                + "\n    （裝到 ~/.local/bin；不在 PATH 就自己加）"
            ),
        )
        return result
    if local is None:
        result.update(
            status="unknown_version",
            browser_login_blocked=True,
            message="❌ `aigo --version` 讀不出版本（binary 損壞、掛住或不是 aigo）。" + reinstall,
        )
        return result
    if version_key(local) < version_key(MIN_BROWSER_LOGIN_VERSION):
        result.update(
            status="incompatible",
            browser_login_blocked=True,
            message=(
                f"❌ aigo {local} 低於 {MIN_BROWSER_LOGIN_VERSION}：瀏覽器登入（`aigo login` 不帶 "
                "`--token`）打的是 apex，平台一律回 401「帳號或密碼錯誤」，怎麼登都失敗——"
                "**不要往密碼方向查**。Deploy Token 路徑（`aigo login --token`／"
                "`AIGO_DEPLOY_TOKEN`）不受影響，用 token 的部署可以先做。\n" + reinstall
            ),
        )
        return result
    if latest is not None and version_key(local) < version_key(latest):
        result.update(
            status="behind_latest",
            browser_login_blocked=False,
            message=(
                f"ℹ️ aigo {local} 可用（≥ {MIN_BROWSER_LOGIN_VERSION}），但最新版是 {latest}。"
                f"要更新就重跑 installer（不要 `aigo update`）：{INSTALL_CMD}"
            ),
        )
        return result
    suffix = "（最新版查不到，略過比對）" if latest is None else ""
    result.update(
        status="ok",
        browser_login_blocked=False,
        message=f"✅ aigo {local} 可用（瀏覽器登入需 ≥ {MIN_BROWSER_LOGIN_VERSION}）{suffix}",
    )
    return result


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------


def find_cli() -> str | None:
    """PATH 優先；installer 預設裝到 ~/.local/bin，PATH 沒帶時也要找得到。"""
    hit = shutil.which("aigo")
    if hit:
        return hit
    for name in ("aigo", "aigo.exe"):
        candidate = Path.home() / ".local" / "bin" / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def local_version(path: str) -> str | None:
    """跑 `<path> --version`，有界；失敗、逾時、解析不到一律 None。"""
    try:
        proc = subprocess.run(
            [path, "--version"],
            capture_output=True,
            text=True,
            timeout=VERSION_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    if proc.returncode != 0:
        return None
    return parse_version_output(proc.stdout or proc.stderr)


def latest_version() -> str | None:
    """問 GitHub 最新 release tag；任何失敗回 None（fail-open）。"""
    try:
        req = urllib.request.Request(
            LATEST_API_URL,
            headers={"User-Agent": "aigo-builder-skill", "Accept": "application/vnd.github+json"},
        )
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
            if resp.status != 200:
                return None
            body = resp.read().decode("utf-8", errors="replace")
    except Exception:  # fail-open：任何網路／解析錯誤（含 http.client.IncompleteRead）都只算「最新版未知」
        return None
    return parse_latest_tag(body)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="aigo CLI 相容性檢查")
    parser.add_argument("--json", action="store_true", help="機器可讀輸出")
    args = parser.parse_args(argv)

    path = find_cli()
    local = local_version(path) if path else None
    latest = latest_version()
    result = evaluate(local=local, latest=latest, found=path is not None)
    result["path"] = path

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result["message"])
    return 1 if result["browser_login_blocked"] else 0


if __name__ == "__main__":
    sys.exit(main())
