"""画面から変える設定（興味プロファイル・重み・しきい値・件数・費用の上限）。

DB の settings 表に持つ。
"""

from pathlib import Path

from sqlmodel import Session, select

from app.models import ProfileVersion, Setting
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


def save_settings(
    session: Session,
    settings: Settings,
    *,
    profile_source: str = "manual",
    proposal_id: int | None = None,
) -> Settings:
    """設定を保存する。興味プロファイルが変わったときは、版（履歴）を1つ追記する。"""
    old_profile = load_settings(session).profile
    row = session.get(Setting, _APP_KEY)
    value = settings.model_dump()
    if row is None:
        session.add(Setting(key=_APP_KEY, value=value))
    else:
        row.value = value
    if settings.profile != old_profile:
        if session.exec(select(ProfileVersion.id)).first() is None:
            # 初めて変えるときは、変える前の文を最初の版として残す
            session.add(ProfileVersion(text=old_profile, source="initial"))
        session.add(
            ProfileVersion(text=settings.profile, source=profile_source, proposal_id=proposal_id)
        )
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
