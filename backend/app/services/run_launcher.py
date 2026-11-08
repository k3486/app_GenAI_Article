"""更新の処理（scripts/collect.py）を、API とは別のプロセスとして起動する。

別プロセスにする理由: 更新は数分かかるうえ、API の再起動や落ち方に巻き込まれたくないため。
出力は data/logs/run-<id>.log に残す（落ちたときの原因を調べられるように）。
"""

import subprocess
import sys

from app.config import REPO_ROOT

LOG_DIR = REPO_ROOT / "data" / "logs"


def launch_collect(run_id: int) -> None:
    """実行の行の ID を渡して、更新の処理を起動する（終わりは待たない）。"""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_DIR / f"run-{run_id}.log", "ab") as log:
        subprocess.Popen(
            [sys.executable, "-m", "scripts.collect", "--run-id", str(run_id)],
            cwd=REPO_ROOT / "backend",
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,  # API が再起動しても、更新の処理は道連れにならない
        )
