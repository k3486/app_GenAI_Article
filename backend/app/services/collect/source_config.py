"""情報源の設定（config/sources.yaml）の読み込みと、DB の sources 表との同期。"""

import re
from functools import cache
from pathlib import Path
from typing import Any, Literal, Self

import yaml
from pydantic import BaseModel, Field, model_validator
from sqlmodel import Session, select

from app.models import Source

CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"
SOURCES_PATH = CONFIG_DIR / "sources.yaml"
SCORING_PATH = CONFIG_DIR / "scoring.yaml"

FetchKind = Literal["rss", "sitemap", "listing", "zenn", "qiita", "hf_papers"]


class SourceConfig(BaseModel):
    key: str
    name: str
    kind: Literal["official", "media", "paper"]
    fetch: FetchKind
    url: str | None = None
    pattern: str | None = None
    language: Literal["ja", "en"] = "en"
    ai_filter: bool = False
    fetch_body: bool = True  # False: 記事ページを取りに行かず、一覧の概要だけで登録する
    disabled_reason: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_required_fields(self) -> Self:
        if self.fetch in ("rss", "sitemap", "listing") and not self.url:
            raise ValueError(f"{self.key}: {self.fetch} には url が必要です")
        if self.fetch in ("sitemap", "listing") and not self.pattern:
            raise ValueError(f"{self.key}: {self.fetch} には pattern が必要です")
        return self

    @property
    def usable(self) -> bool:
        return self.disabled_reason is None


class FetchConfig(BaseModel):
    min_interval_seconds: dict[str, float] = Field(default_factory=lambda: {"default": 1.0})


class SourcesFile(BaseModel):
    fetch: FetchConfig = Field(default_factory=FetchConfig)
    sources: list[SourceConfig]

    @model_validator(mode="after")
    def _unique_keys(self) -> Self:
        keys = [s.key for s in self.sources]
        duplicated = {k for k in keys if keys.count(k) > 1}
        if duplicated:
            raise ValueError(f"情報源の key が重複しています: {sorted(duplicated)}")
        return self


def load_sources(path: Path = SOURCES_PATH) -> SourcesFile:
    return SourcesFile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def load_ai_keywords(path: Path = SCORING_PATH) -> list[str]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [str(word) for word in data.get("ai_keywords", [])]


@cache
def _exclude_pattern() -> re.Pattern[str] | None:
    data = yaml.safe_load(SCORING_PATH.read_text(encoding="utf-8")) or {}
    patterns = [str(p) for p in data.get("exclude_titles", [])]
    return re.compile("|".join(f"(?:{p})" for p in patterns), re.IGNORECASE) if patterns else None


def is_excluded_title(title: str) -> bool:
    """募集・公募の告知や一覧ページなど、記事として集めないタイトルか。"""
    pattern = _exclude_pattern()
    return bool(title and pattern and pattern.search(title.strip()))


def sync_sources(session: Session, config: SourcesFile) -> dict[str, Source]:
    """設定ファイルの情報源を DB に反映する（key で突き合わせ）。

    画面で変えた「使う／使わない」は上書きしない。取得できない情報源（disabled_reason あり）は、
    新しく作るときだけ「使わない」にする。
    """
    existing = {s.key: s for s in session.exec(select(Source)).all()}
    result: dict[str, Source] = {}
    for item in config.sources:
        row = existing.get(item.key)
        if row is None:
            row = Source(key=item.key, name=item.name, kind=item.kind, enabled=item.usable)
        else:
            row.name = item.name
            row.kind = item.kind
        session.add(row)
        result[item.key] = row
    session.commit()
    return result
