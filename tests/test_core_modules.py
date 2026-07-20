import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.classificateur import ClassificateurAssistant
from core.controleur_qualite import ControleurQualite
from core.planificateur import PlanificateurAssistant
from core.schemas import RapportQualite


def test_classificateur_detecte_maths():
    analyse = ClassificateurAssistant().analyser("Résous 2x + 5 = 17")
    assert analyse.mode == "maths"
    assert analyse.besoin_maths is True


def test_classificateur_detecte_technique_fastapi():
    analyse = ClassificateurAssistant().analyser("Comment créer un endpoint FastAPI avec Pydantic ?")
    assert analyse.mode == "technique"
    assert analyse.domaine == "fastapi"
    assert analyse.besoin_rag is True


def test_classificateur_projet_metier_sans_rag():
    """Quincaillerie / app métier : mentorat sans corpus GitHub forcé."""
    analyse = ClassificateurAssistant().analyser(
        "Aide-moi à créer une plateforme de gestion complète pour une quincaillerie"
    )
    assert analyse.mode == "projet"
    assert analyse.besoin_rag is False
    assert analyse.besoin_web is False
    assert analyse.besoin_abstention is False


def test_classificateur_projet_avec_stack_active_rag():
    analyse = ClassificateurAssistant().analyser(
        "Aide-moi à créer une API FastAPI de gestion de stock pour une quincaillerie"
    )
    assert analyse.mode == "projet"
    assert analyse.besoin_rag is True


def test_controleur_qualite_technique_insuffisant():
    analyse = ClassificateurAssistant().analyser("Comment créer une API Flask ?")
    plan = PlanificateurAssistant().construire_plan(analyse)
    rapport = ControleurQualite().verifier(
        "Utilise Flask.", analyse, plan, question="Comment créer une API Flask ?"
    )
    assert rapport.valide is False
    assert "bonnes_pratiques_absentes" in rapport.problemes or "exemple_absent" in rapport.problemes
    assert 0.0 <= rapport.score <= 1.0
    assert ControleurQualite().doit_regenerer(rapport) is True


def test_controleur_qualite_technique_solide():
    analyse = ClassificateurAssistant().analyser("Comment créer une API Flask ?")
    plan = PlanificateurAssistant().construire_plan(analyse)
    reponse = """
Flask est un micro-framework Python pour exposer des routes HTTP.

Exemple :
```python
from flask import Flask, jsonify
app = Flask(__name__)

@app.route("/hello")
def hello():
    return jsonify({"msg": "ok"})
```

Bonnes pratiques : utilise un blueprint et valide les entrées.
Erreur fréquente : oublier `app.run(debug=False)` en production.
"""
    rapport = ControleurQualite().verifier(
        reponse, analyse, plan, question="Comment créer une API Flask ?"
    )
    assert rapport.valide is True
    assert rapport.score >= 0.65
    assert ControleurQualite().doit_regenerer(rapport) is False


def test_feedback_regeneration_humanise_et_mode():
    analyse = ClassificateurAssistant().analyser("Comment créer une API Flask ?")
    plan = PlanificateurAssistant().construire_plan(analyse)
    rapport = ControleurQualite().verifier(
        "Bien sûr ! Court.", analyse, plan, question="Comment créer une API Flask ?"
    )
    feedback = ControleurQualite().construire_feedback_regeneration(
        rapport, analyse=analyse, question="Comment créer une API Flask ?"
    )
    assert "Réécris" in feedback or "Améliore" in feedback or "Corrige" in feedback
    assert "mode technique" in feedback.lower() or "bonnes pratiques" in feedback.lower()
    assert "Flask" in feedback


def test_choisir_meilleure_prefere_valide():
    cq = ControleurQualite()
    a = RapportQualite(valide=False, score=0.4, problemes=["code_absent"])
    b = RapportQualite(valide=True, score=0.8, problemes=[])
    texte, rapport = cq.choisir_meilleure("faible", a, "bonne réponse longue avec code", b)
    assert texte.startswith("bonne")
    assert rapport.valide is True


def test_detecte_ouverture_faible():
    analyse = ClassificateurAssistant().analyser("Comment créer une API FastAPI ?")
    plan = PlanificateurAssistant().construire_plan(analyse)
    rapport = ControleurQualite().verifier(
        "Bien sûr ! Je vais vous expliquer FastAPI rapidement sans code.",
        analyse,
        plan,
        question="Comment créer une API FastAPI ?",
    )
    assert "ouverture_faible" in rapport.problemes
