"""
Module de génération de réponses — Mentor / Architecte
Pipeline : intention → format (code|roadmap|projet|…) → docs → rédaction → qualité
ISI KOMUNIK · Master IAGE
"""

import os
import re
import time
from typing import List, Dict, Optional
from dotenv import load_dotenv
from web import WebSearcher
from web.config import web_search_desactive, web_timeout
from generation.llm_client import LLMClient, tronquer_messages

load_dotenv()

# Compat : flags lus dynamiquement (toggle UI peut les modifier via web.config / env)
WEB_SEARCH_DESACTIVE = web_search_desactive()
MODE_RAGAS_EVAL = os.getenv("MODE_RAGAS_EVAL", "false").lower() == "true"
WEB_TIMEOUT = web_timeout()


# ════════════════════════════════════════════════════════════════
# PROMPT SYSTÈME — ADAPTATIF
# ════════════════════════════════════════════════════════════════

PROMPT_SYSTEME = """Tu es AssistDoc — assistant intelligent francophone de niveau professionnel.

MISSION GÉNÉRALE
- Comprendre précisément l'intention réelle de l'utilisateur avant de répondre.
- Répondre directement à la question dès le début.
- Donner une réponse exacte, utile, rigoureuse, naturelle et directement exploitable.
- Rester strictement dans le sujet demandé.
- Adapter la longueur, le ton et le niveau de détail au contexte.

RÈGLES DE QUALITÉ OBLIGATOIRES
1. Réponds toujours en français, sauf si une autre langue est demandée.
2. Privilégie la clarté avant la quantité.
3. Évite les réponses vagues, répétitives, incohérentes ou hors sujet.
4. N'invente jamais de faits, de commandes, d'API ou d'informations incertaines.
5. Si une information est incertaine, dis-le clairement.
6. Si la demande est ambiguë, pose une question de clarification ou annonce l'hypothèse choisie.
7. Si la demande est complexe, structure la réponse avec des titres et des étapes.

MODES DE RÉPONSE

CONVERSATION
- Ton humain, chaleureux, naturel et professionnel.
- Pas de structure lourde si elle n'apporte rien.
- Réponse concise pour les questions simples.

TECHNIQUE
- Explique d'abord le concept.
- Ensuite, détaille l'implémentation étape par étape.
- Fournis du code complet, exécutable et commenté quand du code est demandé ou utile.
- Explique les parties importantes du code.
- Mentionne les bonnes pratiques, les pièges courants et les alternatives pertinentes.
- Termine par une courte conclusion ou les prochaines étapes.

MATHÉMATIQUES / EXERCICES
- Rappelle brièvement la méthode.
- Présente les calculs ligne par ligne.
- Explique les transformations importantes.
- Ne compacte jamais plusieurs opérations sur une seule ligne.
- Termine par une réponse finale clairement indiquée.
- Si plusieurs questions sont posées, réponds dans l'ordre.

RÉDACTION
- Rédige directement le texte final.
- Adapte le ton : formel, cordial, neutre, amical ou persuasif.
- Si plusieurs versions sont utiles, propose-les.

RECHERCHE / EXPLICATION
- Commence par la réponse courte.
- Développe ensuite les points importants.
- Compare les options de manière équilibrée.
- Mets en avant avantages, limites et cas d'usage.

PROJET COMPLET
- Commence par une vue d'ensemble.
- Propose l'architecture.
- Donne une feuille de route complète.
- Détaille uniquement la première étape.
- Attends implicitement la confirmation avant de passer à l'étape suivante.
- Donne les fichiers à créer, le code complet de l'étape en cours et les tests à effectuer.

RÈGLES CORPUS / SOURCES
- Utilise les documents du corpus seulement s'ils sont pertinents.
- Priorise `enrichissement/` et `knowledge/` s'ils correspondent vraiment au sujet.
- N'affirme jamais être « limité aux documents ».
- Utilise les sources pour renforcer la réponse, pas pour la rendre artificielle.

À ÉVITER
- Répondre hors sujet
- Donner une réponse générique quand une réponse précise est possible
- Répéter la même idée
- Utiliser une structure lourde pour une question simple
- Donner du code incomplet sans le signaler
"""

PROMPT_SYSTEME_LEGER = """Tu es AssistDoc — assistant intelligent francophone, clair et professionnel.
Réponds d'abord directement à la question, puis développe seulement si nécessaire.
En technique : explique le concept, puis l'implémentation, les bonnes pratiques, les erreurs fréquentes et les prochaines étapes.
En conversation : ton naturel, fluide, humain.
En maths : méthode, calculs ligne par ligne, réponse finale claire.
Interdit : faits inventés, réponses hors sujet, code incomplet non signalé, commandes CLI inventées.
Priorité aux docs pertinents ; ignore les documents hors sujet.
"""

PROMPT_UTILISATEUR_TECHNIQUE = """Contexte — Documents du corpus (pertinents uniquement) :

{contexte}

---

Ressources web (documentation / tutoriels) :
{ressources_web}

---

Question : {question}

Format CODE obligatoire :
## Explication
## Architecture / approche
## Code
(blocs COMPLETS, commentés, prêts à coller)
## Pourquoi ce code
## Alternatives
## Erreurs fréquentes
## Bonnes pratiques
## Prochaines étapes
### Ressources pour aller plus loin
(reprends les liens web utiles en markdown)

Réponds en français. Sois exhaustif et pédagogique (vise 600+ mots si le sujet le mérite).
"""

