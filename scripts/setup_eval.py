"""
setup_eval.py — 架設 A/B 對照的 eval 工作區

改 skill 之後要回答的是「agent 的行為有沒有變差」，不是「文件看起來有沒有比較好」。
本腳本把兩個 git ref 的 skill 各裝成一個乾淨工作區，除了 skill 版本以外條件相同。

用法：
    python scripts/setup_eval.py                      # before=main, after=HEAD
    python scripts/setup_eval.py --before v1.43.0 --after HEAD
    python scripts/setup_eval.py --dir ~/work         # 工作區放哪（預設 ~/work）
    python scripts/setup_eval.py --restore            # 還原使用者層 skill，收工用

⚠️ 憑證不由本腳本處理：工作區只寫 `.aigo/config.json`（base_url），
   `.aigo/.env` 請自己填或從既有工作區複製——憑證一律由使用者本人經手。

為什麼要停用使用者層的 skill：`~/.claude/skills/aigo-builder` 與測試工作區內的
`.claude/skills/aigo-builder` 同名，同時存在時哪一份生效不可靠，實測會讓兩版混在一起
（跑過一次，agent 一邊說照舊版走、一邊引用新版才有的規則）。本腳本把它整個移到
`~/.claude/skills-disabled/`，`--restore` 放回去。
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL_NAME = "aigo-builder"
USER_SKILLS = Path.home() / ".claude" / "skills"
DISABLED = Path.home() / ".claude" / "skills-disabled"
DEFAULT_TENANT_URL = "https://demo.ai-go.app"


def export_ref(ref: str, dest: Path) -> None:
    """把某個 git ref 的內容整份鋪到 dest（等同該版本的安裝）。"""
    dest.mkdir(parents=True, exist_ok=True)
    archive = dest.parent / f".{dest.name}.tar"
    with archive.open("wb") as fh:
        subprocess.run(["git", "archive", ref], cwd=ROOT, stdout=fh, check=True)
    with tarfile.open(archive) as tf:
        tf.extractall(dest)
    archive.unlink()


def make_workspace(base: Path, label: str, ref: str, tenant_url: str) -> Path:
    ws = base / f"eval-{label}"
    if ws.exists():
        shutil.rmtree(ws)
    skill_dir = ws / ".claude" / "skills" / SKILL_NAME
    export_ref(ref, skill_dir)
    (ws / ".aigo").mkdir(parents=True, exist_ok=True)
    (ws / ".aigo" / "config.json").write_text(
        json.dumps({"schema": 2, "base_url": tenant_url, "email": "",
                    "default_app": "", "apps": {}}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    version = (skill_dir / "VERSION").read_text(encoding="utf-8").strip()
    lines = len((skill_dir / "SKILL.md").read_text(encoding="utf-8").splitlines())
    print(f"  {ws}  ref={ref}  VERSION={version}  SKILL.md={lines} 行")
    return ws


def disable_user_skill() -> None:
    src = USER_SKILLS / SKILL_NAME
    if not src.exists():
        print(f"  使用者層沒有 {SKILL_NAME}，不需停用")
        return
    DISABLED.mkdir(parents=True, exist_ok=True)
    dst = DISABLED / SKILL_NAME
    if dst.exists():
        print(f"  ⚠️ {dst} 已存在，保留原樣不覆蓋——先手動處理")
        return
    shutil.move(str(src), str(dst))
    print(f"  已停用使用者層 skill → {dst}")


def restore_user_skill() -> int:
    src = DISABLED / SKILL_NAME
    if not src.exists():
        print(f"沒有待還原的 skill（{src} 不存在）")
        return 0
    dst = USER_SKILLS / SKILL_NAME
    if dst.exists():
        print(f"❌ {dst} 已存在，不覆蓋。確認哪一份要留之後自行處理")
        return 1
    shutil.move(str(src), str(dst))
    print(f"已還原 → {dst}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="架設 A/B 對照的 eval 工作區")
    ap.add_argument("--before", default="main", help="對照組的 git ref（預設 main）")
    ap.add_argument("--after", default="HEAD", help="實驗組的 git ref（預設 HEAD）")
    ap.add_argument("--dir", default="~/work", help="工作區放哪（預設 ~/work）")
    ap.add_argument("--tenant-url", default=DEFAULT_TENANT_URL, help="測試租戶空間網址")
    ap.add_argument("--restore", action="store_true", help="只還原使用者層 skill")
    args = ap.parse_args()

    if args.restore:
        return restore_user_skill()

    base = Path(args.dir).expanduser()
    base.mkdir(parents=True, exist_ok=True)
    print("建立工作區：")
    before = make_workspace(base, "before", args.before, args.tenant_url)
    after = make_workspace(base, "after", args.after, args.tenant_url)
    print("停用使用者層 skill（避免同名兩份混用）：")
    disable_user_skill()

    print(f"""
接下來（照 evals/README.md）：
  1. 填憑證：把可用的 .aigo/.env 放進兩個工作區（內容相同），或各自 `aigo_auth.py setup`
  2. 每個工作區各開 3 個**新對話**，工作目錄分別選：
       {before}
       {after}
  3. 貼 evals/scenarios/<情境>.json 的 query，照該檔 answers 回答，照 expected_behavior 評分
  4. 收工：python scripts/setup_eval.py --restore
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
