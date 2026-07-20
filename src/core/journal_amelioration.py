"""Journal d'interactions pour amélioration automatique."""

from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config


class JournalAmelioration:
    def __init__(self, chemin: Optional[Path] = None):
        logs_dir = Path(config.PROJECT_ROOT) / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        self.chemin = Path(chemin or logs_dir / "interactions.jsonl")

    def enregistrer(self, evenement: Dict[str, Any]) -> None:
        payload = dict(evenement or {})
        payload.setdefault("ts", datetime.now(timezone.utc).isoformat())
        try:
            with self.chemin.open("a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
        except Exception:
            pass

    def lire(self, limite: int = 200) -> List[Dict[str, Any]]:
        if not self.chemin.exists():
            return []
        lignes = self.chemin.read_text(encoding="utf-8").splitlines()
        out: List[Dict[str, Any]] = []
        for ligne in lignes[-limite:]:
            try:
                out.append(json.loads(ligne))
            except Exception:
                continue
        return out

    def synthetiser(self, limite: int = 300) -> Dict[str, Any]:
        """Produit des insights simples pour ajuster le comportement."""
        events = self.lire(limite=limite)
        if not events:
            return {"n": 0, "insights": []}

        modes: Dict[str, int] = {}
        feedbacks: List[int] = []
        scores_rag: List[float] = []
        web_utile = 0
        web_total = 0
        regen_total = 0

        for e in events:
            mode = e.get("mode") or "inconnu"
            modes[mode] = modes.get(mode, 0) + 1
            if isinstance(e.get("feedback"), (int, float)):
                feedbacks.append(int(e["feedback"]))
            if isinstance(e.get("score_rag"), (int, float)):
                scores_rag.append(float(e["score_rag"]))
            if e.get("strategie_sources") in {"web", "hybride"}:
                web_total += 1
                if e.get("web_utile"):
                    web_utile += 1
            if e.get("regen"):
                regen_total += int(e.get("regen") or 0)

        insights: List[str] = []
        if scores_rag:
            moy = statistics.mean(scores_rag)
            if moy < 0.3:
                insights.append("score_rag_faible: privilégier web ou reformulation")
            elif moy > 0.55:
                insights.append("score_rag_fort: réduire le web inutile")
        if feedbacks:
            neg = sum(1 for f in feedbacks if f < 0)
            if neg / len(feedbacks) >= 0.35:
                insights.append("feedback_negatif_eleve: renforcer critique qualité")
        if web_total and web_utile / web_total < 0.4:
            insights.append("web_peu_utile: n'activer le web que si RAG faible")
        if regen_total >= max(3, len(events) // 4):
            insights.append("regenerations_frequentes: durcir le plan initial")

        top_modes = sorted(modes.items(), key=lambda x: -x[1])[:5]
        return {
            "n": len(events),
            "modes": dict(top_modes),
            "score_rag_moyen": round(statistics.mean(scores_rag), 3) if scores_rag else None,
            "feedback_moyen": round(statistics.mean(feedbacks), 3) if feedbacks else None,
            "insights": insights,
        }

    def formater_insights_prompt(self) -> str:
        synth = self.synthetiser()
        if not synth.get("insights"):
            return ""
        lignes = ["Insights d'amélioration (logs récents) :"]
        for i in synth["insights"][:4]:
            lignes.append(f"- {i}")
        return "\n".join(lignes)
