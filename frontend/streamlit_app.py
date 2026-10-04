import os

import requests
import streamlit as st

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="Azure IT Incident Copilot", page_icon="🛠️", layout="wide")

with st.sidebar:
    st.header("Architecture")
    st.markdown(
        """
```
Streamlit UI
   ↓
FastAPI backend
   ↓
Azure AI Search
(hybrid + vector, HNSW)
   ↓
Retrieved incidents
   ↓
Azure OpenAI chat model
   ↓
Grounded answer + citations
```
"""
    )
    st.divider()
    st.subheader("Try these")
    examples = [
        "VPN keeps disconnecting for remote sales users every 15 minutes. What should I check?",
        "New employee accounts are not appearing on one domain controller.",
        "Users cannot authenticate after MFA enrollment.",
        "server is slow",
        "How do I bake a cake?",
    ]
    for ex in examples:
        if st.button(ex, use_container_width=True):
            st.session_state.pending = ex
    if st.button("Clear conversation", type="secondary"):
        st.session_state.history = []
        st.rerun()

st.title("Azure IT Incident Copilot")
st.caption("RAG-grounded IT incident triage powered by Azure AI")
st.warning(
    "Answers are grounded in a synthetic incident knowledge base only. "
    "If no matching precedent exists, the copilot says so instead of guessing.",
    icon="⚠️",
)

if "history" not in st.session_state:
    st.session_state.history = []

for msg in st.session_state.history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("meta"):
            st.caption(msg["meta"])

query = st.chat_input("Describe the incident or ask a triage question...") or st.session_state.pop("pending", None)

if query:
    prior = [{"role": m["role"], "content": m["content"]} for m in st.session_state.history]
    st.session_state.history.append({"role": "user", "content": query})
    with st.chat_message("user"):
        st.markdown(query)
    with st.chat_message("assistant"):
        with st.spinner("Retrieving precedents and generating..."):
            try:
                r = requests.post(f"{BACKEND_URL}/chat", json={"query": query, "history": prior}, timeout=90)
                r.raise_for_status()
                data = r.json()
                text = data["answer"]
                ids = ", ".join(s["id"] for s in data["sources"]) or "none"
                meta = f"Sources: {ids} · {data['tokens_used']} tokens"
            except Exception as exc:
                text, meta = f"Backend error: {exc}", None
        st.markdown(text)
        if meta:
            st.caption(meta)
            for s in data["sources"]:
                st.markdown(f"- **{s['id']}** — {s['title']}")
    st.session_state.history.append({"role": "assistant", "content": text, "meta": meta})
