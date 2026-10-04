import logging
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from app.config import settings
from app.rag import answer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("incident-copilot")

if settings.appinsights:
    try:
        from azure.monitor.opentelemetry import configure_azure_monitor

        configure_azure_monitor(connection_string=settings.appinsights)
        log.info("Application Insights telemetry enabled")
    except Exception:  # observability must never break the app
        log.exception("Failed to enable Application Insights")

app = FastAPI(title="Azure IT Incident Copilot", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class Turn(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str


class ChatRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    history: list[Turn] = []

    @field_validator("query")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("query must not be blank")
        return v.strip()


class Source(BaseModel):
    id: str
    title: str


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]
    tokens_used: int


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    start = time.perf_counter()
    try:
        result = answer(req.query, [t.model_dump() for t in req.history])
    except Exception as exc:
        log.exception("chat failed")
        raise HTTPException(status_code=502, detail=f"Upstream Azure error: {type(exc).__name__}") from exc
    log.info(
        "chat ok latency_ms=%d tokens=%d sources=%s",
        (time.perf_counter() - start) * 1000,
        result["tokens_used"],
        [s["id"] for s in result["sources"]],
    )
    return result


@app.exception_handler(Exception)
async def unhandled(_: Request, exc: Exception):
    log.exception("unhandled error")
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
