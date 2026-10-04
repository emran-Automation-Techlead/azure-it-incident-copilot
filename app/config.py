"""Environment-driven configuration. No secrets live in code."""
import os

from dotenv import load_dotenv

load_dotenv()


def _req(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


class Settings:
    """Lazy accessors so importing the module never fails without a .env."""

    api_version = "2024-10-21"

    @property
    def openai_endpoint(self) -> str:
        return _req("AZURE_OPENAI_ENDPOINT")

    @property
    def openai_key(self) -> str:
        return _req("AZURE_OPENAI_KEY")

    @property
    def chat_deployment(self) -> str:
        return os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")

    @property
    def embedding_deployment(self) -> str:
        return os.environ.get("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-small")

    @property
    def search_endpoint(self) -> str:
        return _req("AZURE_SEARCH_ENDPOINT")

    @property
    def search_key(self) -> str:
        return _req("AZURE_SEARCH_KEY")

    @property
    def search_index(self) -> str:
        return os.environ.get("AZURE_SEARCH_INDEX", "incidents-index")

    @property
    def appinsights(self) -> str:
        return os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING", "")


settings = Settings()
