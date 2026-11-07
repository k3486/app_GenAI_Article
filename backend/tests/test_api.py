"""API の動き（本物の DB・試しのデータ）。画面が頼る約束事を確かめる。"""

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session


@pytest.fixture
def api(client: TestClient, seeded: Session) -> TestClient:
    return client


def test_latest_lists_selected_and_major_only(api: TestClient) -> None:
    body = api.get("/api/topics", params={"view": "latest"}).json()
    assert body["total"] > 0
    assert {t["selection"] for t in body["items"]} <= {"selected", "major"}
    # 既定の並びは、更新の回の新しい順 → 点数の高い順
    keys = [(t["run_id"], t["score"]) for t in body["items"]]
    assert keys == sorted(keys, reverse=True)


def test_rejected_view_has_reason_and_five_lines(api: TestClient) -> None:
    items = api.get("/api/topics", params={"view": "rejected"}).json()["items"]
    assert items
    for item in items:
        assert item["selection"] == "rejected"
        assert item["rejection_reason"]
        assert len(item["summary_5lines"]) == 5


def test_sort_filter_and_paging(api: TestClient) -> None:
    page = api.get(
        "/api/topics",
        params={"view": "all", "sort": "score", "order": "asc", "page": 1, "page_size": 3},
    ).json()
    scores = [t["score"] for t in page["items"]]
    assert len(scores) == 3
    assert scores == sorted(scores)
    assert page["total"] > 3

    second = api.get(
        "/api/topics",
        params={"view": "all", "sort": "score", "order": "asc", "page": 2, "page_size": 3},
    ).json()
    assert scores[-1] <= second["items"][0]["score"]
    assert {t["id"] for t in page["items"]}.isdisjoint({t["id"] for t in second["items"]})

    howto = api.get("/api/topics", params={"view": "all", "type": "howto"}).json()["items"]
    assert howto
    assert {t["article_type"] for t in howto} == {"howto"}

    source = api.get("/api/topics", params={"view": "all", "source": "Sample Lab Blog"}).json()
    assert source["items"]
    assert {t["source_name"] for t in source["items"]} == {"Sample Lab Blog"}


def test_search_finds_japanese_and_short_words(api: TestClient) -> None:
    # 3文字以上は全文検索（trigram）、2文字以下は部分一致で探す
    mcp = api.get("/api/topics", params={"view": "all", "q": "MCP"}).json()["items"]
    assert len(mcp) >= 2
    assert all("MCP" in t["title_ja"] or "MCP" in t["tags"] for t in mcp)

    hook = api.get("/api/topics", params={"view": "all", "q": "フック"}).json()["items"]
    assert hook
    assert any("フック" in t["title_ja"] for t in hook)

    short = api.get("/api/topics", params={"view": "all", "q": "RAG"}).json()["items"]
    assert short

    two = api.get("/api/topics", params={"view": "all", "q": "買収"}).json()["items"]
    assert two
    assert "買収" in two[0]["title_ja"]
    assert (
        api.get("/api/topics", params={"view": "all", "q": "存在しない語句"}).json()["total"] == 0
    )


def test_search_does_not_break_on_special_characters(api: TestClient) -> None:
    for query in ['"', "a\"b'c", "%", "_", "*", "AND OR"]:
        assert api.get("/api/topics", params={"view": "all", "q": query}).status_code == 200


def test_invalid_params_are_rejected(api: TestClient) -> None:
    assert api.get("/api/topics", params={"view": "nope"}).status_code == 422
    assert api.get("/api/topics", params={"page": 0}).status_code == 422
    assert api.get("/api/topics", params={"page_size": 500}).status_code == 422


def test_detail_has_digest_with_inference_marks(api: TestClient) -> None:
    detail = api.get("/api/topics/1").json()
    assert len(detail["digest"]["lead"]) == 3
    inference = [p["inference"] for s in detail["digest"]["sections"] for p in s["paragraphs"]]
    assert any(inference)
    assert not all(inference)
    assert detail["articles"][0]["role"] == "representative"
    assert len(detail["articles"]) == 1 + detail["related_count"]


def test_rejected_topic_has_no_digest(api: TestClient) -> None:
    rejected = api.get("/api/topics", params={"view": "rejected"}).json()["items"][0]
    assert api.get(f"/api/topics/{rejected['id']}").json()["digest"] is None


def test_unknown_topic_is_404(api: TestClient) -> None:
    assert api.get("/api/topics/9999").status_code == 404
    assert api.patch("/api/topics/9999/state", json={"starred": True}).status_code == 404


def test_patch_state_changes_only_sent_fields(api: TestClient) -> None:
    card = api.patch("/api/topics/1/state", json={"starred": True}).json()
    assert card["state"]["starred"] is True
    favorites = api.get("/api/topics", params={"view": "favorites"}).json()["items"]
    assert 1 in {t["id"] for t in favorites}

    again = api.patch("/api/topics/1/state", json={"read_state": "read"}).json()
    assert again["state"]["starred"] is True
    assert again["state"]["read_state"] == "read"


def test_dislike_reason_is_cleared_when_rating_changes(api: TestClient) -> None:
    api.patch("/api/topics/2/state", json={"rating": "dislike", "dislike_reason": "low_quality"})
    state = api.patch("/api/topics/2/state", json={"rating": "like"}).json()["state"]
    assert state["rating"] == "like"
    assert state["dislike_reason"] is None
    cleared = api.patch("/api/topics/2/state", json={"rating": None}).json()["state"]
    assert cleared["rating"] is None