PROMPT_UTILISATEUR_ROADMAP = """Contexte corpus (ignore si hors sujet) :

{contexte}

---

Ressources web :
{ressources_web}

---

Demande de roadmap / parcours : {question}

Format ROADMAP obligatoire :
## Objectif
## Compétences nécessaires
## Technologies recommandées
## Architecture / vision d'ensemble
## Étapes (numérotées, progressives)
## Difficultés & pièges
## Temps estimé (réaliste)
## Conseils de mentor
## Ressources

Justifie chaque choix. Pas de liste sèche sans explication.
"""

# Prompt dédié à l'évaluation RAGAS (fidélité aux contextes)
PROMPT_SYSTEME_RAGAS = """Tu es un assistant RAG francophone. Tu réponds UNIQUEMENT à partir des documents fournis.

Règles strictes :
1. Base-toi uniquement sur les faits des documents. N'invente rien.
2. Ignore les passages hors sujet (autre langue, autre techno, changelog, tests mock...).
3. Réponds en français, 80 à 180 mots maximum.
4. La PREMIÈRE phrase doit répondre directement à la question en reprenant ses mots-clés.
5. Ne dis jamais « selon les documents », « Doc 1 », « fournis », etc.
6. Pas de YouTube / ressources externes.
7. Un seul petit exemple de code si le contexte le justifie.
"""

PROMPT_UTILISATEUR_RAGAS = """Documents récupérés :

{contexte}

---

Question : {question}

Réponds DIRECTEMENT à la question, de façon concise et fidèle (première phrase = réponse claire).
"""

PROMPT_UTILISATEUR_SIMPLE = """Question / Message de l'utilisateur : {question}

Réponds de manière naturelle et adaptée à la demande. Si des informations
techniques du corpus ci-dessous sont pertinentes, utilise-les ; sinon ignore-les.

{contexte}
"""

PROMPT_UTILISATEUR_MATHS = """Exercice / question de mathématiques :

{question}

Format obligatoire :
## Méthode
Une phrase sur ce qu'il faut faire.

## Calcul
Étapes une par une, avec des sauts de ligne entre chaque transformation.

## Réponse
Résultat final clairement indiqué.

Règles :
- Explique brièvement chaque transformation importante.
- Ne compacte jamais plusieurs opérations sur une seule ligne.
- Vérifie le résultat si c'est utile.
"""

PROMPT_UTILISATEUR_PROJET = """L'utilisateur souhaite réaliser un PROJET COMPLET :

{question}

{contexte}

Format PROJET obligatoire (mentor / chef de projet) :

## Analyse de la demande
Objectif réel, utilisateurs, contraintes, niveau estimé.

## Architecture
Vue d'ensemble (couches / modules) — simple et évolutive.

## Choix techniques
Stack recommandée + pourquoi (+ 1–2 alternatives écartées).

## Roadmap
Toutes les étapes numérotées (Étape 1…N), une phrase chacune.

## Organisation des dossiers
Arborescence proposée.

## Modules
Responsabilités de chaque module.

## Planning indicatif
Ordre + effort relatif (S/M/L).

## Risques
Techniques et projet + mitigations.

## Évolutions futures
Hors MVP.

## Étape 1 — [titre] (DÉTAILLÉE)
Explications + commandes + code complet + fichiers à créer.
C'est la seule étape à détailler complètement maintenant.

## Prochaines étapes
Invite à demander « étape suivante ».

RÈGLES :
- Pas tout coder d'un coup.
- Interdit : `fastapi new` / CLI inventées.
- Priorité aux docs `enrichissement/projet-*` et `knowledge/`.
- App tâches : `Tache`/`TacheCreate` (titre, fait), PAS `Item(name, price)`.
- FastAPI : venv → pip → main.py → `uvicorn` ; activation Windows + Linux/Mac.
- Ignore les docs hors sujet.
"""


# ════════════════════════════════════════════════════════════════
# DÉTECTION DU TYPE DE DEMANDE
# ════════════════════════════════════════════════════════════════

MOTS_CLES_TECHNIQUES = {
    'code', 'fonction', 'classe', 'variable', 'algorithme', 'algorithm',
    'script', 'programme', 'programmation', 'développer', 'implémenter',
    'implement', 'debug', 'bug', 'erreur', 'error', 'exception',
    'python', 'javascript', 'typescript', 'java', 'sql', 'react', 'vue',
    'angular', 'node', 'flask', 'django', 'fastapi', 'docker', 'kubernetes',
    'api', 'rest', 'graphql', 'json', 'yaml', 'html', 'css',
    'base de données', 'database', 'orm', 'sqlalchemy', 'requête',
    'serveur', 'server', 'backend', 'frontend', 'framework', 'librairie',
    'library', 'package', 'module', 'import', 'export', 'syntaxe',
    'syntax', 'compiler', 'compilation', 'git', 'github', 'déploiement',
    'deploy', 'authentification', 'jwt', 'oauth', 'middleware', 'hook',
    'composant', 'component', 'endpoint', 'route', 'pipeline', 'docker',
    'conteneur', 'container', 'test', 'pytest', 'unittest',
}


