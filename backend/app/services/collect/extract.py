"""記事の本文を取り出す（HTML・PDF・arXiv の論文）と、言語・リンクの判定。"""

import html as html_lib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO

import trafilatura
from pypdf import PdfReader

# これより短い本文は「取れなかった」と見なす（ブラウザで取り直す・概要で採点する）
MIN_TEXT_CHARS = 400
# 日本語は同じ文字数でも情報量が多いので、基準を下げる
MIN_TEXT_CHARS_JA = 200
MAX_TEXT_CHARS = 200_000
_PAPER_FALLBACK_CHARS = 12_000
_ARXIV_ID = re.compile(r"arxiv\.org/(?:abs|pdf|html)/(\d{4}\.\d{4,5})(?:v\d+)?", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"\s+")
_ENGLISH_STOPWORDS = frozenset({"the", "and", "of", "to", "in", "is", "for", "on", "with", "that"})
_PAPER_HEADINGS = ("abstract", "introduction", "conclusion", "concluding")


@dataclass(frozen=True)
class Extracted:
    title: str
    text: str
    published_at: datetime | None
    image_url: str | None
    canonical_url: str | None


def extract_article(body: bytes | str, url: str) -> Extracted:
    """HTML から本文（見出し・箇条書きを残した文章）と、題名・日付・画像・正規 URL を取り出す。"""
    text = trafilatura.extract(
        body,
        url=url,
        output_format="markdown",
        include_comments=False,
        include_tables=True,
        include_links=False,
        favor_recall=True,
    )
    meta = trafilatura.extract_metadata(body, default_url=url)
    published: datetime | None = None
    if meta is not None and meta.date:
        try:
            published = datetime.strptime(meta.date[:10], "%Y-%m-%d").replace(tzinfo=UTC)
        except ValueError:
            published = None
    return Extracted(
        title=(meta.title or "").strip() if meta else "",
        text=(text or "").strip()[:MAX_TEXT_CHARS],
        published_at=published,
        image_url=(meta.image or None) if meta else None,
        canonical_url=(meta.url or None) if meta else None,
    )


class ExtractError(Exception):
    pass


def extract_pdf_text(data: bytes, *, max_pages: int = 40) -> str:
    try:
        reader = PdfReader(BytesIO(data))
        pages = [(page.extract_text() or "") for page in reader.pages[:max_pages]]
    except Exception as exc:  # pypdf は壊れた PDF でさまざまな例外を投げる
        raise ExtractError(f"PDF を読めません: {type(exc).__name__}") from exc
    return _SPACES.sub(" ", " ".join(pages)).strip()[:MAX_TEXT_CHARS]


def paper_sections(text: str) -> str:
    """論文の本文から、要旨・序論・結論だけを取り出す。見出しが見つからなければ冒頭を使う。"""
    sections: list[str] = []
    keep = False
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            title = re.sub(r"^[#\s\d.]+", "", line).strip().lower()
            keep = title.startswith(_PAPER_HEADINGS)
        if keep:
            sections.append(line)
    picked = "\n".join(sections).strip()
    return picked if len(picked) >= 200 else text[:_PAPER_FALLBACK_CHARS]


def find_arxiv_ids(text: str) -> list[str]:
    """本文や HTML の中の arXiv の論文 ID（出てきた順・重複なし）。"""
    seen: dict[str, None] = {}
    for match in _ARXIV_ID.finditer(text):
        seen.setdefault(match.group(1), None)
    return list(seen)


def clean_summary(fragment: str, *, limit: int = 1000) -> str:
    """RSS の概要（HTML 断片）を、文字だけにする。"""
    return _SPACES.sub(" ", html_lib.unescape(_TAG.sub(" ", fragment))).strip()[:limit]


def detect_language(text: str) -> str:
    """'ja' / 'en' / 'other'（日本語・英語以外）/ 'unknown'（短くて判定できない）。

    日本語は仮名の割合で見分ける。漢字だけ・ハングル・キリル文字などは 'other'。
    ラテン文字の文章は、英語に多い語の割合で見分けるが、短い文は誤判定しやすいので、
    十分に長い（300字以上）ときだけ 'other' にする。
    """
    sample = text[:1500]
    letters = [c for c in sample if c.isalpha()]
    if len(letters) < 20:
        return "unknown"
    kana = sum(1 for c in letters if "\u3040" <= c <= "\u30ff")
    if kana / len(letters) > 0.1:
        return "ja"
    # 仮名の無い漢字・ハングル・キリル文字など（ラテン文字は U+024F まで）
    foreign_script = sum(1 for c in letters if ord(c) > 0x024F)
    if foreign_script / len(letters) > 0.3:
        return "other"
    words = re.findall(r"[a-z']+", sample.lower())
    if words and sum(1 for w in words if w in _ENGLISH_STOPWORDS) / len(words) >= 0.12:
        return "en"
    return "other" if len(letters) >= 300 else "unknown"


def is_substantial(text: str) -> bool:
    """本文として十分な長さか（短いときは、ブラウザで取り直す・概要で採点する）。"""
    minimum = MIN_TEXT_CHARS_JA if detect_language(text) == "ja" else MIN_TEXT_CHARS
    return len(text) >= minimum
