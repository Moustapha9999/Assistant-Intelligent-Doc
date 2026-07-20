"""
Dashboard Admin AssistDoc — modules séparés, feedbacks, corpus, paramètres IA.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from app import admin_corpus
from app import runtime_config
from app.auth_basique import (
    deconnecter,
    est_admin_session,
    exiger_auth,
    users_db,
    utilisateur_session,
)
from app.historique_sqlite import HistoriqueSQLite
from app.quotas import QUOTAS

st.set_page_config(page_title="AssistDoc Admin", page_icon="🛡", layout="wide")

st.markdown(
    """
    <style>
    .admin-hero {
        background: linear-gradient(135deg, #1a2332 0%, #243044 55%, #1e3a5f 100%);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 16px;
        padding: 1.25rem 1.5rem;
        margin-bottom: 1.25rem;
    }
    .admin-hero h1 {
        margin: 0 0 0.35rem 0;
        font-size: 1.55rem;
        font-weight: 650;
        letter-spacing: -0.02em;
    }
    .admin-hero p { margin: 0; color: #a8b3c4; font-size: 0.95rem; }
    .metric-card {
        background: rgba(255,255,255,0.03);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 12px;
        padding: 0.85rem 1rem;
        margin-bottom: 0.5rem;
    }
    .fb-pos { color: #3dd68c; font-weight: 600; }
    .fb-neg { color: #f07178; font-weight: 600; }
    .fb-sig { color: #e6b450; font-weight: 600; }
    /* Déconnexion collée en bas de la sidebar Admin */
    section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {
        display: flex !important;
        flex-direction: column !important;
        min-height: calc(100vh - 6rem) !important;
    }
    section[data-testid="stSidebar"] .admin-sb-logout {
        margin-top: auto !important;
        padding-top: 1rem;
        padding-bottom: 0.5rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

exiger_auth()

if not est_admin_session():
    from app.auth_basique import formulaire_connexion

    st.markdown(
        """
        <div style="text-align:center;margin:1rem 0 0.5rem 0;color:#a8b3c4;font-size:0.95rem">
          Accès admin — connectez-vous avec le compte administrateur.
        </div>
        """,
        unsafe_allow_html=True,
    )
    formulaire_connexion(key_prefix="admin_gate")
    st.stop()

admin = utilisateur_session()
db = users_db()
histo = HistoriqueSQLite()


def _entete_module(titre: str, caption: str, module_key: str) -> None:
    """Titre + bouton Actualiser pour recharger les données du module."""
    c1, c2 = st.columns([5, 1])
    with c1:
        st.subheader(titre)
        if caption:
            st.caption(caption)
    with c2:
        if st.button(
            "🔄 Actualiser",
            key=f"admin_refresh_{module_key}",
            use_container_width=True,
            help="Recharger ce module",
        ):
            st.rerun()


with st.sidebar:
    st.markdown(
        '<div style="min-height:52vh" aria-hidden="true"></div>',
        unsafe_allow_html=True,
    )
    st.divider()
    st.caption(f"Connecté · {admin.get('email') or admin.get('display_name')}")
    if st.button(
        "Se déconnecter",
        key="admin_logout",
        use_container_width=True,
        type="primary",
        help="Quitter l'admin et revenir en mode invité",
    ):
        deconnecter()
        st.toast("Déconnecté — mode invité")
        try:
            st.switch_page("main.py")
        except Exception:
            st.rerun()

st.markdown(
    f"""
    <div class="admin-hero">
      <h1>🛡 AssistDoc Admin</h1>
      <p>Connecté : <b>{admin.get('email') or admin.get('display_name')}</b>
      · Pilotage users, feedbacks, corpus & paramètres IA</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ── Vue d'ensemble ──────────────────────────────────────────────
stats = db.stats_globales()
fb_stats = histo.stats_feedback()
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Utilisateurs", stats["users_total"])
m2.metric("Actifs 24h", stats["users_actifs_24h"])
m3.metric("Requêtes 24h", stats["asks_24h"])
m4.metric("👍 Feedbacks +", fb_stats["positifs"])
m5.metric("👎 / Signalements", f"{fb_stats['negatifs']} / {fb_stats['signalements']}")

modules = st.tabs(
    [
        "👥 Utilisateurs",
        "💬 Feedbacks",
        "📊 Activité",
        "📚 Corpus",
        "⚙️ Paramètres IA",
        "🧾 Audit",
    ]
)

# ── Module Utilisateurs ─────────────────────────────────────────
with modules[0]:
    _entete_module(
        "Gestion des comptes",
        "Invité / email / GitHub / admin — suspension et changement de tier.",
        "users",
    )
    col_a, col_b = st.columns([2, 1])
    with col_b:
        st.markdown("**Quotas**")
        for tier, q in QUOTAS.items():
            st.write(
                f"`{tier}` → {q.requetes_par_jour if q.requetes_par_jour >= 0 else '∞'} req/j"
            )
    with col_a:
        st.write("Répartition :", stats["par_tier"])

    users = db.lister_users(300)
    st.markdown(f"**{len(users)} utilisateur(s)**")
    for u in users:
        with st.container(border=True):
            cols = st.columns([3, 2, 2, 2, 2])
            with cols[0]:
                st.markdown(
                    f"**{u.get('display_name') or '—'}**  \n"
                    f"`{u.get('email') or u.get('github_login') or u['id'][:8]}`"
                )
            with cols[1]:
                st.caption(f"tier **{u.get('tier')}**")
                if u.get("suspended"):
                    st.error("suspendu")
            with cols[2]:
                st.caption(f"vu {(u.get('derniere_connexion') or '')[:16]}")
                st.caption(f"{db.compter_requetes_jour(u['id'])} req aujourd'hui")
            with cols[3]:
                nouveau = st.selectbox(
                    "Tier",
                    ["guest", "email", "github", "google", "apple", "admin"],
                    index=["guest", "email", "github", "google", "apple", "admin"].index(
                        u.get("tier")
                        if u.get("tier")
                        in {"guest", "email", "github", "google", "apple", "admin"}
                        else "guest"
                    ),
                    key=f"tier_{u['id']}",
                    label_visibility="collapsed",
                )
                if st.button("Appliquer", key=f"apply_tier_{u['id']}"):
                    db.set_tier(u["id"], nouveau, admin_id=admin["id"])
                    st.toast(f"Tier → {nouveau}")
                    st.rerun()
            with cols[4]:
                if u.get("suspended"):
                    if st.button("Réactiver", key=f"unsus_{u['id']}"):
                        db.suspendre(u["id"], False, admin_id=admin["id"])
                        st.rerun()
                else:
                    if st.button("Suspendre", key=f"sus_{u['id']}"):
                        db.suspendre(u["id"], True, admin_id=admin["id"])
                        st.rerun()

# ── Module Feedbacks ────────────────────────────────────────────
with modules[1]:
    _entete_module(
        "Avis utilisateurs sur les réponses IA",
        "👍 / 👎 et signalements d'erreur enregistrés depuis le chat.",
        "feedbacks",
    )
    # Recharger stats au clic Actualiser (même run = données fraîches)
    fb_stats = histo.stats_feedback()
    f1, f2, f3, f4 = st.columns(4)
    f1.metric("Total", fb_stats["total"])
    f2.metric("Positifs", fb_stats["positifs"])
    f3.metric("Négatifs", fb_stats["negatifs"])
    f4.metric("Signalements", fb_stats["signalements"])

    filtre = st.selectbox(
        "Filtrer",
        ["Tous", "Positifs", "Négatifs", "Signalements"],
        key="fb_filtre",
    )
    try:
        feedbacks = histo.lister_feedback(150)
    except Exception as exc:
        st.error(f"Impossible de charger les feedbacks : {exc}")
        st.caption("Arrêtez Streamlit (Ctrl+C) puis relancez `streamlit run src/app/main.py`.")
        feedbacks = []
    if filtre == "Positifs":
        feedbacks = [f for f in feedbacks if f.get("label") == "positif"]
    elif filtre == "Négatifs":
        feedbacks = [f for f in feedbacks if f.get("label") == "negatif"]
    elif filtre == "Signalements":
        feedbacks = [
            f for f in feedbacks if (f.get("commentaire") or "").startswith("[signalement]")
        ]

    if not feedbacks:
        st.info("Aucun feedback pour ce filtre. Les 👍 / 👎 du chat apparaissent ici.")
    for fb in feedbacks:
        note = int(fb.get("note") or 0)
        if note > 0:
            badge = '<span class="fb-pos">👍 Positif</span>'
        elif (fb.get("commentaire") or "").startswith("[signalement]"):
            badge = '<span class="fb-sig">⚠ Signalement</span>'
        else:
            badge = '<span class="fb-neg">👎 Négatif</span>'
        user = (fb.get("user_label") or "invité").strip()
        mode = (fb.get("mode") or "").strip()
        with st.container(border=True):
            st.markdown(
                f"{badge} · `{str(fb.get('cree_le') or '')[:19]}` · "
                f"**{user}**"
                + (f" · `{mode}`" if mode else "")
                + f" · conv **{(fb.get('titre') or fb.get('conversation_id') or '')[:40]}**",
                unsafe_allow_html=True,
            )
            if fb.get("question"):
                st.markdown(f"**Q :** {fb['question'][:300]}")
            if fb.get("extrait_court"):
                st.markdown(f"> {fb['extrait_court']}")
            elif not fb.get("question"):
                st.caption("(Ancien feedback sans snapshot — recliquez 👍/👎 sur une nouvelle réponse.)")
            if fb.get("commentaire"):
                st.caption(f"Commentaire : {fb['commentaire']}")

# ── Module Activité ─────────────────────────────────────────────
with modules[2]:
    _entete_module("Activité récente", "Requêtes et journal RAG.", "activite")
    for e in db.usage_recent(80):
        st.markdown(
            f"`{str(e.get('cree_le') or '')[:19]}` · **{e.get('kind')}** · "
            f"{e.get('display_name') or e.get('email') or e.get('user_id', '')[:8]} "
            f"({e.get('tier')})"
        )
        meta = e.get("meta_json") or "{}"
        try:
            m = json.loads(meta)
            if m.get("question"):
                st.caption(f"Q : {m['question'][:120]}")
        except json.JSONDecodeError:
            pass

    journal = ROOT / "logs" / "interactions.jsonl"
    if journal.exists():
        with st.expander("Journal RAG (interactions.jsonl)", expanded=False):
            for line in journal.read_text(encoding="utf-8", errors="replace").splitlines()[-30:]:
                try:
                    obj = json.loads(line)
                    st.caption(
                        f"{obj.get('mode')} · rag={obj.get('score_rag')} · "
                        f"fb={obj.get('feedback')} · {(obj.get('question') or '')[:70]}"
                    )
                except json.JSONDecodeError:
                    continue

# ── Module Corpus ───────────────────────────────────────────────
with modules[3]:
    _entete_module(
        "Corpus & indexation",
        "Ajouter, supprimer ou ré-indexer les documents Qdrant.",
        "corpus",
    )

    try:
        stats_c = admin_corpus.stats_corpus()
        c1, c2, c3 = st.columns(3)
        c1.metric("Chunks locaux", stats_c.get("nombre_chunks", 0))
        c2.metric("Dépôts", stats_c.get("nombre_repos", 0))
        qd = stats_c.get("qdrant") or {}
        c3.metric("Points Qdrant", qd.get("points", "?"))
        if qd.get("erreur"):
            st.warning(f"Qdrant : {qd['erreur']}")
        else:
            st.caption(f"Collection : `{qd.get('collection', '?')}`")
        if stats_c.get("par_langage"):
            with st.expander("Chunks par langage"):
                st.json(stats_c["par_langage"])
    except Exception as exc:
        st.warning(str(exc))

    st.markdown("#### ➕ Ajouter un document")
    with st.form("admin_add_doc"):
        r1, r2 = st.columns(2)
        with r1:
            repo = st.text_input("Identifiant (owner/repo)", value="manuel/upload")
        with r2:
            src = st.text_input("Fichier source", value="notes.md")
        texte = st.text_area("Contenu Markdown / texte", height=160)
        if st.form_submit_button("Indexer maintenant", type="primary"):
            ok, msg = admin_corpus.ajouter_document_texte(texte, repo, src)
            db.audit(admin["id"], "corpus_add", msg)
            if ok:
                st.success(msg)
            else:
                st.error(msg)

    st.markdown("#### 🗑 Supprimer un dépôt")
    try:
        repos = admin_corpus.lister_repos_qdrant(120)
    except Exception as exc:
        repos = []
        st.caption(str(exc))
    labels = [f"{r['nom_complet']} ({r['nb_points']})" for r in repos]
    if not labels:
        labels = admin_corpus.lister_repos_indexes()[:120]
    if labels:
        choix = st.selectbox("Dépôt", labels, key="corpus_del_sel")
        repo_del = choix.split(" (")[0] if " (" in choix else choix
        if st.button("Supprimer de Qdrant", type="secondary"):
            ok, msg = admin_corpus.supprimer_repo(repo_del)
            db.audit(admin["id"], "corpus_delete", msg)
            if ok:
                st.toast(msg)
            else:
                st.error(msg)
            st.rerun()
    else:
        st.info("Aucun dépôt listé.")

    st.markdown("#### 🔄 Ré-indexation")
    recreer = st.checkbox("Recréer la collection (destructif)", key="admin_recreer")
    if st.button("Lancer ré-indexation embeddings", type="primary"):
        with st.spinner("Ré-indexation en cours…"):
            ok, msg = admin_corpus.reindexer_collection(recreer=recreer)
        db.audit(admin["id"], "corpus_reindex", msg)
        if ok:
            st.success(msg)
        else:
            st.error(msg)

# ── Module Paramètres IA ────────────────────────────────────────
with modules[4]:
    _entete_module(
        "Configuration de l'IA",
        "Valeurs dans `data/app/runtime_ia.json` "
        "(redémarrer Streamlit pour tout recharger dans les modules déjà chargés).",
        "params_ia",
    )
    cfg = runtime_config.charger()
    with st.form("form_runtime_ia"):
        st.markdown("##### Modèle & génération")
        modele = st.text_input("Modèle LLM", value=str(cfg.get("LLM_MODEL", "")))
        vision = st.text_input(
            "Modèle vision", value=str(cfg.get("GROQ_VISION_MODEL", ""))
        )
        c1, c2 = st.columns(2)
        with c1:
            temp = st.slider(
                "Température",
                0.0,
                1.5,
                float(cfg.get("LLM_TEMPERATURE", 0.3)),
                0.05,
            )
            top_p = st.slider(
                "Top P", 0.0, 1.0, float(cfg.get("LLM_TOP_P", 0.95)), 0.05
            )
        with c2:
            max_tok = st.number_input(
                "Max tokens",
                min_value=256,
                max_value=8000,
                value=int(cfg.get("MAX_TOKENS", 3000)),
                step=100,
            )
            freq_p = st.slider(
                "Frequency penalty",
                0.0,
                2.0,
                float(cfg.get("LLM_FREQUENCY_PENALTY", 0.2)),
                0.05,
            )
        presence = st.slider(
            "Presence penalty",
            0.0,
            2.0,
            float(cfg.get("LLM_PRESENCE_PENALTY", 0.0)),
            0.05,
        )
        web_off = st.toggle(
            "Désactiver la recherche web",
            value=str(cfg.get("DESACTIVER_WEB_SEARCH", "false")).lower()
            in {"1", "true", "yes"},
        )

        st.markdown("##### Quotas (requêtes / jour)")
        q1, q2, q3 = st.columns(3)
        with q1:
            q_guest = st.number_input(
                "Invité", min_value=1, max_value=500, value=int(cfg.get("QUOTA_GUEST_REQ", 12))
            )
        with q2:
            q_email = st.number_input(
                "Email", min_value=1, max_value=2000, value=int(cfg.get("QUOTA_EMAIL_REQ", 80))
            )
        with q3:
            q_gh = st.number_input(
                "GitHub", min_value=1, max_value=5000, value=int(cfg.get("QUOTA_GITHUB_REQ", 200))
            )

        if st.form_submit_button("Enregistrer les paramètres", type="primary"):
            runtime_config.sauvegarder(
                {
                    "LLM_MODEL": modele.strip(),
                    "GROQ_VISION_MODEL": vision.strip(),
                    "LLM_TEMPERATURE": temp,
                    "LLM_TOP_P": top_p,
                    "MAX_TOKENS": int(max_tok),
                    "LLM_FREQUENCY_PENALTY": freq_p,
                    "LLM_PRESENCE_PENALTY": presence,
                    "DESACTIVER_WEB_SEARCH": "true" if web_off else "false",
                    "QUOTA_GUEST_REQ": int(q_guest),
                    "QUOTA_EMAIL_REQ": int(q_email),
                    "QUOTA_GITHUB_REQ": int(q_gh),
                }
            )
            db.audit(admin["id"], "runtime_config", "Paramètres IA mis à jour")
            st.success("Paramètres enregistrés. Redémarrez Streamlit pour appliquer aux modules déjà chargés.")
            st.rerun()

    st.json(runtime_config.charger())

# ── Module Audit ────────────────────────────────────────────────
with modules[5]:
    _entete_module("Journal des actions admin", "Historique des actions admin.", "audit")
    for a in db.lister_audit(80):
        st.markdown(
            f"`{str(a.get('cree_le') or '')[:19]}` · **{a.get('action')}** · "
            f"{a.get('details')}"
        )