MOTS_CLES_EXPLICATION = {
    'explique', 'explication', 'qu\'est-ce que', 'qu est ce que', 'c\'est quoi',
    'parle-moi', 'parle moi', 'présente', 'présentation', 'définition',
    'définis', 'comprendre', 'apprendre', 'différence entre', 'avantages',
    'inconvénients', 'comment fonctionne', 'principe', 'concept', 'théorie',
    'historique de', 'qu\'est ce', 'machine learning', 'deep learning',
    'intelligence artificielle', 'data science', 'algorithme de',
}

MOTS_CLES_MATHS = {
    "résous", "resous", "calcule", "simplifie", "dérive", "derive",
    "intègre", "integre", "équation", "equation", "fraction", "racine",
    "matrice", "probabilité", "probabilite", "statistique", "limite",
    "suite", "trinôme", "trinome", "vecteur", "géométrie", "geometrie",
}


def est_demande_technique(question: str) -> bool:
    """Détecte si la question nécessite une réponse technique structurée (code)"""
    q = question.lower()

    if '```' in question or 'def ' in question or 'function ' in question:
        return True

    nb_mots_cles = sum(1 for mot in MOTS_CLES_TECHNIQUES if mot in q)
    return nb_mots_cles >= 1


def necessite_recherche_web(question: str) -> bool:
    """Détecte si la question mérite des liens/ressources web réels,
    même en mode conversationnel (sujets éducatifs, explications, etc.)"""
    q = question.lower()

    if est_demande_technique(question):
        return True

    return any(mot in q for mot in MOTS_CLES_EXPLICATION)


def est_demande_maths(question: str) -> bool:
    """Détecte un exercice ou une question mathématique/scolaire."""
    q = question.lower()
    if any(m in q for m in MOTS_CLES_MATHS):
        return True
    return bool(re.search(r"\d+\s*[\+\-\*/=]\s*\d+", q))


# Mots indiquant une demande EXPLICITE de code (utile quand un fichier est joint)
MOTS_CODE_EXPLICITE = {
    'montre-moi le code', 'montre le code', 'écris le code', 'écris du code',
    'écris une fonction', 'génère le code', 'génère du code', 'code pour',
    'donne-moi le code', 'donne le code', 'implémente', 'programme-moi',
    'écris un script', 'crée une fonction', 'exemple de code',
}


def demande_code_explicite(question: str) -> bool:
    """Vrai si l'utilisateur réclame explicitement du code (même avec un fichier joint)."""
    q = question.lower()
    return any(mot in q for mot in MOTS_CODE_EXPLICITE)


# Salutations / petite conversation — pas de RAG ni de liens sources
_MOTS_SALUTATION = {
    "salut", "hello", "hi", "hey", "bonjour", "bonsoir", "coucou",
    "yo", "hola", "slt", "bjr", "bsr", "cc", "re", "wesh",
}
_MOTS_POLITESSE = {
    "merci", "mercii", "thanks", "thank you", "ok", "okay", "d'accord",
    "dac", "super", "parfait", "top", "cool", "nickel", "bye", "au revoir",
    "à bientôt", "a bientot", "bonne journée", "bonne soiree", "bonne soirée",
}


def demande_generation_image(question: str) -> bool:
    """Vrai si l'utilisateur demande de créer / dessiner une image (pas une image Docker)."""
    if not question:
        return False
    q = question.strip().lower()
    # Exclusions : Docker / conteneurs / disques
    if any(
        x in q
        for x in (
            "docker image", "image docker", "dockerfile", "docker-compose",
            "pull image", "build image", "image système", "image systeme",
            "ami aws", "iso ", "vm image",
        )
    ):
        return False
    triggers = (
        "génère une image", "genere une image", "génère-moi une image", "genere-moi une image",
        "crée une image", "cree une image", "créer une image", "creer une image",
        "fais une image", "fait une image", "faire une image",
        "dessine", "dessine-moi", "illustre", "illustration de",
        "génère une illustration", "genere une illustration",
        "crée une illustration", "cree une illustration",
        "generate an image", "generate a picture", "draw me", "create an image",
        "montre-moi une image", "montre moi une image",
        "image qui représente", "image qui represente",
        "génère un schéma visuel", "genere un schema visuel",
        "visuel de", "picture of",
    )
    return any(t in q for t in triggers)


def est_salutation(question: str) -> bool:
    """Vrai pour un message de politesse / salutation sans besoin de corpus."""
    if not question:
        return False
    q = question.strip().lower()
    # Retirer ponctuation courante
    q_clean = re.sub(r"[!?.…,;:]+", " ", q).strip()
    q_clean = re.sub(r"\s+", " ", q_clean)

    if len(q_clean) > 80:
        return False

    # Message = uniquement un (ou deux) mots de salutation / politesse
    mots = q_clean.split()
    if not mots:
        return False
    if len(mots) <= 3 and all(m in _MOTS_SALUTATION | _MOTS_POLITESSE for m in mots):
        return True

    # Formules courtes du type "salut ça va", "bonjour assistDoc"
    if mots[0] in _MOTS_SALUTATION and len(mots) <= 5:
        suite = " ".join(mots[1:])
        if not any(k in suite for k in ("comment", "créer", "faire", "api", "code", "erreur", "bug")):
            # Si aucun mot technique / question métier évidente
            if not est_demande_technique(q_clean) and not necessite_recherche_web(q_clean):
                return True

    return False


