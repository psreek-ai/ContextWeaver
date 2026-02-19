"""
Central configuration for ContextWeaver.

All settings are readable from environment variables or a .env file,
making the system deployable in any environment without code changes.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="CW_",
        case_sensitive=False,
    )

    # Anthropic / Claude
    anthropic_api_key: str = Field(..., description="Anthropic API key")
    claude_model: str = Field(
        default="claude-opus-4-6",
        description="Claude model ID to use for all agent reasoning",
    )

    # GitHub integration
    github_token: str = Field(default="", description="GitHub personal access token")
    github_repo: str = Field(default="", description="owner/repo to analyze (e.g. org/myrepo)")

    # Storage
    chroma_persist_dir: str = Field(
        default=".contextweaver/chroma",
        description="Directory for ChromaDB persistent storage",
    )
    graph_persist_path: str = Field(
        default=".contextweaver/decision_graph.json",
        description="Path for the serialized decision graph",
    )

    # API server
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8765)
    api_secret: str = Field(
        default="dev-secret-change-me",
        description="Bearer token secret for API auth",
    )

    # Agent behavior
    mining_lookback_days: int = Field(
        default=365,
        description="How many days of history to mine on first run",
    )
    conflict_threshold: float = Field(
        default=0.78,
        description="Cosine similarity threshold for flagging potential conflicts",
    )
    max_decision_graph_nodes: int = Field(
        default=50_000,
        description="Maximum nodes in the in-memory decision graph",
    )


# Singleton - import `settings` everywhere
settings = Settings()  # type: ignore[call-arg]
