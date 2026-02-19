"""
ContextWeaver REST API.

Endpoints:

  POST /webhook/github          → Receive GitHub webhooks
  GET  /decisions               → List indexed decisions (paginated)
  GET  /decisions/{id}          → Get a single decision
  POST /brief                   → Generate a context briefing
  POST /why                     → Answer a "why?" question
  POST /conflicts               → Check text for conflicts
  GET  /stats                   → System statistics
  GET  /graph                   → Export decision graph JSON
  POST /mine/github             → Trigger GitHub mining
  POST /mine/local              → Trigger local repo mining

All write endpoints require Bearer token auth (set CW_API_SECRET).
"""

from __future__ import annotations

import json
from typing import Annotated, Any

import structlog
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from contextweaver.agents.orchestrator import Orchestrator
from contextweaver.config import settings
from contextweaver.integrations.github_webhook import GitHubWebhookHandler

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class BriefRequest(BaseModel):
    topic: str
    subject: str = "developer"
    scope: str = "project"


class WhyRequest(BaseModel):
    question: str


class ConflictCheckRequest(BaseModel):
    text: str
    label: str = "analysis"


class MineGitHubRequest(BaseModel):
    repo: str = ""
    lookback_days: int | None = None


class MineLocalRequest(BaseModel):
    repo_path: str
    docs_dir: str | None = None


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    app = FastAPI(
        title="ContextWeaver API",
        description="Decision Archaeology & Living Project Intelligence",
        version="0.1.0",
        docs_url="/docs",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Single shared orchestrator (lazy init on first request avoids slow startup)
    _orchestrator: Orchestrator | None = None

    def get_orchestrator() -> Orchestrator:
        nonlocal _orchestrator
        if _orchestrator is None:
            _orchestrator = Orchestrator()
        return _orchestrator

    # Webhook handler
    _webhook_handler = GitHubWebhookHandler(webhook_secret="")

    # ---------------------------------------------------------------------------
    # Auth dependency
    # ---------------------------------------------------------------------------

    def require_auth(authorization: Annotated[str, Header()] = "") -> None:
        if settings.api_secret == "dev-secret-change-me":
            return  # Dev mode: skip auth
        expected = f"Bearer {settings.api_secret}"
        if authorization != expected:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing Bearer token",
            )

    # ---------------------------------------------------------------------------
    # Routes
    # ---------------------------------------------------------------------------

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": "0.1.0"}

    @app.get("/stats")
    def get_stats(orc: Orchestrator = Depends(get_orchestrator)) -> dict[str, Any]:
        return orc.stats()

    @app.get("/graph")
    def get_graph(orc: Orchestrator = Depends(get_orchestrator)) -> dict[str, Any]:
        return orc.graph_export()

    @app.post("/brief")
    def brief(
        req: BriefRequest,
        _: None = Depends(require_auth),
        orc: Orchestrator = Depends(get_orchestrator),
    ) -> dict[str, Any]:
        briefing = orc.brief(req.topic, subject=req.subject, scope=req.scope)
        return briefing.model_dump(mode="json")

    @app.post("/why")
    def why(
        req: WhyRequest,
        _: None = Depends(require_auth),
        orc: Orchestrator = Depends(get_orchestrator),
    ) -> dict[str, str]:
        answer = orc.why(req.question)
        return {"question": req.question, "answer": answer}

    @app.post("/conflicts")
    def check_conflicts(
        req: ConflictCheckRequest,
        _: None = Depends(require_auth),
        orc: Orchestrator = Depends(get_orchestrator),
    ) -> dict[str, Any]:
        conflicts = orc.check_text_conflicts(req.text, label=req.label)
        return {
            "conflicts_found": len(conflicts),
            "conflicts": [c.model_dump(mode="json") for c in conflicts],
        }

    @app.post("/mine/github")
    def mine_github(
        req: MineGitHubRequest,
        _: None = Depends(require_auth),
        orc: Orchestrator = Depends(get_orchestrator),
    ) -> dict[str, Any]:
        decisions, status_obj = orc.mine_github(
            repo_name=req.repo or None,
            lookback_days=req.lookback_days,
        )
        return {
            "decisions_extracted": len(decisions),
            "status": status_obj.model_dump(mode="json"),
        }

    @app.post("/mine/local")
    def mine_local(
        req: MineLocalRequest,
        _: None = Depends(require_auth),
        orc: Orchestrator = Depends(get_orchestrator),
    ) -> dict[str, Any]:
        decisions = orc.mine_local(req.repo_path, docs_dir=req.docs_dir)
        return {"decisions_extracted": len(decisions)}

    @app.post("/webhook/github")
    async def github_webhook(
        request: Request,
        x_github_event: Annotated[str, Header()] = "",
        x_hub_signature_256: Annotated[str, Header()] = "",
        orc: Orchestrator = Depends(get_orchestrator),
    ) -> dict[str, Any]:
        body = await request.body()

        if not _webhook_handler.verify_signature(body, x_hub_signature_256):
            raise HTTPException(status_code=400, detail="Invalid webhook signature")

        payload = json.loads(body)
        event = x_github_event
        indexed = 0
        conflicts: list[Any] = []

        if event == "pull_request":
            artifact = _webhook_handler.parse_pull_request(payload)
            if artifact:
                # Check for conflicts BEFORE indexing (so we don't conflict with ourselves)
                found_conflicts = orc.check_conflicts(artifact)
                conflicts = [c.model_dump(mode="json") for c in found_conflicts]
                orc.index_artifact(artifact)
                indexed = 1

        elif event == "issues":
            artifact = _webhook_handler.parse_issue(payload)
            if artifact:
                orc.index_artifact(artifact)
                indexed = 1

        elif event == "push":
            artifacts = _webhook_handler.parse_push(payload)
            for artifact in artifacts:
                orc.index_artifact(artifact)
            indexed = len(artifacts)

        log.info("webhook.processed", event=event, indexed=indexed, conflicts=len(conflicts))
        return {
            "event": event,
            "artifacts_indexed": indexed,
            "conflicts_detected": len(conflicts),
            "conflicts": conflicts,
        }

    return app