MOTS_ROADMAP = {
    "roadmap", "road map", "feuille de route", "parcours", "plan de carrière",
    "devenir développeur", "devenir developpeur", "compétences pour",
    "competences pour", "apprendre python", "apprendre java", "apprendre react",
    "par où commencer", "par ou commencer", "plan d'apprentissage",
    "plan d apprentissage", "curriculum", "progression",
}


def est_demande_roadmap(question: str) -> bool:
    """Vrai pour une demande de parcours / roadmap (pas un projet à coder tout de suite)."""
    q = question.lower()
    if any(m in q for m in MOTS_ROADMAP):
        return True
    if "apprendre" in q and any(t in q for t in ("python", "java", "react", "devops", "backend", "frontend")):
        return True
    return False


def identifier_intention(question: str, mode_force: Optional[str] = None) -> str:
    """
    Pipeline d'intention :
    salutation | cdc | projet | roadmap | code | maths | explication | conversation
    """
    if mode_force == "texte":
        return "conversation"
    if mode_force == "technique":
        return "code"
    if mode_force == "projet":
        return "projet"
    if mode_force == "cdc":
        return "cdc"
    if mode_force == "roadmap":
        return "roadmap"

    if est_salutation(question):
        return "salutation"
    if est_cahier_des_charges(question):
        return "cdc"
    if est_demande_projet(question):
        return "projet"
    if est_demande_roadmap(question):
        return "roadmap"
    if est_demande_technique(question):
        return "code"
    if est_demande_maths(question):
        return "maths"
    if necessite_recherche_web(question):
        return "explication"
    return "conversation"


# Mots indiquant une demande de PROJET COMPLET (multi-étapes)
MOTS_PROJET = {
    'aide-moi à créer', 'aide moi à créer', 'aide-moi à faire', 'aide moi à faire',
    'aide-moi à construire', 'aide moi à construire', 'aide-moi à développer',
    'guide-moi', 'guide moi', 'étape par étape', 'etape par etape',
    'pas à pas', 'comment créer un projet', 'comment construire',
    'je veux faire', 'je veux créer', 'je veux développer', 'je veux construire',
    'voila ce que je veux faire', 'voilà ce que je veux faire',
    'aide-moi étape', 'crée un projet', 'créer une application complète',
    'application complète', 'système complet', 'plateforme complète',
}

# Indices d'un CAHIER DES CHARGES / spécification longue
MOTS_CDC = {
    'cahier de charge', 'cahier des charges', 'cahier de charges',
    'spécification', 'specification', 'requirements', 'cdc',
    'version 1.0', 'modules erp', 'types d\'utilisateurs',
    'architecture technique recommandée', 'workflow principal',
    'présentation', 'fonctionnalités', 'périmètre',
}


def _normaliser_texte(texte: str) -> str:
    """Minuscules + suppression des accents courants pour matching robuste."""
    t = texte.lower()
    for a, b in (
        ("à", "a"), ("â", "a"), ("ä", "a"),
        ("é", "e"), ("è", "e"), ("ê", "e"), ("ë", "e"),
        ("î", "i"), ("ï", "i"),
        ("ô", "o"), ("ö", "o"),
        ("ù", "u"), ("û", "u"), ("ü", "u"),
        ("ç", "c"),
    ):
        t = t.replace(a, b)
    return t


def est_demande_projet(question: str) -> bool:
    """Détecte une demande de projet complet nécessitant un guidage multi-étapes."""
    q = _normaliser_texte(question)
    if any(_normaliser_texte(mot) in q for mot in MOTS_PROJET):
        return True
    # Formulations libres : "projet … de A à Z", "accompagner mon projet"
    if "projet" in q and any(x in q for x in ("a a z", "a à z", "de a a z", "accompagner", "guider", "construire", "developper", "creer")):
        return True
    return est_cahier_des_charges(question)


def est_cahier_des_charges(texte: str) -> bool:
    """Détecte un cahier des charges / spécification longue (pas une simple question)."""
    if not texte or len(texte.strip()) < 800:
        return False
    t = texte.lower()
    score = 0
    if any(m in t for m in MOTS_CDC):
        score += 2
    if t.count("module") >= 3:
        score += 2
    if any(m in t for m in ("super admin", "rbac", "dashboard", "erp", "workflow")):
        score += 1
    if len(texte) > 3000:
        score += 1
    if t.count("\n") >= 15:
        score += 1
    return score >= 3


