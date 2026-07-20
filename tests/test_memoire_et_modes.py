import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.classificateur import ClassificateurAssistant
from core.constructeur_prompt import ConstructeurPrompt
from core.journal_amelioration import JournalAmelioration
from core.memoire_longue import MemoireLongue
from core.memoire_projet import MemoireProjet
from core.planificateur import PlanificateurAssistant


def test_classificateur_cours():
    analyse = ClassificateurAssistant().analyser("Fais un cours sur FastAPI pour débutants")
    assert analyse.mode == "cours"


def test_classificateur_resume():
    analyse = ClassificateurAssistant().analyser("Résume ce texte : FastAPI est un framework...")
    assert analyse.mode == "resume"


def test_classificateur_code():
    analyse = ClassificateurAssistant().analyser("Écris une fonction Python qui calcule la factorielle")
    assert analyse.mode == "code"
    assert analyse.besoin_code is True


def test_classificateur_perplexity():
    analyse = ClassificateurAssistant().analyser(
        "Quelle est la dernière version de FastAPI en 2026 ? sources web"
    )
    assert analyse.mode == "perplexity"
    assert analyse.besoin_web is True


def test_plan_cours_et_code():
    c = ClassificateurAssistant()
    p = PlanificateurAssistant()
    plan_cours = p.construire_plan(c.analyser("Fais un cours sur Docker"))
    assert "concepts clés" in " ".join(plan_cours.sections)
    plan_code = p.construire_plan(
        c.analyser("Écris une fonction Python qui calcule la factorielle")
    )
    assert plan_code.sections  # mode code
    assert any("test" in s for s in plan_code.sections)


def test_constitution_injectee(tmp_path):
    cp = ConstructeurPrompt()
    analyse = ClassificateurAssistant().analyser("Bonjour")
    plan = PlanificateurAssistant().construire_plan(analyse)
    system, user = cp.construire(
        question="Bonjour",
        analyse=analyse,
        plan=plan,
        documents=[],
        ressources_web=[],
    )
    assert "Constitution" in system or "Comprendre avant" in system
    assert "Compréhension" in user


def test_memoire_projet_erp():
    mp = MemoireProjet()
    ctx = mp.extraire_ou_mettre_a_jour(
        historique=[{"role": "user", "content": "Je crée un ERP avec FastAPI et PostgreSQL"}],
        question="Crée le modèle Produit",
        mode="projet",
    )
    assert ctx.actif is True
    assert "fastapi" in ctx.stack
    assert "postgresql" in ctx.stack
    txt = mp.formater_pour_prompt(ctx)
    assert "Mémoire temporaire" in txt
    assert "fastapi" in txt.lower()


def test_memoire_longue_et_journal(tmp_path):
    db = tmp_path / "prefs.db"
    ml = MemoireLongue(chemin=db)
    prefs = ml.mettre_a_jour_depuis_echange(
        "Je préfère FastAPI et des réponses détaillées",
        mode="technique",
    )
    assert "stacks" in prefs or "long" in prefs or "fastapi" in json.dumps(prefs)

    log = tmp_path / "interactions.jsonl"
    j = JournalAmelioration(chemin=log)
    j.enregistrer({"mode": "technique", "score_rag": 0.1, "feedback": -1})
    j.enregistrer({"mode": "technique", "score_rag": 0.15, "feedback": -1})
    synth = j.synthetiser()
    assert synth["n"] == 2
    assert synth["insights"]
