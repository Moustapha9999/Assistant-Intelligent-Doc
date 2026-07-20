"""Mémoire temporaire de projet (contexte structuré dans la conversation)."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


_STACK_PATTERNS = (
    ("python", r"\bpython\b"),
    ("fastapi", r"\bfastapi\b"),
    ("flask", r"\bflask\b"),
    ("django", r"\bdjango\b"),
    ("react", r"\breact\b"),
    ("nextjs", r"\bnext\.?js\b"),
    ("postgresql", r"\b(postgres|postgresql)\b"),
    ("mysql", r"\bmysql\b"),
    ("sqlite", r"\bsqlite\b"),
    ("docker", r"\bdocker\b"),
    ("redis", r"\bredis\b"),
    ("jwt", r"\bjwt\b"),
)


@dataclass
class ContexteProjet:
    nom: str = ""
    objectif: str = ""
    stack: List[str] = field(default_factory=list)
    modules: List[str] = field(default_factory=list)
    etape_courante: str = "1"
    decisions: List[str] = field(default_factory=list)
    actif: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "ContexteProjet":
        if not data:
            return cls()
        return cls(
            nom=str(data.get("nom") or ""),
            objectif=str(data.get("objectif") or ""),
            stack=list(data.get("stack") or []),
            modules=list(data.get("modules") or []),
            etape_courante=str(data.get("etape_courante") or "1"),
            decisions=list(data.get("decisions") or []),
            actif=bool(data.get("actif")),
        )


class MemoireProjet:
    def extraire_ou_mettre_a_jour(
        self,
        historique: List[Dict],
        question: str,
        mode: str = "",
        existant: Optional[Dict[str, Any]] = None,
    ) -> ContexteProjet:
        ctx = ContexteProjet.from_dict(existant)
        textes = []
        for m in (historique or [])[-12:]:
            if m.get("role") in {"user", "assistant"}:
                textes.append(m.get("content") or "")
        textes.append(question or "")
        blob = "\n".join(textes)
        blob_low = blob.lower()
        q_low = (question or "").lower()

        # Activation projet
        if mode == "projet" or any(
            x in q_low
            for x in ("je crée", "je cree", "aide-moi à créer", "aide moi a creer", "je veux créer", "je veux creer", "construire un", "développer un", "developper un")
        ):
            ctx.actif = True

        if not ctx.actif and not existant:
            # Peut réactiver si l'historique parle déjà d'un projet
            if any(x in blob_low for x in ("roadmap", "étape 1", "etape 1", "architecture proposée", "feuille de route")):
                ctx.actif = True

        if not ctx.actif:
            return ctx

        # Nom / objectif
        if not ctx.nom:
            m = re.search(
                r"(?:créer|creer|construire|développer|developper)\s+(?:un|une|le|la|mon|ma)?\s*([a-zA-ZÀ-ÿ0-9 _-]{3,40})",
                q_low,
            )
            if m:
                ctx.nom = m.group(1).strip().title()
            elif "erp" in q_low:
                ctx.nom = "ERP"
            elif "api" in q_low:
                ctx.nom = "API"

        if not ctx.objectif and question:
            ctx.objectif = (question or "").strip()[:180]

        # Stack
        for nom, pat in _STACK_PATTERNS:
            if re.search(pat, blob_low) and nom not in ctx.stack:
                ctx.stack.append(nom)

        # Modules typiques mentionnés
        for mod in (
            "auth", "authentification", "produits", "stock", "factures",
            "comptabilité", "comptabilite", "api", "frontend", "backend",
            "base de données", "base de donnees", "paiement", "utilisateurs",
        ):
            if mod in blob_low and mod not in ctx.modules:
                ctx.modules.append(mod)

        # Étape courante
        m_etape = re.search(r"étape\s*(\d+)|etape\s*(\d+)", q_low)
        if m_etape:
            ctx.etape_courante = m_etape.group(1) or m_etape.group(2)
        elif any(x in q_low for x in ("ensuite", "étape suivante", "etape suivante", "passe à", "passe a")):
            try:
                ctx.etape_courante = str(int(ctx.etape_courante) + 1)
            except ValueError:
                ctx.etape_courante = "2"

        # Décisions techniques simples
        for motif in (
            r"on (?:utilise|part sur|choisit)\s+([a-zA-Z0-9.+#-]+)",
            r"je (?:préfère|prefere)\s+([a-zA-Z0-9.+#-]+)",
        ):
            for m in re.finditer(motif, q_low):
                dec = m.group(0).strip()
                if dec and dec not in ctx.decisions:
                    ctx.decisions.append(dec[:80])
        ctx.decisions = ctx.decisions[-8:]
        return ctx

    def formater_pour_prompt(self, ctx: ContexteProjet) -> str:
        if not ctx or not ctx.actif:
            return ""
        lignes = ["Mémoire temporaire du projet en cours :"]
        if ctx.nom:
            lignes.append(f"- projet: {ctx.nom}")
        if ctx.objectif:
            lignes.append(f"- objectif: {ctx.objectif}")
        if ctx.stack:
            lignes.append(f"- stack: {', '.join(ctx.stack)}")
        if ctx.modules:
            lignes.append(f"- modules: {', '.join(ctx.modules[:12])}")
        lignes.append(f"- étape courante: {ctx.etape_courante}")
        if ctx.decisions:
            lignes.append("- décisions:")
            for d in ctx.decisions[-5:]:
                lignes.append(f"  - {d}")
        lignes.append(
            "- Réutilise ce contexte sans redemander les infos déjà connues."
        )
        return "\n".join(lignes)
