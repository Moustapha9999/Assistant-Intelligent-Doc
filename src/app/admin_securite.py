"""Admin → Sécurité : supervision et gestion de la sécurité (onglet de la page Admin).

Toutes les valeurs affichées viennent des tables réelles (journal d'audit, sessions, tentatives,
incidents) ou de la configuration du serveur ; une information absente est signalée comme
« Non configuré », « Non vérifié » ou « Données indisponibles ». Chaque action sensible est
revérifiée côté serveur (administrateur actif) et journalisée.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List

import streamlit as st

import config
from app import runtime_config
from app.securite_sqlite import STATUTS_INCIDENT, STATUTS_OUVERTS, SecuriteSQLite, depuis_heures
from app.ui_composants import afficher_avertissement, afficher_erreur, message_erreur, notifier
from app.utilisateurs_sqlite import MSG_SESSION_INVALIDE, UtilisateursSQLite
from securite import mots_de_passe, politique, totp, verifications
from securite.evenements import (
    CATEGORIE_SECURITE,
    GRAVITES,
    LIBELLES_GRAVITE,
    TYPES,
    libelle_type,
)

PERIODES = {"24 heures": 24, "7 jours": 24 * 7, "30 jours": 24 * 30}
COULEUR_GRAVITE = {"info": "gray", "faible": "blue", "moyenne": "orange", "elevee": "red", "critique": "red"}
COULEUR_STATUT = {
    verifications.OK: "green",
    verifications.ALERTE: "red",
    verifications.NON_CONFIGURE: "orange",
    verifications.NON_VERIFIE: "gray",
}
CLE_VERIFS = "secu_dernieres_verifications"
CLE_SECRET_MFA = "secu_secret_mfa_en_cours"
ACTIONS_AUTH = ("auth_succes", "auth_echec", "auth_verrouillage", "auth_bloquee", "auth_compte_suspendu",
                "auth_deblocage", "oauth_echec", "mfa_echec", "mfa_active", "mfa_desactive",
                "session_revoquee", "mot_de_passe_reinitialise", "mot_de_passe_modifie",
                "mot_de_passe_echec")
ACTIONS_ROLES = ("set_tier", "suspend", "unsuspend", "seed_admin")
ACTIONS_REFUS = ("acces_refuse", "api_acces_refuse")


def _libelle_compte(u: Dict[str, Any]) -> str:
    return u.get("email") or u.get("github_login") or u.get("display_name") or (u.get("id") or "")[:8]


def _tableau_evenements(evenements: List[Dict[str, Any]], vide: str) -> None:
    if not evenements:
        st.caption(vide)
        return
    st.dataframe(
        [
            {
                "Date (UTC)": (e.get("cree_le") or "")[:19].replace("T", " "),
                "Gravité": LIBELLES_GRAVITE.get(e.get("gravite"), e.get("gravite")),
                "Événement": libelle_type(e.get("action") or ""),
                "Détail": e.get("details") or "",
                "Acteur": (e.get("admin_id") or "—")[:12],
            }
            for e in evenements
        ],
        hide_index=True,
        use_container_width=True,
    )


def _badge_statut(statut: str) -> None:
    st.badge(verifications.LIBELLES_STATUT.get(statut, statut), color=COULEUR_STATUT.get(statut, "gray"))


# ── Sous-sections ────────────────────────────────────────────────────────────


def _vue_ensemble(db: UtilisateursSQLite, sec: SecuriteSQLite, depuis: str, periode: str) -> None:
    try:
        r = sec.resume(depuis)
    except Exception as exc:
        afficher_erreur("Données de sécurité indisponibles.", exc)
        return
    c = st.columns(4)
    c[0].metric(f"Échecs d'authentification ({periode})", r["echecs_auth"])
    c[1].metric("Blocages temporaires", r["blocages"])
    c[2].metric("Accès refusés", r["refus_acces"])
    c[3].metric("Incidents ouverts", r["incidents_ouverts"])
    c = st.columns(4)
    c[0].metric("Administrateurs actifs", r["admins"],
                delta=f"{r['admins_sans_mfa']} sans MFA" if r["admins_sans_mfa"] else "tous avec MFA",
                delta_color="inverse" if r["admins_sans_mfa"] else "normal")
    c[1].metric("Sessions de comptes actives", r["sessions_comptes"])
    c[2].metric("Sessions invitées actives", r["sessions_invites"])
    c[3].metric("Signaux d'injection", r["injections"])

    st.markdown("##### Événements par gravité")
    cols = st.columns(len(GRAVITES))
    for col, g in zip(cols, GRAVITES):
        col.metric(LIBELLES_GRAVITE[g], r["par_gravite"].get(g, 0))

    st.markdown("##### État des contrôles")
    e1, e2, e3 = st.columns(3)
    with e1:
        st.caption("Vérifications de sécurité")
        derniere = db.lister_audit(1, categorie=CATEGORIE_SECURITE, actions=["verification_securite"])
        if derniere:
            st.write(f"{derniere[0]['details']}")
            st.caption(f"Le {(derniere[0]['cree_le'] or '')[:16].replace('T', ' ')} UTC")
        else:
            _badge_statut(verifications.NON_VERIFIE)
    with e2:
        st.caption("Vulnérabilités des dépendances")
        rapport = verifications.lire_rapport_dependances()
        if rapport is None:
            _badge_statut(verifications.NON_VERIFIE)
        else:
            st.write(f"{rapport['nb_vulns']} vulnérabilité(s) connue(s)")
            st.caption(f"Rapport pip-audit du {rapport['date'][:10]}")
    with e3:
        st.caption("Sauvegardes")
        sauvegardes = sec.lister_sauvegardes()
        if sauvegardes:
            st.write(f"Dernière : {sauvegardes[0]['date'][:16].replace('T', ' ')} UTC")
        else:
            _badge_statut(verifications.NON_CONFIGURE)

    st.markdown("##### Événements importants")
    _tableau_evenements(
        db.lister_audit(15, categorie=CATEGORIE_SECURITE, depuis=depuis,
                        gravites=["moyenne", "elevee", "critique"]),
        "Aucun événement de gravité moyenne ou supérieure sur la période.",
    )


def _mfa_personnelle(db: UtilisateursSQLite, admin: Dict[str, Any]) -> None:
    st.markdown("##### Ma vérification en deux étapes")
    compte = db.obtenir(admin["id"]) or {}
    if compte.get("totp_actif"):
        st.badge("MFA active", color="green")
        with st.form("secu_mfa_off"):
            code = st.text_input("Code actuel pour désactiver", max_chars=6)
            if st.form_submit_button("Désactiver la MFA"):
                ok, msg = db.verifier_totp(admin["id"], code)
                if ok and db.desactiver_totp(admin["id"], acteur=admin["id"]):
                    notifier("MFA désactivée.", "info")
                    st.rerun()
                else:
                    afficher_erreur(msg)
        return
    st.badge("MFA inactive", color="red")
    st.caption("Compatible Google Authenticator, Microsoft Authenticator, FreeOTP… (TOTP, 6 chiffres, 30 s).")
    secret = st.session_state.get(CLE_SECRET_MFA)
    if not secret:
        if st.button("Configurer la MFA", key="secu_mfa_prep"):
            try:
                st.session_state[CLE_SECRET_MFA] = db.preparer_totp(admin["id"])
            except ValueError as exc:
                afficher_erreur(message_erreur("La MFA n'a pas pu être préparée.", exc))
            st.rerun()
        return
    st.write("1. Ajoutez un compte dans votre application avec cette clé (saisie manuelle) :")
    st.code(secret, language=None)
    st.caption("Ou importez cette URI dans une application qui l'accepte :")
    st.code(totp.uri_provisioning(secret, _libelle_compte(admin)), language=None)
    with st.form("secu_mfa_on"):
        code = st.text_input("2. Code affiché par l'application", max_chars=6)
        c1, c2 = st.columns(2)
        activer = c1.form_submit_button("Activer", type="primary")
        annuler = c2.form_submit_button("Annuler")
    if annuler:
        st.session_state.pop(CLE_SECRET_MFA, None)
        st.rerun()
    if activer:
        if db.activer_totp(admin["id"], code):
            st.session_state.pop(CLE_SECRET_MFA, None)
            notifier("MFA activée : le code sera demandé à chaque connexion.")
            st.rerun()
        else:
            afficher_erreur("Code invalide. Vérifiez l'heure de votre téléphone et réessayez.")


CLE_MDP_OUVERT = "secu_mdp_ouvert"
CLE_MDP_EN_COURS = "secu_mdp_en_cours"
CLE_MDP_ERREUR = "secu_mdp_erreur"
_CHAMPS_MDP = ("secu_mdp_actuel", "secu_mdp_nouveau", "secu_mdp_confirmation", "secu_mdp_code")


def fermer_mot_de_passe() -> None:
    for cle in (*_CHAMPS_MDP, CLE_MDP_OUVERT, CLE_MDP_EN_COURS, CLE_MDP_ERREUR):
        st.session_state.pop(cle, None)


def _soumettre_mot_de_passe() -> None:
    st.session_state[CLE_MDP_EN_COURS] = True
    st.session_state.pop(CLE_MDP_ERREUR, None)


def formulaire_mot_de_passe(db: UtilisateursSQLite, jeton_courant: str) -> None:
    """Changement du mot de passe du compte connecté ; toutes les règles sont appliquées par
    `UtilisateursSQLite.modifier_mon_mot_de_passe` (l'indicateur n'est qu'un guide)."""
    compte = db.valider_session(jeton_courant)
    if not compte:
        afficher_erreur(MSG_SESSION_INVALIDE)
        return
    st.caption(
        "Après la modification, vos autres sessions (autres navigateurs ou appareils) sont fermées ; "
        "celle-ci reste ouverte."
    )
    actuel = st.text_input("Mot de passe actuel", type="password", key=_CHAMPS_MDP[0],
                           autocomplete="current-password")
    nouveau = st.text_input("Nouveau mot de passe", type="password", key=_CHAMPS_MDP[1],
                            autocomplete="new-password")
    confirmation = st.text_input("Confirmer le nouveau mot de passe", type="password",
                                 key=_CHAMPS_MDP[2], autocomplete="new-password")
    code = ""
    if compte.get("totp_actif"):
        code = st.text_input("Code de votre application d'authentification", max_chars=6,
                             key=_CHAMPS_MDP[3], autocomplete="one-time-code")

    exigences = mots_de_passe.evaluer(nouveau or "", [compte.get("email") or "", compte.get("display_name") or ""])
    exigences.append(("Confirmation identique au nouveau mot de passe", bool(confirmation) and confirmation == nouveau))
    st.markdown("\n".join(
        f"- :{'green' if ok else 'gray'}[{':material/check_circle:' if ok else ':material/radio_button_unchecked:'} "
        f"{libelle}]"
        for libelle, ok in exigences
    ))

    if st.session_state.get(CLE_MDP_ERREUR):
        afficher_erreur(st.session_state[CLE_MDP_ERREUR])
    en_cours = bool(st.session_state.get(CLE_MDP_EN_COURS))
    complet = bool(actuel and nouveau and confirmation and (code or not compte.get("totp_actif")))
    c1, c2 = st.columns(2)
    c1.button("Modifier le mot de passe", type="primary", key="secu_mdp_valider", use_container_width=True,
              disabled=en_cours or not complet, on_click=_soumettre_mot_de_passe)
    if c2.button("Annuler", key="secu_mdp_annuler", disabled=en_cours, use_container_width=True):
        fermer_mot_de_passe()
        st.rerun()
    if not en_cours:
        return
    try:
        with st.spinner("Vérification…"):
            ok, msg = db.modifier_mon_mot_de_passe(jeton_courant, actuel or "", nouveau or "",
                                                   confirmation or "", code or "")
    except sqlite3.Error as exc:
        ok, msg = False, message_erreur(
            "Service momentanément indisponible : votre mot de passe n'a pas été modifié.", exc,
            "Réessayez dans un instant.",
        )
    finally:
        st.session_state[CLE_MDP_EN_COURS] = False
    if ok:
        fermer_mot_de_passe()
        notifier(msg)
    else:
        st.session_state[CLE_MDP_ERREUR] = msg
        for cle in (_CHAMPS_MDP[0], _CHAMPS_MDP[3]):
            st.session_state.pop(cle, None)
    st.rerun()


@st.dialog("Modifier mon mot de passe", width="small", on_dismiss=fermer_mot_de_passe)
def dialogue_mot_de_passe(db: UtilisateursSQLite, jeton_courant: str) -> None:
    formulaire_mot_de_passe(db, jeton_courant)


def _authentification(db: UtilisateursSQLite, sec: SecuriteSQLite, admin: Dict[str, Any],
                      depuis: str, jeton_courant: str) -> None:
    st.markdown("##### Politique en vigueur")
    p = politique.valeurs()
    st.markdown(
        f"- Mots de passe : **scrypt** (sel aléatoire de 16 octets), 8 caractères minimum à l'inscription, "
        f"{mots_de_passe.LONGUEUR_MIN} minimum (mots de passe courants refusés) lors d'un changement.\n"
        f"- Blocage temporaire après **{p['SECU_MAX_ECHECS']} échecs** en {p['SECU_FENETRE_MIN']} min "
        f"(par e-mail ; seuil ×4 par adresse IP quand elle est connue).\n"
        f"- Message d'échec identique que le compte existe ou non ; suspension révélée seulement après "
        f"un mot de passe correct.\n"
        f"- Sessions : jeton aléatoire, seule son empreinte SHA-256 est stockée ; expiration "
        f"**{p['SESSION_JOURS_COMPTE']} j** (comptes) / **{p['SESSION_JOURS_INVITE']} j** (invités), "
        f"révocation à la déconnexion, à la suspension et à la rétrogradation d'un administrateur.\n"
        "- Récupération de compte : pas de réinitialisation par e-mail (aucun envoi configuré) ; "
        "un administrateur réinitialise via `scripts/securite_admin.py`."
    )
    _mfa_personnelle(db, admin)

    st.markdown("##### Sessions de comptes actives")
    sessions = sec.sessions_actives()
    if not sessions:
        st.caption("Aucune session de compte active.")
    else:
        st.dataframe(
            [{"Compte": _libelle_compte(s), "Rôle": s["tier"], "Sessions": s["n"],
              "Dernière ouverture (UTC)": (s["derniere"] or "")[:16].replace("T", " ")} for s in sessions],
            hide_index=True, use_container_width=True,
        )
        choix = {f"{_libelle_compte(s)} ({s['tier']}, {s['n']})": s["id"] for s in sessions}
        with st.form("secu_revoquer"):
            cible = st.selectbox("Révoquer toutes les sessions de", list(choix))
            confirme = st.checkbox("Je confirme : le compte devra se reconnecter")
            if st.form_submit_button("Révoquer"):
                if not confirme:
                    afficher_erreur("Cochez la confirmation.")
                elif not db.est_admin_actif(admin["id"]):
                    afficher_erreur("Action réservée aux administrateurs actifs.")
                else:
                    uid = choix[cible]
                    n = db.revoquer_sessions_utilisateur(
                        uid, acteur=admin["id"], sauf_jeton=jeton_courant if uid == admin["id"] else None
                    )
                    notifier(f"{n} session(s) révoquée(s).")
                    st.rerun()

    st.markdown("##### Événements d'authentification")
    _tableau_evenements(
        db.lister_audit(200, categorie=CATEGORIE_SECURITE, depuis=depuis, actions=ACTIONS_AUTH),
        "Aucun événement d'authentification sur la période.",
    )


MATRICE_PERMISSIONS = [
    {"Action": "Poser une question", "Invité": "Oui (quota)", "Compte": "Oui (quota)", "Admin": "Oui"},
    {"Action": "Joindre fichiers / audio", "Invité": "Non (refus serveur)", "Compte": "Oui", "Admin": "Oui"},
    {"Action": "Lire ses conversations", "Invité": "Les siennes", "Compte": "Les siennes", "Admin": "Les siennes"},
    {"Action": "Page Administration", "Invité": "Non", "Compte": "Non", "Admin": "Oui"},
    {"Action": "Changer un rôle / suspendre", "Invité": "Non", "Compte": "Non", "Admin": "Oui (vérifié en base)"},
    {"Action": "Corpus, paramètres IA, sécurité", "Invité": "Non", "Compte": "Non", "Admin": "Oui"},
]


def _permissions(db: UtilisateursSQLite, sec: SecuriteSQLite, depuis: str) -> None:
    st.caption(
        "Les rôles se modifient dans l'onglet Utilisateurs. La base vérifie que l'auteur est un "
        "administrateur actif, interdit l'auto-rétrogradation et la rétrogradation ou la suspension "
        "du dernier administrateur, puis journalise l'opération."
    )
    st.markdown("##### Comptes privilégiés")
    admins = sec.comptes_privilegies()
    st.dataframe(
        [{"Compte": _libelle_compte(a), "MFA": "Active" if a["totp_actif"] else "Inactive",
          "Statut": "Suspendu" if a["suspended"] else "Actif",
          "Dernière connexion (UTC)": (a["derniere_connexion"] or "—")[:16].replace("T", " ")} for a in admins],
        hide_index=True, use_container_width=True,
    )
    st.markdown("##### Matrice des permissions (appliquée côté serveur)")
    st.dataframe(MATRICE_PERMISSIONS, hide_index=True, use_container_width=True)
    st.markdown("##### Modifications de rôles et de statuts")
    _tableau_evenements(db.lister_audit(100, depuis=depuis, actions=ACTIONS_ROLES),
                        "Aucune modification sur la période.")
    st.markdown("##### Accès refusés")
    _tableau_evenements(db.lister_audit(100, depuis=depuis, actions=ACTIONS_REFUS),
                        "Aucun refus d'accès sur la période.")


def _menaces(db: UtilisateursSQLite, sec: SecuriteSQLite, admin: Dict[str, Any], depuis: str) -> None:
    st.markdown("##### Alertes détectées")
    st.caption("Signaux calculés par des règles simples : à qualifier, pas des attaques confirmées.")
    alertes = sec.alertes(depuis)
    if not alertes:
        st.caption("Aucune alerte sur la période.")
    for i, a in enumerate(alertes):
        with st.container(border=True):
            c1, c2 = st.columns([5, 1])
            with c1:
                st.badge(LIBELLES_GRAVITE.get(a["gravite"], a["gravite"]), color=COULEUR_GRAVITE[a["gravite"]])
                st.write(a["titre"])
                st.caption(a["detail"])
            with c2:
                if st.button("Ouvrir un incident", key=f"secu_alerte_{i}", use_container_width=True):
                    try:
                        n = sec.creer_incident(admin["id"], a["type"], a["gravite"], a["titre"], a["detail"])
                        notifier(f"Incident #{n} ouvert.")
                    except (PermissionError, ValueError) as exc:
                        notifier(message_erreur("L'incident n'a pas pu être ouvert.", exc), "erreur")
                    st.rerun()

    st.markdown("##### Événements de sécurité")
    f1, f2 = st.columns(2)
    gravites = f1.multiselect("Gravité", list(GRAVITES), default=["faible", "moyenne", "elevee", "critique"],
                              format_func=LIBELLES_GRAVITE.get, key="secu_f_gravite")
    types = f2.multiselect("Type", sorted(TYPES), format_func=libelle_type, key="secu_f_type")
    _tableau_evenements(
        db.lister_audit(300, categorie=CATEGORIE_SECURITE, depuis=depuis, gravites=gravites, actions=types),
        "Aucun événement pour ces filtres.",
    )

    st.markdown("##### Incidents")
    statuts = st.multiselect("Statut", list(STATUTS_INCIDENT), default=list(STATUTS_OUVERTS),
                             format_func=STATUTS_INCIDENT.get, key="secu_f_statut")
    incidents = sec.lister_incidents(statuts)
    if not incidents:
        st.caption("Aucun incident pour ce filtre.")
    for inc in incidents:
        titre = (f"#{inc['id']} · {STATUTS_INCIDENT[inc['statut']]} · "
                 f"{LIBELLES_GRAVITE.get(inc['gravite'])} · {inc['titre']}")
        with st.expander(titre):
            st.caption(f"Type : {inc['type']} · ouvert le {inc['cree_le'][:16].replace('T', ' ')} UTC "
                       f"· mis à jour le {inc['maj_le'][:16].replace('T', ' ')} UTC")
            if inc["description"]:
                st.text(inc["description"])
            st.dataframe(
                [{"Date (UTC)": h["cree_le"][:16].replace("T", " "),
                  "Statut": f"{STATUTS_INCIDENT.get(h['ancien_statut'], '—')} → {STATUTS_INCIDENT[h['nouveau_statut']]}",
                  "Actions réalisées": h["commentaire"], "Auteur": (h["auteur"] or "")[:12]}
                 for h in sec.historique_incident(inc["id"])],
                hide_index=True, use_container_width=True,
            )
            with st.form(f"secu_inc_{inc['id']}"):
                nouveau = st.selectbox("Nouveau statut", list(STATUTS_INCIDENT), format_func=STATUTS_INCIDENT.get,
                                       index=list(STATUTS_INCIDENT).index(inc["statut"]))
                commentaire = st.text_area("Actions réalisées (obligatoire)", max_chars=2000)
                if st.form_submit_button("Enregistrer"):
                    try:
                        sec.changer_statut(admin["id"], inc["id"], nouveau, commentaire)
                        notifier("Incident mis à jour.")
                        st.rerun()
                    except (PermissionError, ValueError) as exc:
                        afficher_erreur(str(exc))

    with st.expander("Déclarer un incident manuellement"):
        with st.form("secu_inc_nouveau", clear_on_submit=True):
            titre = st.text_input("Titre", max_chars=200)
            c1, c2 = st.columns(2)
            gravite = c1.selectbox("Gravité", list(GRAVITES), index=2, format_func=LIBELLES_GRAVITE.get)
            type_ = c2.text_input("Type", value="autre", max_chars=60)
            description = st.text_area("Description (sans mot de passe, jeton ni contenu confidentiel)",
                                       max_chars=4000)
            if st.form_submit_button("Ouvrir l'incident", type="primary"):
                try:
                    n = sec.creer_incident(admin["id"], type_, gravite, titre, description)
                    notifier(f"Incident #{n} ouvert.")
                    st.rerun()
                except (PermissionError, ValueError) as exc:
                    afficher_erreur(str(exc))


def _donnees(sec: SecuriteSQLite, admin: Dict[str, Any]) -> None:
    st.markdown("##### Mécanismes en place")
    st.markdown(
        "- Chaque conversation, favori et export est lié au `users.id` de l'identité validée par le "
        "serveur ; un identifiant de conversation appartenant à un autre compte renvoie « introuvable ».\n"
        "- Les données antérieures à la migration d'isolation (sans propriétaire) sont en quarantaine : "
        "jamais renvoyées.\n"
        "- Requêtes SQL paramétrées ; noms de colonnes dynamiques limités à des listes fixes.\n"
        "- Accès administrateur aux contenus : les avis (extrait de la question et de la réponse, "
        "envoyés volontairement par l'utilisateur) et les 120 premiers caractères des questions dans "
        "l'onglet Activité. Les conversations complètes ne sont pas affichées dans l'Admin."
    )
    st.markdown("##### Volumes (comptages, sans contenu)")
    stats = sec.stats_donnees()
    c = st.columns(3)
    for col, (cle, libelle) in zip(c, (("conversations", "Conversations"), ("messages", "Messages"),
                                       ("quarantaine", "En quarantaine"))):
        col.metric(libelle, stats[cle] if stats[cle] is not None else "Données indisponibles")
    st.markdown("##### Conservation")
    afficher_avertissement(
        "Politique de conservation : non configurée. Les conversations sont conservées jusqu'à leur "
        "suppression par l'utilisateur ; en production (Streamlit Community Cloud), le disque est "
        "éphémère et toutes les bases sont perdues à chaque redéploiement."
    )
    st.markdown("##### Sauvegardes")
    sauvegardes = sec.lister_sauvegardes()
    if sauvegardes:
        st.dataframe(
            [{"Sauvegarde": s["nom"], "Bases": s["fichiers"], "Taille (Ko)": round(s["taille"] / 1024)}
             for s in sauvegardes],
            hide_index=True, use_container_width=True,
        )
    else:
        st.caption("Non configuré : aucune sauvegarde n'a encore été créée.")
    st.caption(f"Copie cohérente (API backup SQLite) dans `{sec.dossier_sauvegardes}` ; "
               f"les 5 plus récentes sont conservées. Même disque que les bases : à copier ailleurs.")
    with st.form("secu_sauvegarde"):
        confirme = st.checkbox("Créer maintenant une copie de toutes les bases")
        if st.form_submit_button("Sauvegarder"):
            if not confirme:
                afficher_erreur("Cochez la confirmation.")
            else:
                try:
                    cible = sec.creer_sauvegarde(admin["id"])
                    notifier(f"Sauvegarde créée : {cible.name}.")
                    st.rerun()
                except (PermissionError, OSError) as exc:
                    afficher_erreur("La sauvegarde a échoué.", exc)


def _fichiers(db: UtilisateursSQLite, depuis: str) -> None:
    st.markdown("##### Contrôles appliqués à chaque pièce jointe")
    st.markdown(
        "- Réservé aux comptes connectés (vérifié par le serveur, pas seulement masqué dans l'interface).\n"
        "- Liste blanche d'extensions, puis vérification du **contenu réel** (signature PDF, images, audio ; "
        "structure OOXML pour .docx / .xlsx / .pptx ; en-tête OLE pour .xls).\n"
        "- Archives Office : nombre d'éléments, taille décompressée et taux de compression bornés "
        "(bombes de décompression).\n"
        "- Macros VBA **jamais exécutées** (détectées et signalées) ; .docm / .xlsm refusés.\n"
        "- Traitement **en mémoire** : rien n'est écrit sur disque ni exécuté ; nom de fichier assaini ; "
        "images décodées puis ré-encodées (métadonnées et contenus cachés supprimés).\n"
        "- Le texte extrait est rattaché à la conversation de son propriétaire ; aucune URL publique."
    )
    st.markdown("##### Limites")
    st.dataframe(
        [
            {"Limite": "Taille par fichier", "Valeur": f"{config.UPLOAD_MAX_BYTES // (1024 * 1024)} Mo"},
            {"Limite": "Fichiers par message", "Valeur": str(config.FICHIERS_MAX_PAR_MESSAGE)},
            {"Limite": "Pages PDF lues", "Valeur": str(config.PDF_MAX_PAGES)},
            {"Limite": "Taille décompressée (archives)", "Valeur": f"{config.ARCHIVE_MAX_DECOMPRESSE // (1024 * 1024)} Mo"},
            {"Limite": "Éléments par archive", "Valeur": str(config.ARCHIVE_MAX_MEMBRES)},
            {"Limite": "Pixels par image", "Valeur": f"{config.IMAGE_MAX_PIXELS:,}".replace(",", " ")},
            {"Limite": "Délai d'extraction", "Valeur": f"{config.FICHIERS_TIMEOUT_EXTRACTION_S:.0f} s"},
        ],
        hide_index=True, use_container_width=True,
    )
    st.caption("Extensions acceptées : " + ", ".join(sorted(config.UPLOAD_EXTENSIONS_OK)))
    st.caption("Refusées avec explication : " + ", ".join(sorted(config.UPLOAD_FORMATS_REFUSES)))
    st.markdown("##### Fichiers refusés")
    _tableau_evenements(db.lister_audit(200, categorie=CATEGORIE_SECURITE, depuis=depuis, actions=["fichier_refuse"]),
                        "Aucun fichier refusé sur la période.")


def _ia(db: UtilisateursSQLite, sec: SecuriteSQLite, depuis: str, periode: str) -> None:
    st.markdown("##### Clés des services (jamais affichées)")
    c = st.columns(3)
    for col, (nom, var) in zip(c, (("Groq (LLM, vision, audio)", "GROQ_API_KEY"),
                                   ("Tavily (recherche web)", "TAVILY_API_KEY"),
                                   ("Clé admin de l'API REST", "ADMIN_API_KEY"))):
        with col:
            st.caption(nom)
            st.badge("Configurée" if (os.getenv(var) or "").strip() else "Non configurée",
                     color="green" if (os.getenv(var) or "").strip() else "orange")

    st.markdown("##### Utilisation")
    vol = sec.volumes_ia(depuis)
    seuil = politique.valeur("SECU_SEUIL_REQ_HEURE")
    plafond = politique.valeur("QUOTA_INVITES_GLOBAL_HEURE")
    r = sec.resume(depuis)
    c = st.columns(4)
    c[0].metric(f"Requêtes ({periode})", vol["total"])
    c[1].metric("Invités, dernière heure",
                f"{db.requetes_invites_derniere_heure()} / {plafond}" if plafond else "Plafond désactivé")
    c[2].metric("Quotas dépassés", r["quotas"])
    c[3].metric("Erreurs du service d'IA", r["erreurs_ia"])
    if vol["top"]:
        st.dataframe(
            [{"Compte": _libelle_compte({**t, "id": t["user_id"]}), "Rôle": t["tier"] or "—", "Requêtes": t["n"]}
             for t in vol["top"]],
            hide_index=True, use_container_width=True,
        )
    st.caption(f"Alerte « volume anormal » au-delà de {seuil} requêtes par compte et par heure "
               "(onglet Menaces et incidents).")

    st.markdown("##### Manipulation des instructions (prompt injection)")
    st.markdown(
        "- Les fichiers, passages du corpus et pages web sont délimités comme **données non fiables** ; "
        "le prompt système interdit d'exécuter les consignes qu'ils contiennent.\n"
        "- Le modèle n'a **aucun outil** agissant sur les comptes, les rôles ou les données : les "
        "autorisations sont décidées par le serveur, jamais par une réponse du modèle.\n"
        "- Aucune clé ni secret n'est placé dans le prompt.\n"
        "- Détection par motifs (question et fichiers) : un **signal** journalisé, sans blocage."
    )
    _tableau_evenements(
        db.lister_audit(100, categorie=CATEGORIE_SECURITE, depuis=depuis, actions=["ia_injection_suspecte"]),
        "Aucun signal sur la période.",
    )

    st.markdown("##### Données transmises aux fournisseurs")
    st.dataframe(
        [
            {"Capacité": "Réponse (LLM Groq)", "Données envoyées": "Question, 8 derniers messages, passages "
             "du corpus, extraits des fichiers joints, résultats web", "Déclenchement": "Chaque question"},
            {"Capacité": "Vision (Groq)", "Données envoyées": "Images jointes ré-encodées, pages PDF rendues",
             "Déclenchement": "Image ou figure à analyser (compte requis)"},
            {"Capacité": "Transcription (Groq Whisper)", "Données envoyées": "Enregistrement audio",
             "Déclenchement": "Dictée (compte requis)"},
            {"Capacité": "Recherche web (Tavily)", "Données envoyées": "Texte de la question",
             "Déclenchement": "Décidé par l'orchestrateur, désactivable dans Paramètres IA"},
        ],
        hide_index=True, use_container_width=True,
    )


def _configuration(db: UtilisateursSQLite, admin: Dict[str, Any]) -> None:
    st.caption(
        "Valeurs validées côté serveur (entiers bornés) et enregistrées dans `runtime_ia.json`. "
        "Chaque modification est journalisée avec l'ancienne et la nouvelle valeur."
    )
    actuelles = politique.valeurs()
    with st.form("secu_config"):
        saisies = {}
        for p in politique.PARAMETRES:
            saisies[p.cle] = st.number_input(
                p.libelle, min_value=p.mini, max_value=p.maxi, value=actuelles[p.cle], step=1,
                help=p.aide or None, key=f"secu_cfg_{p.cle}",
            )
        enregistrer = st.form_submit_button("Enregistrer", type="primary")
    if enregistrer:
        if not db.est_admin_actif(admin["id"]):
            afficher_erreur("Action réservée aux administrateurs actifs.")
            return
        propres, erreurs = politique.valider(saisies)
        if erreurs:
            for e in erreurs:
                afficher_erreur(e)
            return
        changes = {k: v for k, v in propres.items() if v != actuelles.get(k)}
        if not changes:
            notifier("Aucune modification.", "info")
            return
        try:
            runtime_config.sauvegarder(changes)
        except OSError as exc:
            afficher_erreur("Les paramètres n'ont pas pu être enregistrés.", exc)
            return
        db.audit(admin["id"], "config_securite",
                 " ; ".join(f"{k} : {actuelles.get(k)} → {v}" for k, v in changes.items()),
                 categorie=CATEGORIE_SECURITE, gravite="moyenne")
        notifier("Paramètres de sécurité enregistrés.")
        st.rerun()
    st.markdown("##### Non disponibles dans cette architecture")
    st.markdown(
        "- **Notifications de sécurité** : non configurées (aucun canal d'envoi e-mail ou webhook).\n"
        "- **MFA obligatoire** : non imposée automatiquement (risque de verrouiller l'administration) ; "
        "son absence est signalée dans les vérifications.\n"
        "- **Limites de fichiers** : fixées par variables d'environnement (`UPLOAD_MAX_BYTES`, "
        "`FICHIERS_MAX_PAR_MESSAGE`…), car lues au démarrage."
    )


def _rapport_markdown(resultats: List[Dict[str, str]], date: str) -> str:
    lignes = ["# Rapport de vérification de sécurité — AssistDoc", "", f"Date : {date} (UTC)", "",
              "| Contrôle | Statut | Détail |", "|---|---|---|"]
    for r in resultats:
        detail = r["detail"].replace("|", "/")
        lignes.append(f"| {r['titre']} | {verifications.LIBELLES_STATUT[r['statut']]} | {detail} |")
    return "\n".join(lignes) + "\n"


def _rapports(db: UtilisateursSQLite, sec: SecuriteSQLite, admin: Dict[str, Any]) -> None:
    if st.button("Lancer les vérifications", type="primary", key="secu_lancer"):
        try:
            resultats = verifications.executer(db, sec)
        except Exception as exc:
            afficher_erreur("Les vérifications n'ont pas pu s'exécuter.", exc)
        else:
            compte = verifications.resume_resultats(resultats)
            date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
            st.session_state[CLE_VERIFS] = {"date": date, "resultats": [r.to_dict() for r in resultats]}
            db.audit(admin["id"], "verification_securite",
                     ", ".join(f"{n} {verifications.LIBELLES_STATUT[s].lower()}" for s, n in compte.items() if n),
                     categorie=CATEGORIE_SECURITE,
                     gravite="moyenne" if compte.get(verifications.ALERTE) else "info")
    dernieres = st.session_state.get(CLE_VERIFS)
    if not dernieres:
        st.caption("Non vérifié pendant cette session : lancez les vérifications.")
    else:
        st.caption(f"Résultats du {dernieres['date']} UTC")
        for r in dernieres["resultats"]:
            c1, c2 = st.columns([1, 4])
            with c1:
                _badge_statut(r["statut"])
            with c2:
                st.write(f"**{r['titre']}**")
                st.caption(r["detail"])
        st.download_button(
            "Télécharger le rapport (Markdown)",
            _rapport_markdown(dernieres["resultats"], dernieres["date"]),
            file_name=f"rapport_securite_{dernieres['date'][:10]}.md",
            mime="text/markdown",
        )

    st.markdown("##### Dépendances (pip-audit)")
    rapport = verifications.lire_rapport_dependances()
    if rapport is None:
        st.caption("Non vérifié : produisez `docs/securite/pip_audit.json` avec "
                   "`pip-audit -r requirements.txt --format json`.")
    elif not rapport["vulnerables"]:
        st.caption(f"Aucune vulnérabilité connue ({rapport['paquets']} paquets, rapport du {rapport['date'][:10]}).")
    else:
        st.dataframe(
            [{"Paquet": v["nom"], "Version": v["version"], "Vulnérabilités": ", ".join(v["vulns"]),
              "Corrigé en": ", ".join(v["correctifs"]) or "—"} for v in rapport["vulnerables"]],
            hide_index=True, use_container_width=True,
        )


# ── Point d'entrée ───────────────────────────────────────────────────────────


def afficher(db: UtilisateursSQLite, admin: Dict[str, Any], jeton_courant: str,
             entete: Callable[[str, str, str], None]) -> None:
    entete("Sécurité", "Surveillance, incidents, sessions, permissions et vérifications.", "securite")
    if not db.est_admin_actif(admin.get("id")):
        afficher_erreur("Accès refusé : administrateur actif requis.")
        return
    sec = SecuriteSQLite(db)
    periode = st.selectbox("Période", list(PERIODES), key="secu_periode")
    depuis = depuis_heures(PERIODES[periode])
    onglets = st.tabs([
        "Vue d'ensemble", "Authentification et sessions", "Utilisateurs et permissions",
        "Menaces et incidents", "Protection des données", "Sécurité des fichiers",
        "Sécurité de l'IA", "Configuration", "Rapports et vérifications",
    ])
    with onglets[0]:
        _vue_ensemble(db, sec, depuis, periode)
    with onglets[1]:
        _authentification(db, sec, admin, depuis, jeton_courant)
    with onglets[2]:
        _permissions(db, sec, depuis)
    with onglets[3]:
        _menaces(db, sec, admin, depuis)
    with onglets[4]:
        _donnees(sec, admin)
    with onglets[5]:
        _fichiers(db, depuis)
    with onglets[6]:
        _ia(db, sec, depuis, periode)
    with onglets[7]:
        _configuration(db, admin)
    with onglets[8]:
        _rapports(db, sec, admin)
