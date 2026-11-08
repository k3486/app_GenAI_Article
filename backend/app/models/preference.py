from datetime import datetime

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from app.models.types import UTCDateTime, utcnow


class PreferenceNote(SQLModel, table=True):
    """好みメモ（👍/👎から Haiku がまとめた利用者の好みの傾向）。最新の1行が今のメモ。"""

    __tablename__ = "preference_notes"

    id: int | None = Field(default=None, primary_key=True)
    text: str
    source: str  # haiku | manual（画面で直した）
    based_on_count: int = 0  # このメモを作ったときの、材料にした評価の件数
    run_id: int | None = Field(default=None, foreign_key="runs.id")
    created_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(UTCDateTime, nullable=False, index=True)
    )


class ProfileVersion(SQLModel, table=True):
    """興味プロファイルの履歴（変わるたびに1行追記。ここから元に戻せる）。"""

    __tablename__ = "profile_versions"

    id: int | None = Field(default=None, primary_key=True)
    text: str
    source: str  # initial | manual | proposal | restore
    proposal_id: int | None = Field(default=None, foreign_key="profile_proposals.id")
    created_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(UTCDateTime, nullable=False)
    )


class ProfileProposal(SQLModel, table=True):
    """興味プロファイルの修正案（Haiku が出し、利用者が承認・編集して承認・却下する）。"""

    __tablename__ = "profile_proposals"

    id: int | None = Field(default=None, primary_key=True)
    kind: str  # add | remove | rephrase
    before_text: str = ""  # 変更前の文（add のときは空）
    after_text: str = ""  # 変更後の文（remove のときは空）
    reason: str = ""
    evidence_topic_ids: list[int] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    status: str = "pending"  # pending | approved | rejected
    applied_text: str | None = None  # 編集して承認したときの、実際に反映した文
    run_id: int | None = Field(default=None, foreign_key="runs.id")
    created_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(UTCDateTime, nullable=False)
    )
    decided_at: datetime | None = Field(default=None, sa_column=Column(UTCDateTime))
