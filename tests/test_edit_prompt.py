"""Édition de prompt utilisateur : troncature de branche + relance."""

from app.edition_conversation import (
    appliquer_edition_contenu,
    appliquer_edition_prompt,
    edition_autorisee,
    resync_historique_llm,
)


def test_edition_prompt_tronque_la_branche():
    messages = [
        {"role": "user", "content": "Q1", "quota_decompte": True},
        {"role": "assistant", "content": "R1"},
        {"role": "user", "content": "Q2 ancienne", "quota_decompte": True},
        {"role": "assistant", "content": "R2 ancienne"},
        {"role": "user", "content": "Q3", "quota_decompte": True},
        {"role": "assistant", "content": "R3"},
    ]
    resultat = appliquer_edition_prompt(messages, 2, "Q2 améliorée avec FastAPI")
    assert resultat is not None
    maj, hist = resultat
    assert len(maj) == 3
    assert maj[2]["content"] == "Q2 améliorée avec FastAPI"
    # Le débit de quota du tour d'origine est conservé (pas de double consommation)
    assert maj[2].get("quota_decompte") is True
    assert hist == [
        {"role": "user", "content": "Q1"},
        {"role": "assistant", "content": "R1"},
        {"role": "user", "content": "Q2 améliorée avec FastAPI"},
    ]
    # L'historique d'origine n'est pas muté
    assert len(messages) == 6


def test_edition_contenu_sans_troncature():
    messages = [
        {"role": "user", "content": "Q"},
        {"role": "assistant", "content": "R ancienne"},
    ]
    maj = appliquer_edition_contenu(messages, 1, "R corrigée")
    assert maj is not None
    assert len(maj) == 2
    assert maj[1]["content"] == "R corrigée"
    assert resync_historique_llm(maj)[-1]["content"] == "R corrigée"


def test_edition_refuse_texte_vide_ou_index_invalide():
    messages = [{"role": "user", "content": "Q"}]
    assert appliquer_edition_prompt(messages, 0, "   ") is None
    assert appliquer_edition_prompt(messages, 5, "ok") is None
    assert appliquer_edition_contenu(messages, 0, "") is None


def test_edition_autorisee_selon_etat():
    assert edition_autorisee({"en_cours": False}, figee=False) is True
    assert edition_autorisee({"en_cours": True}, figee=False) is False
    assert edition_autorisee({"en_cours": False}, figee=True) is False
