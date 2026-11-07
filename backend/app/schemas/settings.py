"""設定・運用シートの API 入出力の型。"""

from pydantic import BaseModel, Field

from app.schemas.topics import CriterionKey, SourceKind


class Weights(BaseModel):
    interest: int = Field(ge=0, le=100)
    practical: int = Field(ge=0, le=100)
    freshness: int = Field(ge=0, le=100)
    trust: int = Field(ge=0, le=100)
    depth: int = Field(ge=0, le=100)

    def as_dict(self) -> dict[CriterionKey, int]:
        return {
            "interest": self.interest,
            "practical": self.practical,
            "freshness": self.freshness,
            "trust": self.trust,
            "depth": self.depth,
        }


class Settings(BaseModel):
    profile: str
    weights: Weights
    threshold: int = Field(ge=0, le=110)
    max_selected: int = Field(ge=1, le=50)
    max_major: int = Field(ge=0, le=10)
    max_candidates: int = Field(ge=1, le=300)
    max_scored: int = Field(ge=1, le=200)
    month_limit_usd: float = Field(gt=0)
    run_limit_usd: float = Field(gt=0)


class SourceInfo(BaseModel):
    key: str
    name: str
    kind: SourceKind
    enabled: bool
    candidates: int
    selected: int
    likes: int
    avg_score: float | None


class SourcePatch(BaseModel):
    enabled: bool
