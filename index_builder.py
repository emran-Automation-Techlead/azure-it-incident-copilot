"""Create the Azure AI Search vector index and upload embedded incidents."""
import json
from pathlib import Path

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    SearchableField,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)

from app.config import settings
from app.rag import embed

DATA = Path(__file__).parent / "data" / "incidents.jsonl"


def build_index() -> None:
    cred = AzureKeyCredential(settings.search_key)
    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True),
        SearchableField(name="title", type=SearchFieldDataType.String),
        SearchableField(name="content", type=SearchFieldDataType.String),
        SimpleField(name="category", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SearchField(
            name="embedding",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=1536,
            vector_search_profile_name="default-profile",
        ),
    ]
    vector_search = VectorSearch(
        algorithms=[HnswAlgorithmConfiguration(name="hnsw-config")],
        profiles=[VectorSearchProfile(name="default-profile", algorithm_configuration_name="hnsw-config")],
    )
    SearchIndexClient(settings.search_endpoint, cred).create_or_update_index(
        SearchIndex(name=settings.search_index, fields=fields, vector_search=vector_search)
    )

    docs = []
    for line in DATA.read_text(encoding="utf8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        content = (
            f"{r['title']}\nSeverity: {r['severity']}\nSymptoms: {r['symptoms']}\n"
            f"Root cause: {r['root_cause']}\nResolution: {r['resolution']}"
        )
        docs.append(
            {"id": r["id"], "title": r["title"], "content": content, "category": r["category"], "embedding": embed(content)}
        )

    client = SearchClient(settings.search_endpoint, settings.search_index, cred)
    results = client.upload_documents(docs)
    failed = [x.key for x in results if not x.succeeded]
    if failed:
        raise SystemExit(f"Upload failed for: {failed}")
    print(f"Uploaded {len(docs)} incidents to '{settings.search_index}'")


def verify() -> None:
    import time

    client = SearchClient(settings.search_endpoint, settings.search_index, AzureKeyCredential(settings.search_key))
    for _ in range(10):  # document count is eventually consistent
        n = client.get_document_count()
        if n:
            break
        time.sleep(2)
    print(f"Index '{settings.search_index}' contains {n} documents")


if __name__ == "__main__":
    build_index()
    verify()
