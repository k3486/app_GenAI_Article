from app.config import Settings


def test_blank_key_is_none() -> None:
    # 引数で渡した値は環境変数より優先されるので、実際のキーの有無に左右されない
    assert Settings(anthropic_api_key="  ").anthropic_api_key is None
