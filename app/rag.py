"""Retrieval-augmented generation: embed -> retrieve (hybrid) -> grounded answer."""
import re
from functools import lru_cache

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from openai import AzureOpenAI

from app.config import settings

SYSTEM_PROMPT = """You are an IT Incident Copilot for an enterprise service desk.

Use the retrieved incident context as the primary source of truth.
Do not invent incident IDs, root causes, or resolutions.
If the retrieved context does not contain a relevant precedent, clearly state that no matching precedent was found.
If the question is too vague to triage (for example just "server is slow"), do not guess: ask 2-3 clarifying questions
(what system, what symptoms, since when) and mention only precedents that are clearly relevant.
For out-of-scope questions (anything not about IT incidents), reply that this system is designed for IT incident triage and do not answer the question.
When you give guidance, cite the incident IDs used, in square brackets like [INC-1001].
Provide practical triage guidance only when supported by the retrieved context.
If the user asks which incidents support your recommendation, list the incident IDs from your previous answer with a one-line reason each."""

MAX_HISTORY_TURNS = 6


@lru_cache(maxsize=1)
def _openai() -> AzureOpenAI:
    return AzureOpenAI(
        api_key=settings.openai_key,
        api_version=settings.api_version,
        azure_endpoint=settings.openai_endpoint,
    )


@lru_cache(maxsize=1)
def _search() -> SearchClient:
    return SearchClient(
        settings.search_endpoint,
        settings.search_index,
        AzureKeyCredential(settings.search_key),
    )


def embed(query: str) -> list[float]:
    resp = _openai().embeddings.create(model=settings.embedding_deployment, input=query)
    return resp.data[0].embedding


def retrieve(query: str, k: int = 4) -> list[dict]:
    """Hybrid (keyword + vector) retrieval over the incident index."""
    vector = VectorizedQuery(vector=embed(query), k_nearest_neighbors=k, fields="embedding")
    results = _search().search(search_text=query, vector_queries=[vector], top=k)
    return [
        {"id": r["id"], "title": r["title"], "content": r["content"], "category": r.get("category")}
        for r in results
    ]


def _cited_ids(text: str) -> set[str]:
    return set(re.findall(r"INC-\d+", text))


def answer(query: str, history: list[dict] | None = None) -> dict:
    history = (history or [])[-MAX_HISTORY_TURNS * 2:]

    # Follow-ups like "which incident IDs support that?" carry no topic of their own,
    # so retrieve using the previous user question as well.
    prior_user = next((m["content"] for m in reversed(history) if m["role"] == "user"), "")
    retrieval_query = f"{prior_user}\n{query}" if prior_user and len(query.split()) < 8 else query
    docs = retrieve(retrieval_query)

    context = "\n\n".join(f"[{d['id']}] {d['title']}\n{d['content']}" for d in docs)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append({"role": "user", "content": f"Retrieved incident context:\n{context}\n\nQuestion: {query}"})

    resp = _openai().chat.completions.create(
        model=settings.chat_deployment, messages=messages, temperature=0.2
    )
    text = resp.choices[0].message.content or ""

    # Only surface sources the model actually relied on, so refusals show no citations.
    cited = _cited_ids(text)
    sources = [{"id": d["id"], "title": d["title"]} for d in docs if d["id"] in cited]
    return {"answer": text, "sources": sources, "tokens_used": resp.usage.total_tokens}
