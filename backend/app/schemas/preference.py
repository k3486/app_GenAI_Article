"""好みメモ・興味プロファイルの修正案・プロファイルの履歴の入出力の型。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ProposalKind = Literal["add", "remove", "rephrase"]
MEMO_MAX_CHARS = 800


class ProposalDraft(BaseModel):
    """Haiku が出す修正案1件。"""

    kind: ProposalKind
    before_text: str = Field(description="変更前の文（プロファイルの文そのまま。add のときは空）")
    after_text: str = Field(description="変更後の文（remove のときは空）")
    reason: str = Field(description="理由（日本語で1〜2文）")
    evidence_topic_ids: list[int] = Field(description="根拠にした評価の話題 ID（1〜3件）")


class PreferenceOutput(BaseModel):
    """好みメモスキルの出力。"""

    memo: str = Field(description="好みメモ（800字以内）")
    proposals: list[ProposalDraft] = Field(max_length=3, description="修正案（0〜3件）")


class PreferenceState(BaseModel):
    text: str
    source: Literal["haiku", "manual", "none"]
    updated_at: datetime | None
    feedback_since: int  # 前回のメモより後に付いた評価の件数
    update_every: int


class PreferenceIn(BaseModel):
    text: str = Field(max_length=MEMO_MAX_CHARS)


class EvidenceTopic(BaseModel):
    id: int
    title_ja: str


class ProposalOut(BaseModel):
    id: int
    kind: ProposalKind
    before_text: str
    after_text: str
    reason: str
    evidence: list[EvidenceTopic]
    status: Literal["pending", "approved", "rejected"]
    applied_text: str | None
    created_at: datetime
    decided_at: datetime | None


class ApproveIn(BaseModel):
    edited_text: str | None = Field(default=None, max_length=2000)


class VersionOut(BaseModel):
    id: int
    text: str
    source: Literal["initial", "manual", "proposal", "restore"]
    created_at: datetime