def test_backlog_contains_unread_and_drops_read_items(api: TestClient) -> None:
    def backlog() -> set[int]:
        items = api.get("/api/topics", params={"view": "backlog"}).json()["items"]
        return {t["id"] for t in items}

    assert 1 in backlog()
    api.patch("/api/topics/1/state", json={"read_state": "read", "backlog": False})
    assert 1 not in backlog()
    # 「後で読む」は、読了しても見送りになるまで残る
    api.patch("/api/topics/1/state", json={"backlog": True})
    assert 1 in backlog()
    api.patch("/api/topics/1/state", json={"read_state": "dismissed"})
    assert 1 not in backlog()


def test_state_changes_are_saved_to_the_database(api: TestClient, seeded: Session) -> None:
    from app.models import Topic

    api.patch("/api/topics/3/state", json={"read_state": "read", "rating": "like"})
    topic = seeded.get(Topic, 3)
    assert topic is not None
    seeded.refresh(topic)
    assert topic.read_state == "read"
    assert topic.read_at is not None and topic.read_at.tzinfo is not None
    assert topic.rating == "like" and topic.rated_at is not None


def test_status_and_budget(api: TestClient) -> None:
    status = api.get("/api/status").json()
    assert status["sample_mode"] is True
    assert status["latest_run"]["status"] in {"succeeded", "partial"}
    assert 0 < status["budget"]["month_cost_usd"] < status["budget"]["month_limit_usd"]
    runs = api.get("/api/runs").json()
    assert len(runs) == 3
    assert runs[0]["id"] > runs[-1]["id"]
    partial = next(r for r in runs if r["status"] == "partial")
    assert partial["issues"]
    assert len(runs[0]["search_queries"]) == 5


def test_run_start_is_not_implemented_yet(api: TestClient) -> None:
    response = api.post("/api/runs")
    assert response.status_code == 501
    assert "実装" in response.json()["detail"]


def test_insights_are_consistent_with_the_data(api: TestClient) -> None:
    body = api.get("/api/insights").json()
    total = (
        api.get("/api/topics", params={"view": "all", "page_size": 200}).json()["total"]
        + api.get("/api/topics", params={"view": "rejected"}).json()["total"]
    )
    assert sum(c["count"] for c in body["categories"]) == total
    assert sum(t["count"] for t in body["trend"]) == total
    assert len(body["backlog"]) == 14
    assert all(s["candidates"] >= s["selected"] for s in body["sources"])
    assert {b["label"] for b in body["effectiveness"]["score_bins"]} == {
        "60点未満",
        "60〜69点",
        "70〜79点",
        "80点以上",
    }


def test_insights_react_to_user_actions(api: TestClient) -> None:
    before = api.get("/api/insights").json()["effectiveness"]["rejected_missed_rate"]
    rejected = api.get("/api/topics", params={"view": "rejected"}).json()["items"]
    target = next(t["id"] for t in rejected if not t["state"]["missed"])
    api.patch(f"/api/topics/{target}/state", json={"missed": True})
    after = api.get("/api/insights").json()["effectiveness"]["rejected_missed_rate"]
    assert after > before


def test_backlog_trend_counts_unread_on_each_day(api: TestClient) -> None:
    backlog = api.get("/api/insights").json()["backlog"]
    today = backlog[-1]["count"]
    assert today > 0
    api.patch("/api/topics/1/state", json={"read_state": "read"})
    after = api.get("/api/insights").json()["backlog"][-1]["count"]
    assert after == today - 1


def test_settings_roundtrip_and_validation(api: TestClient) -> None:
    current = api.get("/api/settings").json()
    assert "興味のあるテーマ" in current["profile"]
    assert current["weights"] == {
        "interest": 20,
        "practical": 25,
        "freshness": 25,
        "trust": 15,
        "depth": 15,
    }
    current["threshold"] = 55
    assert api.put("/api/settings", json=current).json()["threshold"] == 55
    assert api.get("/api/settings").json()["threshold"] == 55

    current["max_selected"] = 0
    assert api.put("/api/settings", json=current).status_code == 422


def test_toggle_source(api: TestClient) -> None:
    sources = api.get("/api/sources").json()
    assert len(sources) == 7
    key = sources[0]["key"]
    toggled = api.patch(f"/api/sources/{key}", json={"enabled": False}).json()
    assert toggled["enabled"] is False
    assert next(s for s in api.get("/api/sources").json() if s["key"] == key)["enabled"] is False
    assert api.patch("/api/sources/unknown", json={"enabled": True}).status_code == 404


def test_empty_database_returns_empty_lists_not_errors(client: TestClient) -> None:
    assert client.get("/api/topics").json() == {
        "items": [],
        "total": 0,
        "page": 1,
        "page_size": 50,
    }
    status = client.get("/api/status").json()
    assert status["latest_run"] is None and status["sample_mode"] is False
    assert client.get("/api/runs").json() == []
    insights = client.get("/api/insights").json()
    assert insights["categories"] == [] and len(insights["backlog"]) == 14
    assert insights["effectiveness"]["selected_like_rate"] is None
    assert client.get("/api/sources").json() == []
    assert client.get("/api/settings").status_code == 200
