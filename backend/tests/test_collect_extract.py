import pytest

from app.services.collect.extract import (
    MIN_TEXT_CHARS,
    ExtractError,
    clean_summary,
    detect_language,
    extract_article,
    extract_pdf_text,
    find_arxiv_ids,
    paper_sections,
)
from tests.helpers import EN_SENTENCES, JA_SENTENCES, article_html


def test_extract_article_returns_text_and_metadata() -> None:
    html = article_html(
        "Release notes",
        canonical="https://example.com/posts/release-notes",
        image="https://img.example.com/hero.png",
    )
    extracted = extract_article(html, "https://example.com/posts/release-notes?utm_source=x")
    assert extracted.title == "Release notes"
    assert len(extracted.text) >= MIN_TEXT_CHARS
    assert "new model" in extracted.text
    assert "Copyright" not in extracted.text  # フッターは本文に含めない
    assert extracted.published_at is not None and extracted.published_at.year == 2026
    assert extracted.published_at.tzinfo is not None
    assert extracted.image_url == "https://img.example.com/hero.png"
    assert extracted.canonical_url == "https://example.com/posts/release-notes"


def test_extract_article_from_bytes_and_japanese() -> None:
    html = article_html("新モデルの公開", sentences=JA_SENTENCES, lang="ja")
    extracted = extract_article(html.encode("utf-8"), "https://example.jp/a")
    assert extracted.title == "新モデルの公開"
    assert "新しいモデルが公開され" in extracted.text
    assert detect_language(extracted.text) == "ja"


def test_extract_article_keeps_headings_and_lists() -> None:
    body = "<h2>Steps</h2><ul><li>Install the tool</li><li>Run the command</li></ul>"
    extracted = extract_article(article_html(extra_body=body), "https://example.com/a")
    assert "Steps" in extracted.text
    assert "Install the tool" in extracted.text


def test_empty_page_gives_short_text_so_the_caller_can_fall_back() -> None:
    shell = "<html><head><title>App</title></head><body><div id='root'></div></body></html>"
    extracted = extract_article(shell, "https://example.com/spa")
    assert len(extracted.text) < MIN_TEXT_CHARS


def test_page_without_date_has_no_published_at() -> None:
    extracted = extract_article(article_html(date=None), "https://example.com/a")
    assert extracted.published_at is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (EN_SENTENCES, "en"),
        (JA_SENTENCES, "ja"),
        (
            "Das ist ein deutscher Text über neue Modelle, die für Entwickler verfügbar sind. "
            * 6,
            "other",
        ),
        (
            "Ceci est un texte français sur les nouveaux modèles pour les développeurs. " * 6,
            "other",
        ),
        (
            "这是一个关于新模型的中文文本，它现在可以供所有开发者使用，并且支持新的功能。" * 3,
            "other",
        ),
        ("short", "unknown"),
        # 短い英語の見出しを、外国語と取り違えて落とさない
        ("Nvidia stock jumps as Anthropic signs compute deal", "unknown"),
        ("Это русский текст про новые модели для разработчиков и команд", "other"),
        ("이것은 개발자와 팀을 위한 새로운 모델에 대한 한국어 문장입니다", "other"),
        ("", "unknown"),
        ("日本語と English が混ざった記事です。" * 5, "ja"),
    ],
)
def test_detect_language(text: str, expected: str) -> None:
    assert detect_language(text) == expected


def test_find_arxiv_ids_in_order_without_duplicates() -> None:
    text = (
        'See <a href="https://arxiv.org/abs/2611.06918v2">paper</a> and '
        "https://arxiv.org/pdf/2611.06910 and again arxiv.org/abs/2611.06918. "
        "Not this: https://example.com/arxiv/1234.5678"
    )
    assert find_arxiv_ids(text) == ["2611.06918", "2611.06910"]
    assert find_arxiv_ids("no ids here") == []


def test_paper_sections_keeps_abstract_intro_and_conclusion() -> None:
    filler = "Related work and experiments. " * 40
    text = (
        "# Title\n\n## Abstract\nWe study the problem of long tasks and show an improvement. "
        + "A" * 120
        + "\n\n## 1 Introduction\nLong tasks are hard because of reasons. "
        + "B" * 120
        + f"\n\n## 2 Method\n{filler}\n\n## 3 Experiments\n{filler}"
        "\n\n## 5 Conclusion\nWe conclude that the approach helps. " + "C" * 120
    )
    picked = paper_sections(text)
    assert "We study the problem" in picked
    assert "Long tasks are hard" in picked
    assert "We conclude" in picked
    assert "Related work and experiments" not in picked


def test_paper_sections_falls_back_to_the_beginning_without_headings() -> None:
    text = "plain text without headings " * 1000
    assert paper_sections(text) == text[:12000]


def test_clean_summary_strips_tags_and_entities() -> None:
    raw = "<p>Hello&nbsp;<b>world</b> &amp; <a href='x'>friends</a></p>\n\n  more   text"
    assert clean_summary(raw) == "Hello world & friends more text"
    assert len(clean_summary("x" * 5000)) == 1000


def test_pdf_errors_are_reported_not_raised_as_random_exceptions() -> None:
    with pytest.raises(ExtractError):
        extract_pdf_text(b"this is not a pdf")


def test_japanese_text_needs_fewer_characters_to_count_as_a_body() -> None:
    from app.services.collect.extract import is_substantial

    japanese = JA_SENTENCES + JA_SENTENCES[:50]  # 216 字
    english = (EN_SENTENCES * 2)[:216]
    assert len(japanese) == len(english) == 216
    assert is_substantial(japanese)  # 日本語は 200 字あれば本文と見なす
    assert not is_substantial(english)  # 英語は 400 字必要
    assert not is_substantial(JA_SENTENCES)  # 166 字は、日本語でも短い
    assert is_substantial(EN_SENTENCES * 2)
    assert not is_substantial("")
