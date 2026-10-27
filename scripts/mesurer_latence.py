"""
Latence de bout en bout de l'orchestrateur (retrieval + web + LLM + boucle qualité).

- froid : chargement des modèles + 1re question du processus ;
- chaud : questions suivantes ;
- TTFT : délai avant le premier token visible. En mode qualité (pas de stream),
  l'utilisateur ne voit rien avant la fin : TTFT = total. Le mode stream est mesuré à part.

La mémoire longue et le journal sont redirigés vers des copies temporaires.

Usage :
    python scripts/mesurer_latence.py --n 10 --sortie logs/latence.json
"""

from __future__ import annotations

import argparse
import json
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

T0_PROCESSUS = time.perf_counter()

import config  # noqa: E402
import generation.llm_client as module_llm  # noqa: E402
from core.journal_amelioration import JournalAmelioration  # noqa: E402
from core.memoire_longue import MemoireLongue  # noqa: E402
from core.orchestrateur import OrchestrateurAssistant  # noqa: E402
from evaluation.jeux_questions import JEUX_QUESTIONS  # noqa: E402

QUESTIONS_REFERENCE = [
    "Comment créer une route GET avec FastAPI ?",
    "Comment écrire un Dockerfile multi-stage ?",
]


def _stats(valeurs):
    v = sorted(x for x in valeurs if x is not None)
    if not v:
        return None
    p95 = v[min(len(v) - 1, max(0, round(0.95 * (len(v) - 1))))]
    return {"n": len(v), "moyenne": round(statistics.fmean(v), 3), "mediane": round(statistics.median(v), 3),
            "p95": round(p95, 3), "min": round(v[0], 3), "max": round(v[-1], 3)}


class Chrono:
    """Enveloppe les appels coûteux de l'orchestrateur sans modifier le code de production."""

    def __init__(self, orch: OrchestrateurAssistant):
        self.mesures: dict = {}
        self._envelopper(orch.retrieval, "rechercher", "retrieval")
        self._envelopper(orch.searcher, "rechercher_multi", "web")
        self._envelopper(orch.llm_client, "invoke", "llm_appels")
        sleep_orig = module_llm.time.sleep

        def sleep_compte(s):
            self.mesures["attente_rate_limit"] = self.mesures.get("attente_rate_limit", 0.0) + s
            sleep_orig(s)

        class _Temps:
            sleep = staticmethod(sleep_compte)

            def __getattr__(self, nom):
                return getattr(time, nom)

        module_llm.time = _Temps()

    def _envelopper(self, obj, nom, cle):
        orig = getattr(obj, nom)

        def wrapper(*a, **k):
            t = time.perf_counter()
            try:
                return orig(*a, **k)
            finally:
                self.mesures.setdefault(cle, []).append(time.perf_counter() - t)

        setattr(obj, nom, wrapper)

    def reset(self):
        self.mesures = {}


def mesurer(orch, chrono, question, stream):
    chrono.reset()
    t = time.perf_counter()
    res = orch.repondre(question, stream=stream)
    ttft = None
    if res.stream is not None:
        for delta in res.stream:
            if delta and ttft is None:
                ttft = time.perf_counter() - t
    total = time.perf_counter() - t
    m = chrono.mesures
    retrieval = sum(m.get("retrieval", []))
    web = sum(m.get("web", []))
    llm = sum(m.get("llm_appels", []))
    return {
        "question": question,
        "mode": res.mode,
        "stream": res.stream is not None,
        "total_s": round(total, 3),
        "ttft_s": round(ttft if ttft is not None else total, 3),
        "retrieval_s": round(retrieval, 3),
        "web_s": round(web, 3),
        "llm_s": round(llm, 3) if not res.stream else None,
        "nb_appels_llm": len(m.get("llm_appels", [])) + (1 if res.stream is not None else 0),
        "attente_rate_limit_s": round(m.get("attente_rate_limit", 0.0), 3),
        "reste_s": round(total - retrieval - web - llm, 3) if res.stream is None else None,
        "generation_apres_ttft_s": round(total - ttft, 3) if ttft is not None else None,
        "nb_docs": len(res.documents or []),
        "nb_web": len(res.ressources_web or []),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=10, help="nombre total de questions (dont les 2 de référence)")
    p.add_argument("--sans-stream", action="store_true", help="ne pas mesurer le TTFT en mode stream")
    p.add_argument("--sortie", default=str(ROOT / "logs" / "latence.json"))
    p.add_argument("--pause", type=float, default=0.0,
                   help="secondes entre deux questions (quota Groq gratuit : 8 000 tokens/min)")
    args = p.parse_args()

    pas = max(1, len(JEUX_QUESTIONS) // max(1, args.n - 2))
    questions = QUESTIONS_REFERENCE + [q["question"] for q in JEUX_QUESTIONS[::pas]][: max(0, args.n - 2)]

    tmp = Path(tempfile.mkdtemp(prefix="latence_"))
    t = time.perf_counter()
    orch = OrchestrateurAssistant()
    chargement = time.perf_counter() - t
    orch.memoire_longue = MemoireLongue(chemin=tmp / "memoire.db")
    journal_reel = Path(config.PROJECT_ROOT) / "logs" / "interactions.jsonl"
    if journal_reel.exists():
        shutil.copy(journal_reel, tmp / "interactions.jsonl")
    orch.journal = JournalAmelioration(chemin=tmp / "interactions.jsonl")
    chrono = Chrono(orch)
    print(f"[chargement modèles] {chargement:.1f}s (processus : {time.perf_counter() - T0_PROCESSUS:.1f}s)")

    qualite = []
    for i, q in enumerate(questions):
        if i and args.pause:
            time.sleep(args.pause)
        r = mesurer(orch, chrono, q, stream="auto")
        r["froid"] = i == 0
        qualite.append(r)
        print(json.dumps(r, ensure_ascii=False))

    flux = []
    if not args.sans_stream:
        for q in questions:
            if args.pause:
                time.sleep(args.pause)
            r = mesurer(orch, chrono, q, stream=True)
            flux.append(r)
            print(json.dumps(r, ensure_ascii=False))

    chauds = [r for r in qualite if not r["froid"]]
    resume = {
        "methode": (
            "Orchestrateur.repondre() en processus local, Qdrant Docker, Groq "
            f"{getattr(orch.llm_client, 'modele', '?')}. Froid = chargement + 1re question ; chaud = suivantes. "
            "Mode auto (boucle qualité, sans stream) puis mêmes questions en stream=True pour le TTFT. "
            f"Pause entre questions : {args.pause}s."
        ),
        "pause_s": args.pause,
        "nb_questions": len(questions),
        "chargement_modeles_s": round(chargement, 3),
        "froid": qualite[0] if qualite else None,
        "chaud_auto": {k: _stats([r[k] for r in chauds]) for k in
                       ("total_s", "ttft_s", "retrieval_s", "web_s", "llm_s", "nb_appels_llm", "attente_rate_limit_s", "reste_s")},
        "stream": {k: _stats([r[k] for r in flux]) for k in
                   ("total_s", "ttft_s", "retrieval_s", "web_s", "generation_apres_ttft_s")} if flux else None,
        "details_auto": qualite,
        "details_stream": flux,
    }
    Path(args.sortie).write_text(json.dumps(resume, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: resume[k] for k in ("nb_questions", "chargement_modeles_s", "chaud_auto", "stream")},
                     ensure_ascii=False, indent=2))
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
