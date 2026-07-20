"""API REST optionnelle de l'assistant RAG.

Lancer :
  uvicorn api.main_api:app --app-dir src --reload --port 8000

Les modèles lourds sont initialisés à la première question.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlencode

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

ROOT_SRC = Path(__file__).resolve().parent.parent
ROOT_PROJECT = ROOT_SRC.parent
if str(ROOT_SRC) not in sys.path:
    sys.path.insert(0, str(ROOT_SRC))

from api.auth import exiger_api_key, verifier_secret_webhook
from app.historique_sqlite import HistoriqueSQLite
from core.orchestrateur import OrchestrateurAssistant

app = FastAPI(title="Assistant Intelligent Doc API", version="1.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class QuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=10_000)
    top_k: int = Field(default=5, ge=1, le=20)
    filtres: dict[str, Any] | None = None
    utiliser_corpus: bool = True


class FeedbackRequest(BaseModel):
    conversation_id: str
    message_idx: int = Field(ge=0)
    note: int = Field(ge=-1, le=5)  # 👍=1, 👎=-1, ou Likert 1-5
    commentaire: str = Field(default="", max_length=2_000)


class WebhookIngestRequest(BaseModel):
    since: Optional[str] = Field(default=None, description="Date ISO optionnelle")
    run: bool = Field(default=True, description="Exécuter le scrape (sinon plan seul)")


@lru_cache(maxsize=1)
def orchestrateur() -> OrchestrateurAssistant:
    return OrchestrateurAssistant()


@lru_cache(maxsize=1)
def historique() -> HistoriqueSQLite:
    return HistoriqueSQLite()


def _lancer_sync(since: Optional[str], run: bool) -> None:
    script = ROOT_PROJECT / "scripts" / "sync_incremental_github.py"
    cmd = [sys.executable, str(script)]
    if since:
        cmd.extend(["--since", since])
    if run:
        cmd.append("--run")
    subprocess.run(cmd, cwd=str(ROOT_PROJECT), check=False)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "models": "lazy"}


@app.post("/auth/apple/callback")
async def apple_oauth_callback(request: Request) -> RedirectResponse:
    """Apple form_post → redirige vers Streamlit avec ?code=&state=&apple_name=."""
    form = await request.form()
    code = str(form.get("code") or "")
    state = str(form.get("state") or "")
    user_raw = form.get("user")
    name = ""
    if user_raw:
        try:
            data = json.loads(str(user_raw))
            n = data.get("name") or {}
            name = f"{n.get('firstName', '')} {n.get('lastName', '')}".strip()
        except (json.JSONDecodeError, TypeError, AttributeError):
            name = ""
    streamlit = (
        os.getenv("STREAMLIT_PUBLIC_URL", "").strip()
        or "http://localhost:8501/"
    ).rstrip("/") + "/"
    if not code:
        return RedirectResponse(
            streamlit + "?apple_error=missing_code", status_code=302
        )
    q = urlencode(
        {"code": code, "state": state, "apple_name": name},
        safe="",
    )
    return RedirectResponse(f"{streamlit}?{q}", status_code=302)


@app.post("/ask")
def ask(
    requete: QuestionRequest,
    owner: str = Depends(exiger_api_key),
) -> dict[str, Any]:
    try:
        resultat = orchestrateur().repondre(
            question=requete.question,
            filtres=requete.filtres,
            top_k=requete.top_k,
            utiliser_corpus=requete.utiliser_corpus,
        )
        return {
            "answer": resultat.reponse,
            "documents": resultat.documents,
            "mode": resultat.mode,
            "tokens_utilises": resultat.tokens_utilises,
            "abstention": resultat.abstention,
            "owner": owner,
            "analyse": {
                "mode": resultat.analyse.mode,
                "domaine": resultat.analyse.domaine,
                "complexite": resultat.analyse.complexite,
            },
        }
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Service RAG indisponible : {exc}") from exc


@app.post("/feedback")
def feedback(
    payload: FeedbackRequest,
    owner: str = Depends(exiger_api_key),
) -> dict[str, str]:
    historique().enregistrer_feedback(
        payload.conversation_id,
        payload.message_idx,
        payload.note,
        payload.commentaire,
    )
    return {"status": "enregistre", "owner": owner}


@app.post("/ingest/webhook")
def ingest_webhook(
    payload: WebhookIngestRequest,
    background_tasks: BackgroundTasks,
    x_ingest_secret: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    """Déclenche une sync GitHub incrémentale (cron / GitHub webhook)."""
    verifier_secret_webhook(x_ingest_secret)
    background_tasks.add_task(_lancer_sync, payload.since, payload.run)
    return {
        "status": "accepte",
        "message": "Synchronisation planifiée en arrière-plan",
        "since": payload.since,
        "run": payload.run,
    }