def compresser_cahier_des_charges(texte: str, max_chars: int = 3500) -> str:
    """
    Condensed un CDC long pour le LLM : garde présentation, acteurs, modules (titres),
    stack technique, workflow — sans recopier tout le détail.
    """
    lignes = [ln.rstrip() for ln in texte.strip().splitlines()]
    blocs_utiles = []
    buffer = []
    section_courante = "intro"

    def flush():
        nonlocal buffer
        if buffer:
            blocs_utiles.append((section_courante, "\n".join(buffer)))
            buffer = []

    for ln in lignes:
        low = ln.lower().strip()
        if re.match(r"^#{1,3}\s+", ln) or re.match(
            r"^(\d+\.|module\s+\d+|architecture|workflow|conclusion|types d)",
            low,
        ):
            flush()
            section_courante = low[:80]
        buffer.append(ln)
    flush()

    # Extraire titres de modules (lignes courtes contenant MODULE / Gestion)
    modules = []
    for ln in lignes:
        if re.search(r"module\s*\d+|^\s*gestion\s+", ln, re.I):
            modules.append(re.sub(r"\s+", " ", ln.strip())[:100])
    modules = modules[:40]

    # Chercher bloc architecture / stack
    archi = ""
    for nom, contenu in blocs_utiles:
        if any(k in nom for k in ("architecture", "technique", "stack", "backend", "frontend")):
            archi = contenu[:1200]
            break
    if not archi:
        for ln in lignes:
            if any(k in ln.lower() for k in ("laravel", "angular", "fastapi", "django", "postgresql", "docker")):
                archi += ln + "\n"
        archi = archi[:1200]

    # Intro = premières lignes non vides
    intro = "\n".join(ln for ln in lignes[:40] if ln.strip())[:900]

    resume = [
        "## Extrait condensé du cahier des charges (ne pas recopier tel quel)",
        "",
        "### Présentation / périmètre",
        intro,
        "",
        f"### Modules identifiés ({len(modules)})",
        "\n".join(f"- {m}" for m in modules) if modules else "- (voir texte source)",
        "",
        "### Architecture / stack mentionnée",
        archi or "(non détectée clairement — propose une stack réaliste)",
        "",
        "### Note",
        f"Document original ~{len(texte)} caractères. Analyse et priorise ; ne reformule pas tout.",
    ]
    out = "\n".join(resume)
    return out[:max_chars]


PROMPT_UTILISATEUR_CDC = """L'utilisateur a fourni un CAHIER DES CHARGES / spécification longue.
Tu es un architecte logiciel senior. Tu ne recopies PAS le document.

{cahier_condense}

{contexte}

Réponds UNIQUEMENT avec cette structure :

## 1. Synthèse (5-8 lignes max)
Objectif du système + enjeux principaux. Pas de liste exhaustive.

## 2. Analyse critique
- Ce qui est réaliste / trop ambitieux pour une V1
- Risques majeurs (multi-tenant, paiements, IA, mobile, etc.)
- Ce qu'il faut reporter

## 3. MVP recommandé (V1)
Liste 5 à 8 modules PRIORITAIRES seulement, avec une phrase de justification chacun.
Explicite : « Hors MVP pour plus tard : … »

## 4. Architecture technique
Confirme ou ajuste la stack du CDC (backend, frontend, DB, cache, auth, Docker).
Justifie brièvement. Propose une architecture en couches + multi-tenant si pertinent.

## 5. Modèle de données (cœur)
Liste les 8-15 entités clés et relations principales (pas tout le schéma).

## 6. Feuille de route (phases)
Phase 0 (setup) → Phase 1 (MVP) → Phase 2 → Phase 3. 4 à 7 étapes max au total.

## 7. Étape 1 — démarrage concret
Commandes + structure de dossiers + premiers fichiers (auth / multi-tenant / hello API).
Donne Windows ET Linux/Mac pour les commandes shell.
Code minimal mais réel (pas de pseudo-commandes inventées).

## 8. Et ensuite ?
Invite à écrire « étape suivante » ou le nom d'un module MVP à détailler.

INTERDITS :
- Recopier la liste des 30+ modules
- Reformuler tout le CDC
- Inventer des CLI inexistantes
- Réponse purement descriptive sans plan d'action
"""


# ════════════════════════════════════════════════════════════════
# WEB SEARCHER — déplacé vers src/web/ (réexport pour compat)
# ════════════════════════════════════════════════════════════════
# WebSearcher est importé depuis web (voir en-tête du module).


# ════════════════════════════════════════════════════════════════
# GÉNÉRATEUR ADAPTATIF
# ════════════════════════════════════════════════════════════════

