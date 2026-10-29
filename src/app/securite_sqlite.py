"""Données de la section Admin → Sécurité : incidents, indicateurs, sessions, sauvegardes.

Partage la base des comptes (`utilisateurs.db`) et réutilise son journal d'audit : aucun
second système de journalisation. Les deux tables ajoutées (`incidents`,
`incident_historique`) sont nécessaires au suivi des incidents et à l'historique des statuts.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import config
from app.sqlite_outils import ecriture, lecture
from app.utilisateurs_sqlite import UtilisateursSQLite
from securite import politique
from securite.evenements import CATEGORIE_SECURITE, GRAVITES, TYPES_ECHEC_AUTH, gravite_valide

STATUTS_INCIDENT = {
    "ouvert": "Ouvert",
    "en_analyse": "En analyse",
    "resolu": "Résolu",
    "faux_positif": "Faux positif",
}
STATUTS_OUVERTS = ("ouvert", "en_analyse")
SAUVEGARDES_CONSERVEES = 5


def _maintenant() -> datetime:
    return datetime.now(timezone.utc)


def depuis_heures(heures: float) -> str:
    return (_maintenant() - timedelta(hours=heures)).isoformat()


class SecuriteSQLite:
    def __init__(self, users: UtilisateursSQLite, dossier_bases: Optional[Path] = None):
        self.users = users
        self.chemin = users.chemin
        self.dossier_bases = Path(dossier_bases or config.DB_DIR)
        self._init_db()

    def _init_db(self) -> None:
        with ecriture(self.chemin) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS incidents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cree_le TEXT NOT NULL,
                    maj_le TEXT NOT NULL,
                    type TEXT NOT NULL,
                    gravite TEXT NOT NULL,
                    titre TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    statut TEXT NOT NULL DEFAULT 'ouvert',
                    cree_par TEXT,
                    evenement_id INTEGER
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS incident_historique (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    incident_id INTEGER NOT NULL REFERENCES incidents(id),
                    cree_le TEXT NOT NULL,
                    auteur TEXT,
                    ancien_statut TEXT,
                    nouveau_statut TEXT NOT NULL,
                    commentaire TEXT NOT NULL DEFAULT ''
                )"""
            )

    # ── Incidents ────────────────────────────────────────────────────────────

    def _exiger_admin(self, acteur: str, operation: str) -> None:
        if not self.users.est_admin_actif(acteur):
            self.users.evenement_securite(
                "acces_refuse", "elevee", f"Opération « {operation} » refusée (incidents)", acteur=acteur
            )
            raise PermissionError("Administrateur actif requis")

    def creer_incident(
        self,
        acteur: str,
        type_: str,
        gravite: str,
        titre: str,
        description: str = "",
        evenement_id: Optional[int] = None,
    ) -> int:
        self._exiger_admin(acteur, "ouvrir un incident")
        titre = (titre or "").strip()[:200]
        if not titre:
            raise ValueError("Titre requis")
        gravite = gravite_valide(gravite)
        now = _maintenant().isoformat()
        with ecriture(self.chemin) as conn:
            cur = conn.execute(
                "INSERT INTO incidents (cree_le, maj_le, type, gravite, titre, description, statut, "
                "cree_par, evenement_id) VALUES (?, ?, ?, ?, ?, ?, 'ouvert', ?, ?)",
                (now, now, (type_ or "autre")[:60], gravite, titre, (description or "")[:4000],
                 acteur, evenement_id),
            )
            incident_id = int(cur.lastrowid)
            conn.execute(
                "INSERT INTO incident_historique (incident_id, cree_le, auteur, ancien_statut, "
                "nouveau_statut, commentaire) VALUES (?, ?, ?, NULL, 'ouvert', ?)",
                (incident_id, now, acteur, "Ouverture"),
            )
        self.users.audit(acteur, "incident_cree", f"Incident #{incident_id} ({gravite}) : {titre}",
                         categorie=CATEGORIE_SECURITE, gravite=gravite)
        return incident_id

    def changer_statut(self, acteur: str, incident_id: int, nouveau: str, commentaire: str) -> bool:
        """Changement tracé ; un commentaire décrivant les actions réalisées est obligatoire."""
        self._exiger_admin(acteur, "modifier un incident")
        if nouveau not in STATUTS_INCIDENT:
            raise ValueError("Statut inconnu")
        commentaire = (commentaire or "").strip()[:2000]
        if not commentaire:
            raise ValueError("Décrivez les actions réalisées")
        now = _maintenant().isoformat()
        with ecriture(self.chemin) as conn:
            row = conn.execute("SELECT statut FROM incidents WHERE id = ?", (incident_id,)).fetchone()
            if row is None:
                return False
            ancien = row["statut"]
            conn.execute(
                "UPDATE incidents SET statut = ?, maj_le = ? WHERE id = ?", (nouveau, now, incident_id)
            )
            conn.execute(
                "INSERT INTO incident_historique (incident_id, cree_le, auteur, ancien_statut, "
                "nouveau_statut, commentaire) VALUES (?, ?, ?, ?, ?, ?)",
                (incident_id, now, acteur, ancien, nouveau, commentaire),
            )
        self.users.audit(acteur, "incident_statut", f"Incident #{incident_id} : {ancien} → {nouveau}",
                         categorie=CATEGORIE_SECURITE, gravite="info")
        return True

    def lister_incidents(self, statuts: Optional[List[str]] = None, limite: int = 200) -> List[Dict[str, Any]]:
        statuts = [s for s in (statuts or []) if s in STATUTS_INCIDENT]
        where = f"WHERE statut IN ({', '.join('?' for _ in statuts)})" if statuts else ""
        with lecture(self.chemin) as conn:
            rows = conn.execute(
                f"SELECT * FROM incidents {where} ORDER BY id DESC LIMIT ?", (*statuts, limite)
            ).fetchall()
        return [dict(r) for r in rows]

    def historique_incident(self, incident_id: int) -> List[Dict[str, Any]]:
        with lecture(self.chemin) as conn:
            rows = conn.execute(
                "SELECT * FROM incident_historique WHERE incident_id = ? ORDER BY id", (incident_id,)
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Indicateurs ──────────────────────────────────────────────────────────

    def _compter_evenements(self, conn: sqlite3.Connection, depuis: str, actions: tuple) -> int:
        return int(conn.execute(
            f"SELECT COUNT(*) AS n FROM admin_audit WHERE categorie = ? AND cree_le >= ? "
            f"AND action IN ({', '.join('?' for _ in actions)})",
            (CATEGORIE_SECURITE, depuis, *actions),
        ).fetchone()["n"])

    def resume(self, depuis: str) -> Dict[str, Any]:
        """Indicateurs calculés à partir des tables réelles (aucune valeur estimée)."""
        now = _maintenant().isoformat()
        with lecture(self.chemin) as conn:
            par_gravite = {g: 0 for g in GRAVITES}
            for r in conn.execute(
                "SELECT gravite, COUNT(*) AS n FROM admin_audit WHERE categorie = ? AND cree_le >= ? "
                "GROUP BY gravite",
                (CATEGORIE_SECURITE, depuis),
            ):
                par_gravite[gravite_valide(r["gravite"])] += int(r["n"])
            admins = conn.execute(
                "SELECT COUNT(*) AS n, SUM(CASE WHEN totp_actif = 1 THEN 0 ELSE 1 END) AS sans_mfa "
                "FROM users WHERE tier = 'admin' AND suspended = 0"
            ).fetchone()
            sessions = {
                r["compte"]: int(r["n"])
                for r in conn.execute(
                    "SELECT CASE WHEN u.tier = 'guest' THEN 'invites' ELSE 'comptes' END AS compte, "
                    "COUNT(*) AS n FROM sessions s JOIN users u ON u.id = s.user_id "
                    "WHERE s.revoque_le IS NULL AND s.expire_le > ? GROUP BY compte",
                    (now,),
                )
            }
            incidents_ouverts = int(conn.execute(
                "SELECT COUNT(*) AS n FROM incidents WHERE statut IN ('ouvert', 'en_analyse')"
            ).fetchone()["n"])
            return {
                "echecs_auth": self._compter_evenements(conn, depuis, TYPES_ECHEC_AUTH),
                "blocages": self._compter_evenements(conn, depuis, ("auth_verrouillage",)),
                "refus_acces": self._compter_evenements(conn, depuis, ("acces_refuse", "api_acces_refuse")),
                "fichiers_refuses": self._compter_evenements(conn, depuis, ("fichier_refuse",)),
                "injections": self._compter_evenements(conn, depuis, ("ia_injection_suspecte",)),
                "erreurs_ia": self._compter_evenements(conn, depuis, ("ia_erreur",)),
                "quotas": self._compter_evenements(conn, depuis, ("quota_depasse", "quota_global_invites")),
                "par_gravite": par_gravite,
                "admins": int(admins["n"] or 0),
                "admins_sans_mfa": int(admins["sans_mfa"] or 0),
                "sessions_comptes": sessions.get("comptes", 0),
                "sessions_invites": sessions.get("invites", 0),
                "incidents_ouverts": incidents_ouverts,
            }

    def alertes(self, depuis: str) -> List[Dict[str, Any]]:
        """Règles de détection simples ; chaque alerte est un signal à qualifier, pas une attaque."""
        alertes: List[Dict[str, Any]] = []
        maximum = politique.valeur("SECU_MAX_ECHECS")
        seuil_volume = politique.valeur("SECU_SEUIL_REQ_HEURE")
        with lecture(self.chemin) as conn:
            for r in conn.execute(
                "SELECT cle, COUNT(*) AS n, MAX(cree_le) AS dernier FROM auth_tentatives "
                "WHERE succes = 0 AND cree_le >= ? GROUP BY cle HAVING n >= ? ORDER BY n DESC LIMIT 20",
                (depuis, maximum),
            ):
                nature = {"email": "adresse e-mail", "ip": "adresse IP", "mfa": "second facteur"}.get(
                    r["cle"].split(":", 1)[0], "clé")
                alertes.append({
                    "type": "echecs_repetes",
                    "gravite": "elevee" if r["n"] >= maximum * 3 else "moyenne",
                    "titre": f"{r['n']} échecs de connexion pour une même {nature}",
                    "detail": f"Empreinte {r['cle'][:14]}… · dernier échec {r['dernier'][:16]}",
                })
            for r in conn.execute(
                "SELECT e.user_id, u.tier, u.email, u.display_name, COUNT(*) AS n FROM usage_events e "
                "LEFT JOIN users u ON u.id = e.user_id WHERE e.kind = 'ask' AND e.cree_le >= ? "
                "GROUP BY e.user_id HAVING n >= ? ORDER BY n DESC LIMIT 20",
                (depuis_heures(1), seuil_volume),
            ):
                alertes.append({
                    "type": "volume_anormal",
                    "gravite": "moyenne",
                    "titre": f"{r['n']} requêtes en une heure pour un même compte",
                    "detail": f"{r['email'] or r['display_name'] or r['user_id'][:8]} ({r['tier']})",
                })
            for action, gravite, titre in (
                ("acces_refuse", "elevee", "Accès administrateur refusé"),
                ("api_acces_refuse", "moyenne", "Accès API refusé"),
                ("ia_injection_suspecte", "moyenne", "Manipulation d'instructions suspectée"),
                ("fichier_refuse", "faible", "Fichiers refusés"),
                ("quota_global_invites", "moyenne", "Plafond global des invités atteint"),
            ):
                n = self._compter_evenements(conn, depuis, (action,))
                if n:
                    alertes.append({"type": action, "gravite": gravite, "titre": f"{titre} : {n}",
                                    "detail": "Voir les événements correspondants ci-dessous."})
        ordre = {g: i for i, g in enumerate(reversed(GRAVITES))}
        return sorted(alertes, key=lambda a: ordre.get(a["gravite"], 99))

    def comptes_privilegies(self) -> List[Dict[str, Any]]:
        with lecture(self.chemin) as conn:
            rows = conn.execute(
                "SELECT id, email, display_name, github_login, suspended, totp_actif, derniere_connexion, "
                "cree_le FROM users WHERE tier = 'admin' ORDER BY derniere_connexion DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def sessions_actives(self, limite: int = 100) -> List[Dict[str, Any]]:
        """Sessions de comptes (hors invités) regroupées par compte ; aucun jeton n'est exposé."""
        now = _maintenant().isoformat()
        with lecture(self.chemin) as conn:
            rows = conn.execute(
                "SELECT u.id, u.email, u.display_name, u.github_login, u.tier, COUNT(*) AS n, "
                "MAX(s.cree_le) AS derniere FROM sessions s JOIN users u ON u.id = s.user_id "
                "WHERE s.revoque_le IS NULL AND s.expire_le > ? AND u.tier != 'guest' "
                "GROUP BY u.id ORDER BY derniere DESC LIMIT ?",
                (now, limite),
            ).fetchall()
        return [dict(r) for r in rows]

    def volumes_ia(self, depuis: str, limite: int = 10) -> Dict[str, Any]:
        with lecture(self.chemin) as conn:
            total = int(conn.execute(
                "SELECT COUNT(*) AS n FROM usage_events WHERE kind = 'ask' AND cree_le >= ?", (depuis,)
            ).fetchone()["n"])
            par_tier = {
                r["tier"] or "inconnu": int(r["n"])
                for r in conn.execute(
                    "SELECT u.tier, COUNT(*) AS n FROM usage_events e LEFT JOIN users u ON u.id = e.user_id "
                    "WHERE e.kind = 'ask' AND e.cree_le >= ? GROUP BY u.tier",
                    (depuis,),
                )
            }
            top = [
                dict(r) for r in conn.execute(
                    "SELECT e.user_id, u.email, u.display_name, u.tier, COUNT(*) AS n FROM usage_events e "
                    "LEFT JOIN users u ON u.id = e.user_id WHERE e.kind = 'ask' AND e.cree_le >= ? "
                    "GROUP BY e.user_id ORDER BY n DESC LIMIT ?",
                    (depuis, limite),
                )
            ]
        return {"total": total, "par_tier": par_tier, "top": top}

    # ── Sauvegardes ──────────────────────────────────────────────────────────

    @property
    def dossier_sauvegardes(self) -> Path:
        return self.dossier_bases / "sauvegardes"

    def lister_sauvegardes(self) -> List[Dict[str, Any]]:
        if not self.dossier_sauvegardes.exists():
            return []
        out = []
        for d in sorted(self.dossier_sauvegardes.iterdir(), reverse=True):
            if d.is_dir():
                fichiers = list(d.glob("*.db"))
                out.append({
                    "nom": d.name,
                    "fichiers": len(fichiers),
                    "taille": sum(f.stat().st_size for f in fichiers),
                    "date": datetime.fromtimestamp(d.stat().st_mtime, timezone.utc).isoformat(),
                })
        return out

    def creer_sauvegarde(self, acteur: str) -> Path:
        """Copie cohérente (API backup SQLite) de toutes les bases applicatives."""
        self._exiger_admin(acteur, "créer une sauvegarde")
        cible = self.dossier_sauvegardes / _maintenant().strftime("%Y%m%dT%H%M%SZ")
        cible.mkdir(parents=True, exist_ok=True)
        noms = []
        for base in sorted(self.dossier_bases.glob("*.db")):
            src = sqlite3.connect(str(base))
            dst = sqlite3.connect(str(cible / base.name))
            try:
                src.backup(dst)
            finally:
                dst.close()
                src.close()
            noms.append(base.name)
        anciennes = [d for d in sorted(self.dossier_sauvegardes.iterdir()) if d.is_dir()]
        for d in anciennes[:-SAUVEGARDES_CONSERVEES]:
            for f in d.iterdir():
                f.unlink()
            d.rmdir()
        self.users.audit(acteur, "sauvegarde", f"{len(noms)} base(s) : {', '.join(noms)}",
                         categorie=CATEGORIE_SECURITE, gravite="info")
        return cible

    # ── Données privées (comptages seulement, jamais le contenu) ─────────────

    def stats_donnees(self) -> Dict[str, Optional[int]]:
        stats: Dict[str, Optional[int]] = {"conversations": None, "messages": None, "quarantaine": None}
        chemin = Path(config.HISTORIQUE_DB)
        if chemin.parent != self.dossier_bases:
            chemin = self.dossier_bases / chemin.name
        if not chemin.exists():
            return stats
        try:
            with lecture(chemin) as conn:
                stats["conversations"] = int(conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0])
                stats["messages"] = int(conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0])
                stats["quarantaine"] = int(conn.execute(
                    "SELECT COUNT(*) FROM conversations WHERE owner_id IS NULL"
                ).fetchone()[0])
        except sqlite3.Error:
            pass
        return stats
