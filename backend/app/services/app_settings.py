"""画面から変える設定（興味プロファイル・重み・しきい値・件数・費用の上限）。

DB の settings 表に持つ。
"""

from pathlib import Path

from sqlmodel import Session

from app.models import Setting
from app.schemas.settings import Settings, Weights
from app.services.scoring import DEFAULT_THRESHOLD, DEFAULT_WEIGHTS

_APP_KEY = "app"
_SAMPLE_KEY = "sample_mode"
PROFILE_PATH = Path(__file__).resolve().parents[2] / "config" / "interest_profile.default.md"


def default_settings() -> Settings:
    """初期値。興味プロファイルは、承認済みの叩き台（config/interest_profile.default.md）。"""
    return Settings(
        profile=PROFILE_PATH.read_text(encoding="utf-8"),
        weights=Weights(**DEFAULT_WEIGHTS),
        threshold=DEFAULT_THRESHOLD,
        max_selected=20,
        max_major=3,
        max_candidates=200,
        max_scored=50,
        month_limit_usd=10.0,
        run_limit_usd=0.5,
    )


def load_settings(session: Session) -> Settings:
    row = session.get(Setting, _APP_KEY)
    return Settings.model_validate(row.value) if row else default_settings()


def save_settings(session: Session, settings: Settings) -> Settings:
    row = session.get(Setting, _APP_KEY)
    value = settings.model_dump()
    if row is None:
        session.add(Setting(key=_APP_KEY, value=value))
    else:
        row.value = value
    session.commit()
    return settings


def is_sample_mode(session: Session) -> bool:
    """試しのデータ（make seed）で動いている間は True。画面に注意書きを出す。"""
    row = session.get(Setting, _SAMPLE_KEY)
    return bool(row and row.value.get("enabled"))


def set_sample_mode(session: Session, enabled: bool) -> None:
    row = session.get(Setting, _SAMPLE_KEY)
    if row is None:
        session.add(Setting(key=_SAMPLE_KEY, value={"enabled": enabled}))
    else:
        row.value = {"enabled": enabled}
    session.commit()