class GenerateurReponse:

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client or LLMClient()
        self.api_key = self.llm.api_key
        self.modele = self.llm.modele
        self.temperature = self.llm.temperature
        self.top_p = self.llm.top_p
        self.presence_penalty = self.llm.presence_penalty
        self.frequency_penalty = self.llm.frequency_penalty
        self.max_tokens = self.llm.max_tokens
        self.client = self.llm.client  # compat tests / accès bas niveau
        self.searcher = WebSearcher()
        self.mode_ragas = MODE_RAGAS_EVAL
        self.modele_leger = self.llm.modele_leger

        if self.modele_leger:
            self.max_docs_contexte = int(os.getenv("MAX_DOCS_CONTEXTE", "3"))
            self.max_chars_doc = int(os.getenv("MAX_CHARS_DOC", "400"))
            self.max_historique = int(os.getenv("MAX_HISTORIQUE_LEGER", "6"))
        else:
            self.max_docs_contexte = int(os.getenv("MAX_DOCS_CONTEXTE", "5"))
            self.max_chars_doc = int(os.getenv("MAX_CHARS_DOC", "1000"))
            self.max_historique = int(os.getenv("MAX_HISTORIQUE", "8"))

        if self.mode_ragas:
            self.llm.appliquer_mode_ragas()
            self.max_tokens = self.llm.max_tokens
            self.temperature = self.llm.temperature
            self.max_docs_contexte = min(self.max_docs_contexte, 3)
            self.max_chars_doc = min(self.max_chars_doc, 500)

        statut_web = "désactivé" if self.searcher.desactive else f"activé (timeout {web_timeout()}s)"
        mode_info = " | MODE RAGAS EVAL" if self.mode_ragas else ""
        print(
            f"✅ Groq initialisé — {self.modele} | max_tokens={self.max_tokens} "
            f"| hist={self.max_historique} | docs≤{self.max_docs_contexte}×{self.max_chars_doc}c "
            f"| web search {statut_web}{mode_info}"
        )

    def _construire_contexte(self, documents: List[Dict], max_chars: Optional[int] = None) -> str:
        if not documents:
            return ""
        lim = max_chars if max_chars is not None else self.max_chars_doc
        blocs = []
        for i, doc in enumerate(documents[: self.max_docs_contexte], 1):
            score = doc.get("score_rerank", doc.get("score_dense", 0))
            # Guides projet : laisser plus de texte pour le code complet
            repo = (doc.get("nom_complet") or "").lower()
            lim_doc = max(lim, 1400) if "enrichissement/projet-" in repo else lim
            blocs.append(
                f"[Doc {i}] score={score:.3f} | {doc.get('nom_complet','N/A')} "
                f"| {doc.get('section_titre','N/A')} | {doc.get('langage','N/A')}\n"
                f"URL: {doc.get('url','')}\n"
                f"{doc.get('texte','')[:lim_doc]}"
            )
        return ("\n" + "─"*50 + "\n").join(blocs)

    def _filtrer_docs_pertinents(self, question: str, documents: List[Dict]) -> List[Dict]:
        """Garde les docs alignés avec la question ; priorise enrichissement/projet-*."""
        if not documents:
            return []
        q = question.lower()
        mots = {w for w in re.findall(r"[a-zA-ZÀ-ÿ0-9_+#.-]{3,}", q) if len(w) >= 3}
        boost = {
            "fastapi", "flask", "django", "react", "jwt", "python", "api",
            "pydantic", "tâche", "taches", "todo", "projet", "gestion",
        }
        mots |= {b for b in boost if b in q}
        bruit = ("the-art-of-command-line", "nodebestpractices", "awesome-")

        scores = []
        for doc in documents:
            repo = str(doc.get("nom_complet", "")).lower()
            if any(b in repo for b in bruit) and not any(
                k in q for k in ("linux", "bash", "shell", "node", "npm", "cli")
            ):
                continue
            texte = " ".join([
                repo,
                str(doc.get("section_titre", "")),
                str(doc.get("langage", "")),
                str(doc.get("texte", ""))[:800],
            ]).lower()
            hits = sum(1 for m in mots if m in texte)
            score_r = float(doc.get("score_rerank", doc.get("score_dense", 0)) or 0)
            bonus = 0.0
            if "enrichissement/projet-" in repo:
                bonus += 5.0
            elif "enrichissement/" in repo:
                bonus += 2.0
            scores.append((hits + score_r + bonus, doc))

        scores.sort(key=lambda x: x[0], reverse=True)
        filtrés = [d for h, d in scores if h >= 0.15]
        if not filtrés and scores:
            filtrés = [scores[0][1]]
        # Toujours mettre les guides projet en premier
        projets = [d for d in filtrés if "enrichissement/projet-" in (d.get("nom_complet") or "").lower()]
        autres = [d for d in filtrés if d not in projets]
        return (projets + autres)[: self.max_docs_contexte]

    def _tronquer_messages(self, messages: List[Dict], facteur: float = 0.6) -> List[Dict]:
        """Compat : délègue au client LLM unifié."""
        return tronquer_messages(messages, facteur=facteur)

    def _construire_citations(self, documents: List[Dict], ressources: List[Dict]) -> str:
        lignes = ["📚 **Sources GitHub :**"]
        for i, doc in enumerate(documents, 1):
            repo    = doc.get("nom_complet", "N/A")
            section = doc.get("section_titre", "N/A")
            url     = doc.get("url", "")
            lien    = f"[{repo}]({url})" if url else repo
            lignes.append(f"[{i}] {lien} — *{section}*")

        if ressources:
            lignes.append("\n🌐 **Ressources web :**")
            for r in ressources[:6]:
                if r.get("url") and r.get("titre"):
                    lignes.append(f"- [{r['titre'][:60]}]({r['url']})")

        return "\n".join(lignes)

    def _appeler_llm(self, messages: List[Dict], max_retries: int = 5) -> tuple:
        """Appel Groq via LLMClient (retries 429/413 inclus)."""
        # Garder max_tokens synchronisé si le client l'a réduit
        texte, tokens = self.llm.invoke(messages, max_retries=max_retries)
        self.max_tokens = self.llm.max_tokens
        return texte, tokens

    def _appeler_llm_stream(self, messages: List[Dict], usage_holder: Optional[Dict] = None):
        """Streaming via LLMClient unifié."""
        for delta in self.llm.stream(messages, usage_holder=usage_holder):
            yield delta
        self.max_tokens = self.llm.max_tokens
    def generer(
        self,
        question  : str,
        documents : List[Dict],
        historique: Optional[List[Dict]] = None,
        mode_force: Optional[str] = None,
        stream: bool = False,
    ) -> Dict:
        """
        Pipeline : intention → type de réponse → docs filtrés → plan (via prompt) → rédaction.

        mode_force : None | "texte" | "technique" | "projet" | "cdc" | "roadmap"
        """
        print("   🧠 Identification de l'intention…")
        intention = identifier_intention(question, mode_force)
        print(f"   🎯 Intention : {intention}")

        cdc        = intention == "cdc"
        projet     = intention in ("projet", "cdc")
        roadmap    = intention == "roadmap"
        technique  = intention == "code"
        maths      = intention == "maths"
        besoin_web = intention == "explication"
        conversation = intention in ("conversation", "salutation")

        ressources = []
        citations  = ""

        if self.mode_ragas:
            print(f"   📊 Mode RAGAS EVAL (réponse ancrée, courte)")
            contexte = self._construire_contexte(documents) if documents else "Aucun document."
            prompt = PROMPT_UTILISATEUR_RAGAS.format(
                contexte=contexte,
                question=question,
            )
            messages = [{"role": "system", "content": PROMPT_SYSTEME_RAGAS}]
            if historique:
                messages.extend(historique[-self.max_historique:])
            messages.append({"role": "user", "content": prompt})

            print(f"   🤖 Génération ({self.modele})...")
            reponse_brute, tokens_utilises = self._appeler_llm(messages)
            if tokens_utilises:
                print(f"   ✅ {tokens_utilises} tokens")

            return {
                "reponse"        : reponse_brute.strip(),
                "reponse_seule"  : reponse_brute.strip(),
                "citations"      : "",
                "documents"      : documents or [],
                "ressources_web" : [],
                "tokens_utilises": tokens_utilises,
                "mode"           : "ragas_eval",
            }

        # Filtrer les documents hors sujet avant construction du prompt
        print("   📚 Filtrage des documents pertinents…")
        docs_utiles = self._filtrer_docs_pertinents(question, documents or []) if (projet or roadmap or technique) else (documents or [])

        if projet:
            contexte = self._construire_contexte(docs_utiles) if docs_utiles else ""

            if cdc:
                print("   📋 Plan de réponse : cahier des charges → MVP + étape 1")
                if self.modele_leger:
                    self.max_tokens = max(self.max_tokens, int(os.getenv("MAX_TOKENS_CDC", "2500")))
                cahier = compresser_cahier_des_charges(question)
                prompt = PROMPT_UTILISATEUR_CDC.format(
                    cahier_condense=cahier,
                    contexte=(
                        f"Documents corpus (optionnel) :\n{contexte}"
                        if contexte else "Aucun document corpus."
                    ),
                )
            else:
                print("   🏗️  Plan de réponse : format PROJET mentor")
                prompt = PROMPT_UTILISATEUR_PROJET.format(
                    question=question,
                    contexte=(
                        f"Documents du corpus (ignore hors sujet) :\n{contexte}"
                        if contexte else ""
                    ),
                )
            documents = docs_utiles

        elif roadmap:
            print("   🗺️  Plan de réponse : format ROADMAP")
            if not self.searcher.desactive:
                print("   🌐 Recherche web…")
            ressources = self.searcher.rechercher_multi(question)
            ressources_str = self.searcher.formater(ressources)
            contexte = self._construire_contexte(docs_utiles[:4]) if docs_utiles else "Aucun document."
            prompt = PROMPT_UTILISATEUR_ROADMAP.format(
                contexte=contexte,
                ressources_web=ressources_str,
                question=question,
            )
            documents = docs_utiles
            citations = self._construire_citations(documents, ressources)

        elif technique:
            print("   🔧 Plan de réponse : format CODE")
            if not self.searcher.desactive:
                print("   🌐 Recherche web…")
            ressources = self.searcher.rechercher_multi(question)
            ressources_str = self.searcher.formater(ressources)
            contexte = self._construire_contexte(docs_utiles) if docs_utiles else "Aucun document pertinent."
            prompt = PROMPT_UTILISATEUR_TECHNIQUE.format(
                contexte=contexte,
                ressources_web=ressources_str,
                question=question,
            )
            documents = docs_utiles
            citations = self._construire_citations(documents, ressources)

        elif besoin_web:
            print("   📘 Plan de réponse : format EXPLICATION")
            if not self.searcher.desactive:
                print("   🌐 Recherche web…")
            ressources = self.searcher.rechercher_multi(question)
            ressources_str = self.searcher.formater(ressources)
            contexte = ""
            if documents and documents[0].get("score_rerank", 0) > 0.3:
                contexte = "Documents utiles :\n" + self._construire_contexte(documents[:2])
            prompt = (
                f"Question : {question}\n\n"
                f"Format EXPLICATION : clair, structuré, pédagogique. "
                f"Explique le pourquoi, donne un exemple concret, bonnes pratiques, "
                f"erreurs fréquentes et prochaines étapes. Pas de code sauf si vraiment utile.\n\n"
                f"Ressources web :\n{ressources_str}\n\n{contexte}\n\n"
                f"Auto-vérifie : réponse exacte, exploitable, centrée sur la demande."
            )
            if ressources:
                citations = "🌐 **Pour aller plus loin :**\n" + "\n".join(
                    f"- [{r['titre'][:70]}]({r['url']})"
                    for r in ressources[:6] if r.get("url") and r.get("titre")
                )

        elif maths:
            print("   ➗ Plan de réponse : format MATHS")
            prompt = PROMPT_UTILISATEUR_MATHS.format(question=question)
            documents = []

        else:
            print("   💬 Plan de réponse : conversation" + (" (salutation)" if intention == "salutation" else ""))
            contexte = ""
            if documents and not conversation:
                top_score = documents[0].get("score_rerank", 0)
                if top_score > 0.3:
                    contexte = "Documents utiles :\n" + self._construire_contexte(documents[:2])
            prompt = PROMPT_UTILISATEUR_SIMPLE.format(question=question, contexte=contexte)

        # Système mentor (version courte si modèle léger / CDC)
        if cdc:
            system_prompt = (
                "Tu es AssistDoc — architecte senior + mentor. "
                "CDC : ANALYSE, PRIORISE, MVP, architecture, ÉTAPE 1 concrète. "
                "INTERDIT de recopier le CDC. Actionnable et réaliste."
            )
        elif self.modele_leger:
            system_prompt = PROMPT_SYSTEME_LEGER
        else:
            system_prompt = PROMPT_SYSTEME

        messages = [{"role": "system", "content": system_prompt}]
        if historique and not cdc:
            messages.extend(historique[-self.max_historique:])
        # Rappel qualité intégré au message utilisateur
        messages.append({
            "role": "user",
            "content": prompt + (
                "\n\n[Vérification finale attendue : exactitude, détail utile, choix justifiés, "
                "prochaines étapes, focus sur la demande — sans afficher cette checklist.]"
                if not conversation else ""
            ),
        })

        print(f"   ✍️  Rédaction ({self.modele})…")

        mode_final = {
            "cdc": "cahier_des_charges",
            "projet": "projet",
            "roadmap": "roadmap",
            "code": "technique",
            "maths": "maths",
            "explication": "explication",
            "salutation": "conversation",
            "conversation": "conversation",
        }.get(intention, "conversation")

        docs_retour = documents if (technique or projet or roadmap) else []

        if stream:
            usage_holder: Dict = {"tokens_utilises": 0}

            def _flux():
                for delta in self._appeler_llm_stream(messages, usage_holder):
                    yield delta

            return {
                "reponse": "",
                "reponse_seule": "",
                "citations": citations,
                "documents": docs_retour,
                "ressources_web": ressources,
                "tokens_utilises": 0,
                "usage_holder": usage_holder,
                "mode": mode_final,
                "intention": intention,
                "stream": _flux(),
                "messages_llm": messages,
            }

        reponse_brute, tokens_utilises = self._appeler_llm(messages)
        if tokens_utilises:
            print(f"   ✅ {tokens_utilises} tokens — contrôle qualité implicite appliqué")

        if citations and "🌐" not in reponse_brute and "📚" not in reponse_brute:
            reponse_complete = reponse_brute.strip() + "\n\n---\n\n" + citations
        else:
            reponse_complete = reponse_brute.strip()

        return {
            "reponse"        : reponse_complete,
            "reponse_seule"  : reponse_brute.strip(),
            "citations"      : citations,
            "documents"      : docs_retour,
            "ressources_web" : ressources,
            "tokens_utilises": tokens_utilises,
            "mode"           : mode_final,
            "intention"      : intention,
        }

    def afficher_reponse(self, r: Dict) -> None:
        print("\n" + "═"*70)
        print(f"[Mode: {r['mode']}]")
        print(r["reponse"])
        print("═"*70)
        print(f"Tokens: {r['tokens_utilises']} | Docs: {len(r['documents'])} | Web: {len(r.get('ressources_web',[]))}")


# ════════════════════════════════════════════════════════════════
# TEST
# ════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from retrieval.retrieval_hybride import RetrievalHybride

    moteur     = RetrievalHybride()
    generateur = GenerateurReponse()

    questions = [
        "Salut, comment ça va ?",
        "Que penses-tu du télétravail pour les développeurs ?",
        "Comment créer une API REST avec Flask ?",
        "Écris-moi un petit poème sur le code.",
        "Aide-moi à rédiger un email pour demander un délai sur mon mémoire",
    ]

    for q in questions:
        print(f"\n{'═'*70}\n❓ {q}\n{'═'*70}")
        docs = moteur.rechercher(q, top_k_retrieval=20, top_k_final=5)
        res  = generateur.generer(q, docs)
        generateur.afficher_reponse(res)
        time.sleep(2)