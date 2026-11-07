"""重み・しきい値・公式加点・件数の上限を変えたあと、Haiku を使わずに点数と選定を計算し直す。

保存した内訳（5観点の点数・そのときの重み）から合計点を出し直し、選定・重大ニュース・落選を
決め直す。👍/👎・★などのあなたの操作と、すでに選定された話題の選定日は変えない。

使い方（backend/ で）:
    uv run python -m scripts.reselect --dry-run   # 結果だけ見る（DB は変えない）
    uv run python -m scripts.reselect
"""

import argparse
from datetime import UTC, datetime

from sqlmodel import Session, select

from app.db import engine
from app.models import Topic
from app.services.app_settings import load_settings
from app.services.collect.select import select_scored


def _counts(session: Session) -> dict[str, int]:
    out: dict[str, int] = {}
    for sel in session.exec(select(Topic.selection)).all():
        out[sel] = out.get(sel, 0) + 1
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="点数と選定を計算し直す（Haiku は使わない）")
    parser.add_argument("--dry-run", action="store_true", help="結果を表示して、DB は変えない")
    args = parser.parse_args()
    with Session(engine) as session:
        settings = load_settings(session)
        print(
            f"設定: しきい値 {settings.threshold}・選定 最大{settings.max_selected}件"
            f"・重大 最大{settings.max_major}件"
        )
        print("変更前:", _counts(session))
        report = select_scored(
            session,
            run=None,
            settings=settings,
            now=datetime.now(UTC),
            recompute=True,
            dry_run=args.dry_run,
        )
        label = "（--dry-run・保存していません）変更後" if args.dry_run else "変更後"
        print(f"{label}: 選定 {report.selected}・重大 {report.major}・落選 {report.rejected}")


if __name__ == "__main__":
    main()
