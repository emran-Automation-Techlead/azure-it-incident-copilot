"""Integration tests - require a populated Azure AI Search index and Azure OpenAI (see .env)."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.rag import answer, embed, retrieve

client = TestClient(app)


def test_embedding_dimension():
    assert len(embed("vpn timeout")) == 1536


def test_retrieval_vpn():
    ids = [d["id"] for d in retrieve("VPN keeps disconnecting for remote users", k=4)]
    assert "INC-1001" in ids


def test_retrieval_ad_replication():
    ids = [d["id"] for d in retrieve("New employee accounts are not appearing on one domain controller.", k=4)]
    assert "INC-1003" in ids


def test_retrieval_mfa():
    ids = [d["id"] for d in retrieve("Users cannot authenticate after MFA enrollment.", k=4)]
    assert "INC-1005" in ids


def test_answer_has_source_ids():
    r = answer("VPN keeps disconnecting for remote sales users every 15 minutes. What should I check?")
    assert r["sources"] and all(s["id"].startswith("INC-") for s in r["sources"])
    assert any(s["id"] == "INC-1001" for s in r["sources"])
    assert r["tokens_used"] > 0


def test_vague_query_does_not_guess():
    r = answer("server is slow")
    text = r["answer"].lower()
    assert "?" in text or "clarif" in text or "more detail" in text or "no matching" in text


def test_out_of_domain_not_answered():
    r = answer("How do I bake a cake?")
    text = r["answer"].lower()
    assert "incident triage" in text or "it incident" in text
    assert not r["sources"]
    assert "flour" not in text and "oven" not in text


def test_followup_returns_source_ids():
    first = "VPN keeps disconnecting for remote sales users every 15 minutes. What should I check?"
    a1 = answer(first)
    r = answer(
        "Which incident IDs support your recommendation?",
        [{"role": "user", "content": first}, {"role": "assistant", "content": a1["answer"]}],
    )
    assert "INC-" in r["answer"]


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


@pytest.mark.parametrize("payload", [{"query": ""}, {"query": "   "}, {}, {"query": "x" * 2001}])
def test_invalid_query_rejected(payload):
    assert client.post("/chat", json=payload).status_code == 422


def test_chat_endpoint_shape():
    r = client.post("/chat", json={"query": "DNS resolution failing for internal hostnames"})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"answer", "sources", "tokens_used"}
