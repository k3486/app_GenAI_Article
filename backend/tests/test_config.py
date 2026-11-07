import pytest

from app.config import Settings, get_llm_provider


def make_settings(anthropic: str | None, openai: str | None) -> Settings:
    # 引数で渡した値は環境変数より優先されるので、実際のキーの有無に左右されない
    return Settings(anthropic_api_key=anthropic, openai_api_key=openai)


@pytest.mark.parametrize(
    ("anthropic", "openai", "expected"),
    [
        ("sk-ant-test", None, "anthropic"),
        (None, "sk-openai-test", "openai"),
        ("sk-ant-test", "sk-openai-test", "anthropic"),
        ("   ", "sk-openai-test", "openai"),
        ("sk-ant-test", "", "anthropic"),
    ],
)
def test_get_llm_provider_uses_non_blank_key(
    anthropic: str | None, openai: str | None, expected: str
) -> None:
    assert get_llm_provider(make_settings(anthropic, openai)) == expected


@pytest.mark.parametrize(("anthropic", "openai"), [(None, None), ("", "  ")])
def test_get_llm_provider_without_keys_raises(anthropic: str | None, openai: str | None) -> None:
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY か OPENAI_API_KEY"):
        get_llm_provider(make_settings(anthropic, openai))


def test_blank_key_is_none() -> None:
    settings = make_settings("  ", "")
    assert settings.anthropic_api_key is None
    assert settings.openai_api_key is None
