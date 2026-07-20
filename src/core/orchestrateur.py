"""Orchestrateur central de l'assistant."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, Union

from web import WebSearcher

from core.classificateur import ClassificateurAssistant
from core.constructeur_prompt import ConstructeurPrompt
from core.controleur_qualite import ControleurQualite
from core.journal_amelioration import JournalAmelioration
from core.memoire_longue import MemoireLongue
from core.memoire_projet import MemoireProjet
from core.memoire_reponse import MemoireReponse
from core.schemas import AnalyseQuestion, ResultatOrchestration
from core.planificateur import PlanificateurAssistant
from generation.llm_client import LLMClient
from retrieval.citations import construire_bloc_citations, enrichir_document
from retrieval.retrieval_hybride import RetrievalHybride

# Signaux qui poussent vers le web même si le RAG est correct
_SIGNES_WEB_PRIORITAIRE = (
    "actualité", "actualite", "news", "2024", "2025", "2026",
    "dernière version", "derniere version", "latest", "changelog",
    "prix", "tarif", "official docs", "documentation officielle",
    "site officiel", "télécharger", "telecharger", "release",
)

# Modes où le corpus GitHub est en général suffisant
_MODES_RAG_FORT = {"technique", "debug", "documentation", "code"}
# Modes où le web apporte souvent un vrai plus (pas le mentorat projet)
_MODES_WEB_UTILE = {"explication", "comparaison", "analyse", "cours", "expert", "perplexity"}
# Modes où on force la boucle qualité (pas de stream)
_MODES_QUALITE = {
    "technique", "debug", "projet", "comparaison", "code",
    "cours", "expert", "documentation", "analyse", "perplexity",
}
# Sous ce seuil, on ignore les docs (pas de fausses citations)
_SEUIL_CITATION_MIN = 0.45


class OrchestrateurAssistant:
    def __init__(
        self,
        retrieval: Optional[RetrievalHybride] = None,
        llm_client: Optional[LLMClient] = None,
    ):
        self.retrieval = retrieval or RetrievalHybride()
        self.llm_client = llm_client or LLMClient()
        self.searcher = WebSearcher()
        self.classificateur = ClassificateurAssistant()
        self.planificateur = PlanificateurAssistant()
        self.constructeur_prompt = ConstructeurPrompt()
        self.controleur_qualite = ControleurQualite()
        self.memoire = MemoireReponse()
        self.memoire_longue = MemoireLongue()
        self.memoire_projet = MemoireProjet()
        self.journal = JournalAmelioration()

    def repondre(
        self,
        question: str,
        historique: Optional[List[Dict]] = None,
        fichiers: Optional[List[Dict]] = None,
        filtres: Optional[Dict] = None,
        top_k: int = 5,
        stream: Union[bool, str] = "auto",
        mode_force: Optional[str] = None,
        contexte_projet_existant: Optional[Dict[str, Any]] = None,
        utiliser_corpus: bool = True,
    ) -> ResultatOrchestration:
        historique = historique or []
        fichiers = fichiers or []
        # Vision réelle : analyser les images avant classification / prompt
        if any(f.get("type") == "image" and f.get("image_b64") for f in fichiers):
            try:
                from app.gestionnaire_fichiers import analyser_images_vision

                fichiers = analyser_images_vision(
                    fichiers, question=question, llm_client=self.llm_client
                )
            except Exception:
                pass
        contexte_fichiers = self._formater_fichiers(fichiers)

        # Génération d'image (hors pipeline RAG)
        from generation.generateur_reponse import demande_generation_image

        if demande_generation_image(question) and mode_force not in {"cdc", "projet"}:
            return self._repondre_generation_image(
                question=question,
                historique=historique,
                contexte_fichiers=contexte_fichiers,
                contexte_projet_existant=contexte_projet_existant,
            )

        # Passe 1 — compréhension / classification
        analyse = self.classificateur.analyser(
            question=question if not contexte_fichiers else f"{question}\n{contexte_fichiers}",
            mode_force=mode_force,
            a_un_fichier=bool(fichiers),
        )

        # Insights logs → peut pousser web si RAG souvent faible
        insights_txt = self.journal.formater_insights_prompt()
        if "score_rag_faible" in insights_txt and analyse.mode in _MODES_RAG_FORT:
            analyse.besoin_web = True
            analyse.notes = list(analyse.notes) + ["insight:web_renforce"]

        # Passe 2 — plan
        plan = self.planificateur.construire_plan(analyse)
        comprehension = self.constructeur_prompt.construire_comprehension(analyse, question)

        # Mémoires
        prefs_session = self.memoire.extraire_preferences(historique)
        prefs_longues = self.memoire_longue.mettre_a_jour_depuis_echange(question, mode=analyse.mode)
        ctx_projet = self.memoire_projet.extraire_ou_mettre_a_jour(
            historique=historique,
            question=question,
            mode=analyse.mode,
            existant=contexte_projet_existant,
        )
        contexte_projet_txt = self.memoire_projet.formater_pour_prompt(ctx_projet)

        # Décision initiale fine RAG / Web / les deux
        faire_rag, faire_web = self._choisir_sources_initial(analyse, question)
        # Toggle fichier + corpus : force / coupe le RAG explicitement
        if fichiers:
            if utiliser_corpus:
                faire_rag = True
                analyse.notes = list(analyse.notes) + ["fichier+corpus"]
            else:
                faire_rag = False
                analyse.notes = list(analyse.notes) + ["fichier_seul"]
        analyse.besoin_rag = faire_rag
        analyse.besoin_web = faire_web
        analyse.strategie_sources = self._nommer_strategie(faire_rag, faire_web)
        analyse.notes = list(analyse.notes) + [f"sources:{analyse.strategie_sources}"]

        documents: List[Dict] = []
        ressources_web: List[Dict] = []

        if faire_rag:
            documents = self.retrieval.rechercher(
                question,
                top_k_retrieval=20,
                top_k_final=top_k,
                filtres=filtres,
            )
            documents = [enrichir_document(d) for d in documents]
            # Jeter les hits faibles / hors sujet (ex. Next.js pour une quincaillerie)
            avant = len(documents)
            documents = self._filtrer_docs_fiables(documents, question=question)
            if avant and not documents:
                analyse.notes = list(analyse.notes) + ["rag_faible_ignore"]
                faire_rag = False

        # Vérification RAG → web si insuffisant
        faire_web = self._ajuster_web_apres_rag(analyse, question, documents, faire_web)
        # Mode Perplexity : forcer web
        if analyse.mode == "perplexity":
            faire_web = True
        # Mentorat projet : pas de web forcé ni de sources fantômes
        if analyse.mode == "projet" and not documents:
            faire_web = False
        analyse.besoin_web = faire_web
        analyse.strategie_sources = self._nommer_strategie(bool(documents), faire_web)

        score_rag = self._score_rag(documents)

        abstention = (
            analyse.besoin_abstention
            and not fichiers
            and faire_rag
            and not faire_web
            and self.retrieval.doit_sabstenir(documents)
        )
        if abstention:
            resultat = ResultatOrchestration(
                analyse=analyse,
                plan=plan,
                documents=[],
                ressources_web=[],
                reponse=(
                    "Je n'ai pas trouvé de passages suffisamment fiables dans le corpus pour "
                    "répondre avec confiance. Reformulez la question, élargissez les filtres "
                    "ou joignez un fichier pertinent."
                ),
                reponse_seule=(
                    "Je n'ai pas trouvé de passages suffisamment fiables dans le corpus pour "
                    "répondre avec confiance. Reformulez la question, élargissez les filtres "
                    "ou joignez un fichier pertinent."
                ),
                mode="abstention",
                abstention=True,
                contexte_projet=ctx_projet.to_dict(),
                preferences_longues=prefs_longues,
                score_rag=score_rag,
            )
            self._journaliser(question, resultat, latence=0.0, regen=0)
            return resultat

        if faire_web:
            try:
                ressources_web = self.searcher.rechercher_multi(question)
            except Exception:
                ressources_web = []

        # Si on est en hybride/web fort avec beaucoup de sources → mode perplexity soft
        if (
            analyse.mode not in {"projet", "code", "debug", "cours", "expert"}
            and faire_web
            and (not documents or score_rag < 0.25)
            and len(ressources_web) >= 3
            and analyse.mode in {"explication", "perplexity", "technique"}
        ):
            if analyse.mode == "explication" or analyse.mode == "perplexity":
                analyse.mode = "perplexity"
                plan = self.planificateur.construire_plan(analyse)

        prompt_systeme, prompt_utilisateur = self.constructeur_prompt.construire(
            question=question,
            analyse=analyse,
            plan=plan,
            documents=documents,
            ressources_web=ressources_web,
            historique=historique,
            contexte_fichiers=contexte_fichiers,
            preferences=prefs_session,
            preferences_longues=prefs_longues,
            contexte_projet=contexte_projet_txt,
            insights=insights_txt,
            comprehension=comprehension,
        )

        messages = [{"role": "system", "content": prompt_systeme}]
        if historique:
            messages.extend(historique[-8:])
        messages.append({"role": "user", "content": prompt_utilisateur})

        citations = construire_bloc_citations(
            documents, ressources_web, mode_expert=(analyse.mode in {"expert", "cours"})
        )
        mode_retour = analyse.mode

        # stream=auto : conversation/rédaction streamées ; le reste avec critique
        if stream == "auto":
            utiliser_stream = analyse.mode not in _MODES_QUALITE
        else:
            utiliser_stream = bool(stream)

        if utiliser_stream:
            usage_holder: Dict = {"tokens_utilises": 0}

            def _flux():
                for delta in self.llm_client.stream(messages, usage_holder):
                    yield delta

            resultat = ResultatOrchestration(
                analyse=analyse,
                plan=plan,
                documents=documents,
                ressources_web=ressources_web,
                prompt_systeme=prompt_systeme,
                prompt_utilisateur=prompt_utilisateur,
                citations=citations,
                mode=mode_retour,
                tokens_utilises=0,
                usage_holder=usage_holder,
                stream=_flux(),
                contexte_projet=ctx_projet.to_dict(),
                preferences_longues=prefs_longues,
                score_rag=score_rag,
                meta_journal={
                    "strategie_sources": analyse.strategie_sources,
                    "web_utile": bool(ressources_web),
                },
            )
            return resultat

        # Passe 3 — génération
        reponse, tokens = self.llm_client.invoke(messages)
        # Passe 4 — critique heuristique
        rapport = self.controleur_qualite.verifier(
            reponse, analyse, plan, question=question
        )

        # Passe 5 — amélioration / régénération
        max_regen = 2
        tentatives = 0
        while (
            tentatives < max_regen
            and self.controleur_qualite.doit_regenerer(rapport)
        ):
            feedback = self.controleur_qualite.construire_feedback_regeneration(
                rapport, analyse=analyse, question=question
            )
            if not feedback:
                break
            tentatives += 1
            temp_orig = self.llm_client.temperature
            try:
                self.llm_client.temperature = max(0.1, temp_orig - 0.1 * tentatives)
                messages_corriges = list(messages) + [
                    {"role": "assistant", "content": reponse},
                    {
                        "role": "user",
                        "content": (
                            "Tu es un expert senior. Analyse la réponse précédente.\n"
                            "Est-elle complète, exacte ? Manque-t-il infos, exemples, code, bonnes pratiques ?\n"
                            f"{feedback}\n"
                            "Réécris une meilleure version finale."
                        ),
                    },
                ]
                reponse_corrigee, tokens_2 = self.llm_client.invoke(messages_corriges)
            finally:
                self.llm_client.temperature = temp_orig

            if not reponse_corrigee or reponse_corrigee.startswith("❌ Erreur"):
                break

            rapport_2 = self.controleur_qualite.verifier(
                reponse_corrigee, analyse, plan, question=question
            )
            reponse, rapport = self.controleur_qualite.choisir_meilleure(
                reponse, rapport, reponse_corrigee, rapport_2
            )
            tokens += tokens_2
            if rapport.valide:
                break

        if tentatives:
            analyse.notes = list(analyse.notes) + [f"regen:{tentatives}"]
            rapport.commentaire = (
                f"{rapport.commentaire} (régénération×{tentatives})"
            ).strip()

        reponse_complete = reponse.strip()
        if citations and "📚" not in reponse_complete and "🌐" not in reponse_complete:
            reponse_complete += "\n\n---\n\n" + citations

        resultat = ResultatOrchestration(
            analyse=analyse,
            plan=plan,
            documents=documents,
            ressources_web=ressources_web,
            prompt_systeme=prompt_systeme,
            prompt_utilisateur=prompt_utilisateur,
            reponse=reponse_complete,
            reponse_seule=reponse.strip(),
            citations=citations,
            mode=mode_retour,
            tokens_utilises=tokens,
            rapport_qualite=rapport,
            abstention=False,
            contexte_projet=ctx_projet.to_dict(),
            preferences_longues=prefs_longues,
            score_rag=score_rag,
            meta_journal={
                "strategie_sources": analyse.strategie_sources,
                "web_utile": bool(ressources_web),
                "regen": tentatives,
                "score_qualite": getattr(rapport, "score", None),
            },
        )
        self._journaliser(question, resultat, latence=0.0, regen=tentatives)
        return resultat

    def journaliser_feedback(
        self,
        question: str,
        mode: str,
        note: int,
        score_rag: float = 0.0,
        meta: Optional[Dict] = None,
    ) -> None:
        payload = {
            "question": (question or "")[:300],
            "mode": mode,
            "feedback": int(note),
            "score_rag": score_rag,
        }
        if meta:
            payload.update(meta)
        self.journal.enregistrer(payload)

    def _repondre_generation_image(
        self,
        question: str,
        historique: List[Dict],
        contexte_fichiers: str,
        contexte_projet_existant: Optional[Dict[str, Any]],
    ) -> ResultatOrchestration:
        """Branche dédiée : créer une image puis répondre brièvement."""
        from generation.generateur_image import disponible, generer_image, raffiner_prompt_image

        analyse = AnalyseQuestion(
            mode="image",
            domaine="general",
            complexite="simple",
            besoin_rag=False,
            besoin_web=False,
            strategie_sources="aucune",
            notes=["generation_image"],
        )
        plan = self.planificateur.construire_plan(analyse)
        ctx_projet = self.memoire_projet.extraire_ou_mettre_a_jour(
            historique=historique,
            question=question,
            mode="image",
            existant=contexte_projet_existant,
        )

        if not disponible():
            msg = (
                "La génération d'images est désactivée. "
                "Configurez `IMAGE_GEN_PROVIDER=pollinations` (défaut) ou une clé OpenAI."
            )
            return ResultatOrchestration(
                analyse=analyse,
                plan=plan,
                reponse=msg,
                reponse_seule=msg,
                mode="image",
                contexte_projet=ctx_projet.to_dict(),
                images_generees=[],
            )

        base = question
        if contexte_fichiers:
            base = f"{question}\n\nContexte images/fichiers joints :\n{contexte_fichiers[:1500]}"
        prompt_img = raffiner_prompt_image(base, self.llm_client)
        resultat_img = generer_image(prompt_img)

        images: List[Dict[str, Any]] = []
        if resultat_img.get("ok") and resultat_img.get("b64"):
            images.append(
                {
                    "b64": resultat_img["b64"],
                    "media_type": resultat_img.get("media_type") or "image/png",
                    "caption": prompt_img,
                    "provider": resultat_img.get("provider") or "",
                }
            )
            texte = (
                f"Voici l'illustration générée.\n\n"
                f"**Prompt :** {prompt_img}\n\n"
                f"_Provider : {resultat_img.get('provider')}_"
            )
        else:
            err = resultat_img.get("erreur") or "inconnu"
            texte = (
                f"Je n'ai pas pu générer l'image ({err}).\n\n"
                f"Prompt tenté : `{prompt_img}`\n\n"
                "Réessayez avec une description plus courte, ou configurez `OPENAI_API_KEY`."
            )

        return ResultatOrchestration(
            analyse=analyse,
            plan=plan,
            reponse=texte,
            reponse_seule=texte,
            mode="image",
            tokens_utilises=0,
            contexte_projet=ctx_projet.to_dict(),
            images_generees=images,
            meta_journal={"generation_image": True, "prompt": prompt_img[:200]},
        )

    def _journaliser(
        self,
        question: str,
        resultat: ResultatOrchestration,
        latence: float,
        regen: int,
    ) -> None:
        meta = dict(resultat.meta_journal or {})
        self.journal.enregistrer(
            {
                "question": (question or "")[:300],
                "mode": resultat.mode,
                "strategie_sources": resultat.analyse.strategie_sources,
                "score_rag": resultat.score_rag,
                "tokens": resultat.tokens_utilises,
                "latence": latence,
                "regen": regen,
                "web_utile": meta.get("web_utile", bool(resultat.ressources_web)),
                "nb_docs": len(resultat.documents or []),
                "nb_web": len(resultat.ressources_web or []),
                "score_qualite": meta.get("score_qualite"),
                "abstention": resultat.abstention,
            }
        )

    @staticmethod
    def _score_rag(documents: List[Dict]) -> float:
        if not documents:
            return 0.0
        vals = [float(d.get("score_confiance") or 0) for d in documents]
        return max(vals) if vals else 0.0

    @staticmethod
    def _filtrer_docs_fiables(
        documents: List[Dict],
        seuil: float = _SEUIL_CITATION_MIN,
        question: str = "",
    ) -> List[Dict]:
        """Ne garde que les documents assez confiants et un minimum pertinents."""
        import re

        tokens = {
            t
            for t in re.findall(r"[a-zàâçéèêëîïôùûü0-9_]{4,}", (question or "").lower())
            if t not in {
                "avec", "pour", "dans", "une", "des", "les", "comment",
                "quoi", "fait", "faire", "aide", "créer", "creer", "projet",
            }
        }
        fiables = []
        for d in documents or []:
            try:
                score = float(d.get("score_confiance") or 0)
            except (TypeError, ValueError):
                score = 0.0
            if score < seuil:
                continue
            if tokens:
                hay = " ".join(
                    str(d.get(k) or "")
                    for k in ("texte", "nom_complet", "section_titre", "source_file", "theme")
                ).lower()
                if not any(tok in hay for tok in tokens):
                    # Score élevé seul ne suffit pas s'il n'y a aucun chevauchement lexical
                    if score < 0.70:
                        continue
            fiables.append(d)
        return fiables

    def _choisir_sources_initial(
        self, analyse: AnalyseQuestion, question: str
    ) -> Tuple[bool, bool]:
        """Décide RAG / Web / les deux avant retrieval, de façon plus fine que le mode seul."""
        q_low = (question or "").lower()
        mode = analyse.mode

        if mode in {"conversation", "maths", "redaction", "resume"}:
            return False, False

        if mode == "perplexity":
            return False, True

        # Mentorat projet : corpus seulement si stack documentée ciblée
        if mode == "projet":
            stack = analyse.domaine in {
                "fastapi", "flask", "django", "react", "docker", "jwt", "python", "sql",
            } or any(
                k in q_low
                for k in (
                    "fastapi", "flask", "django", "react", "docker", "jwt",
                    "postgres", "postgresql", "sqlite", "sqlalchemy",
                )
            )
            web = any(s in q_low for s in _SIGNES_WEB_PRIORITAIRE)
            return stack, web

        faire_rag = analyse.besoin_rag
        faire_web = analyse.besoin_web

        if analyse.domaine in {"fastapi", "flask", "django", "react", "docker", "jwt", "python", "sql"}:
            faire_rag = True
            if mode in _MODES_RAG_FORT and analyse.complexite == "simple":
                faire_web = False

        if any(s in q_low for s in _SIGNES_WEB_PRIORITAIRE):
            faire_web = True

        if mode in _MODES_WEB_UTILE:
            faire_web = True
            if mode == "comparaison":
                faire_rag = True

        if mode == "debug" and analyse.domaine != "general":
            faire_rag = True
            faire_web = analyse.complexite == "complexe"

        if mode == "documentation":
            faire_rag = True
            faire_web = any(s in q_low for s in ("officiel", "latest", "changelog", "release"))

        if mode in {"cours", "expert"}:
            faire_rag = True
            faire_web = analyse.complexite != "simple"

        if mode == "code":
            faire_rag = True
            faire_web = False

        return faire_rag, faire_web

    def _ajuster_web_apres_rag(
        self,
        analyse: AnalyseQuestion,
        question: str,
        documents: List[Dict],
        faire_web: bool,
    ) -> bool:
        """Affine le besoin web selon la confiance réelle du retrieval."""
        q_low = (question or "").lower()

        if any(s in q_low for s in _SIGNES_WEB_PRIORITAIRE):
            return True
        if analyse.mode == "perplexity":
            return True
        # Projet métier (quincaillerie, etc.) : rester en mentorat, pas de web forcé
        if analyse.mode == "projet":
            return bool(faire_web)

        if not documents:
            if analyse.mode in {
                "technique", "debug", "comparaison", "explication",
                "documentation", "cours", "expert", "code",
            }:
                return True
            return faire_web

        confiances = [float(d.get("score_confiance") or 0) for d in documents]
        best = max(confiances) if confiances else 0.0
        moyenne = sum(confiances) / len(confiances)

        if best >= 0.55 and moyenne >= 0.35 and analyse.mode in _MODES_RAG_FORT:
            return False

        if best < 0.22 or self.retrieval.doit_sabstenir(documents):
            return True

        if analyse.mode in {"comparaison", "cours", "expert"} and analyse.complexite != "simple":
            return True

        return faire_web

    @staticmethod
    def _nommer_strategie(faire_rag: bool, faire_web: bool) -> str:
        if faire_rag and faire_web:
            return "hybride"
        if faire_rag:
            return "rag"
        if faire_web:
            return "web"
        return "aucune"

    def _formater_fichiers(self, fichiers: List[Dict]) -> str:
        if not fichiers:
            return ""
        blocs = []
        for f in fichiers:
            nom = f.get("nom", "fichier")
            contenu = f.get("contenu", "")
            langage = f.get("langage", "texte")
            if f.get("type") == "image" and contenu:
                tag = "image analysée" if f.get("vision_ok") else "image"
                blocs.append(f"[{nom} | {tag}]\n{contenu[:4000]}")
            elif contenu:
                blocs.append(f"[{nom} | {langage}]\n{contenu[:4000]}")
        return "\n\n".join(blocs)

    def _construire_citations(self, documents: List[Dict], ressources: List[Dict]) -> str:
        """Compat : délègue au formateur expert."""
        return construire_bloc_citations(documents, ressources, mode_expert=True)
