"""
Génère les figures UI pour le mémoire (Fig. 4.2 accueil, Fig. 4.3 réponse + sources).
Crée des pages HTML fidèles au thème AssistDoc, puis capture en PNG via Playwright.
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "figures_chap4"
LOGO = ROOT / "assets" / "assistdoc_logo.png"
REPONSES = ROOT / "resultats" / "generation" / "reponses_generees.json"


CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Source+Serif+4:wght@500;600&family=JetBrains+Mono:wght@400;500&display=swap');
:root {
  --bg: #141413; --bg-side: #1a1918; --bg-elev: #232221;
  --text: #ececec; --text-muted: #b4b4b4; --text-dim: #8a8a8a;
  --accent: #5b9fd4; --border: rgba(255,255,255,0.08);
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: Inter, system-ui, sans-serif;
  background: var(--bg); color: var(--text);
  width: 1280px; height: 800px; overflow: hidden;
  display: flex;
}
.sidebar {
  width: 260px; background: var(--bg-side);
  border-right: 1px solid var(--border);
  padding: 16px 12px; display: flex; flex-direction: column; gap: 8px;
}
.brand { display: flex; align-items: center; gap: 10px; padding: 8px 8px 16px; }
.brand img { width: 32px; height: 32px; border-radius: 9px; object-fit: cover; }
.brand span { font-size: 15px; font-weight: 600; }
.hist {
  font-size: 13px; color: var(--text-muted); padding: 9px 12px;
  border-radius: 10px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.hist.active { background: rgba(255,255,255,0.06); color: var(--text); }
.main { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.topbar {
  display: flex; justify-content: space-between; align-items: center;
  padding: 14px 28px 10px;
}
.topbar-l { font-size: 14px; font-weight: 500; }
.topbar-r { font-size: 13px; color: var(--text-dim); font-weight: 500; }
.chat { flex: 1; max-width: 720px; margin: 0 auto; width: 100%; padding: 8px 24px 120px; }
.welcome { text-align: center; padding: 90px 20px 28px; }
.welcome img {
  width: 52px; height: 52px; border-radius: 14px; margin: 0 auto 20px;
  display: block; box-shadow: 0 6px 20px rgba(0,0,0,0.28);
}
.wtitle {
  font-family: 'Source Serif 4', Georgia, serif;
  font-size: 34px; font-weight: 500; letter-spacing: -0.6px; margin-bottom: 12px;
}
.wsub { font-size: 15px; color: var(--text-muted); line-height: 1.65; margin-bottom: 28px; }
.suggestions { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; max-width: 560px; margin: 0 auto; }
.sug {
  border: 1px solid var(--border); background: rgba(255,255,255,0.03);
  color: var(--text-muted); border-radius: 12px; padding: 12px 14px;
  font-size: 13px; text-align: left;
}
.composer {
  position: absolute; left: 260px; right: 0; bottom: 28px;
  display: flex; justify-content: center; pointer-events: none;
}
.composer-inner {
  width: min(720px, calc(100% - 80px));
  background: var(--bg-elev); border: 1px solid var(--border);
  border-radius: 22px; padding: 14px 16px; color: var(--text-dim); font-size: 14px;
  display: flex; align-items: center; justify-content: space-between;
}
.composer-inner .send {
  width: 32px; height: 32px; border-radius: 50%;
  background: #3a3a38; color: #fff; display: grid; place-items: center; font-size: 14px;
}
.row { display: flex; margin: 18px 0; gap: 12px; }
.row.user { flex-direction: row-reverse; }
.avatar {
  width: 28px; height: 28px; border-radius: 50%; background: var(--bg-elev);
  flex-shrink: 0; display: grid; place-items: center; font-size: 11px; color: var(--text-dim);
}
.bubble-user {
  max-width: 520px; background: rgba(91,159,212,0.12);
  border: 1px solid rgba(91,159,212,0.22); border-radius: 16px 16px 4px 16px;
  padding: 12px 16px; font-size: 15px; font-weight: 500;
}
.bubble-ai {
  max-width: 560px; font-family: 'Source Serif 4', Georgia, serif;
  font-size: 16.5px; line-height: 1.7;
}
.bubble-ai code, .bubble-ai .mono {
  font-family: 'JetBrains Mono', monospace; font-size: 13px;
  background: #1a1918; border: 1px solid var(--border); border-radius: 8px;
  padding: 2px 6px;
}
.meta { margin-top: 12px; font-size: 12px; color: var(--text-dim); font-family: Inter, sans-serif; }
.sources {
  margin-top: 14px; border: 1px solid var(--border); border-radius: 12px;
  background: rgba(255,255,255,0.02); overflow: hidden;
}
.sources-h {
  padding: 10px 14px; font-size: 13px; font-weight: 600; color: var(--text-muted);
  border-bottom: 1px solid var(--border); background: rgba(255,255,255,0.02);
}
.src {
  padding: 10px 14px; border-bottom: 1px solid var(--border);
  display: grid; grid-template-columns: 1fr auto; gap: 8px; align-items: start;
}
.src:last-child { border-bottom: none; }
.src-title { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--accent); }
.src-excerpt { font-size: 12px; color: var(--text-muted); margin-top: 4px; line-height: 1.45; }
.badge {
  font-size: 11px; font-family: 'JetBrains Mono', monospace;
  background: rgba(91,159,212,0.15); color: var(--accent);
  border-radius: 6px; padding: 3px 8px; white-space: nowrap;
}
"""


def logo_data_uri() -> str:
    if LOGO.exists():
        b64 = base64.b64encode(LOGO.read_bytes()).decode("ascii")
        return f"data:image/png;base64,{b64}"
    return ""


def page_shell(body: str, title: str, sidebar_mode: str = "reponse") -> str:
    logo = logo_data_uri()
    img = f'<img src="{logo}" alt="AssistDoc" />' if logo else '<div class="avatar">A</div>'
    if sidebar_mode == "accueil":
        hist = """
  <div class="hist active">Nouvelle conversation</div>
  <div class="hist">Authentification JWT</div>
  <div class="hist">Hooks React</div>
"""
    else:
        hist = """
  <div class="hist">Nouvelle conversation</div>
  <div class="hist active">API REST Flask</div>
  <div class="hist">Authentification JWT</div>
  <div class="hist">Hooks React</div>
"""
    return f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8"><title>{title}</title>
<style>{CSS}</style></head>
<body>
<aside class="sidebar">
  <div class="brand">{img}<span>AssistDoc</span></div>
  {hist}
</aside>
<main class="main">
  <div class="topbar">
    <span class="topbar-l">AssistDoc ▾</span>
    <span class="topbar-r">Documentation GitHub</span>
  </div>
  {body}
</main>
</body></html>"""


def html_accueil() -> str:
    logo = logo_data_uri()
    icon = f'<img src="{logo}" alt="AssistDoc" />' if logo else ""
    body = f"""
<div class="chat">
  <div class="welcome">
    {icon}
    <div class="wtitle">Bonjour, je suis AssistDoc</div>
    <div class="wsub">Posez une question technique ou joignez un fichier<br>pour l’analyser ensemble.</div>
    <div class="suggestions">
      <div class="sug">Créer une API REST avec Flask</div>
      <div class="sug">Implémenter l'authentification JWT</div>
      <div class="sug">Comprendre les hooks React</div>
      <div class="sug">Containeriser une app avec Docker</div>
      <div class="sug">SQLAlchemy avec PostgreSQL</div>
      <div class="sug">Démarrer une API FastAPI</div>
    </div>
  </div>
</div>
<div class="composer"><div class="composer-inner">
  <span>Posez votre question…</span><span class="send">↑</span>
</div></div>
"""
    return page_shell(body, "AssistDoc — Accueil", sidebar_mode="accueil")


def html_reponse() -> str:
    data = {"question": "Comment créer une API REST avec Flask en Python ?",
            "reponse": "", "contextes": []}
    if REPONSES.exists():
        payload = json.loads(REPONSES.read_text(encoding="utf-8"))
        ex = (payload.get("donnees") or [{}])[0]
        data["question"] = ex.get("question") or data["question"]
        data["reponse"] = ex.get("reponse_generee") or ""
        data["contextes"] = ex.get("contextes") or []

    if not data["reponse"]:
        data["reponse"] = (
            "Pour créer une API REST avec Flask en Python, on définit des routes "
            "avec le décorateur <span class='mono'>@app.route()</span> et on renvoie "
            "du JSON via <span class='mono'>jsonify()</span>."
        )

    sources_html = ""
    repos = [
        ("pallets/flask", "docs/quickstart.rst", 0.92),
        ("pallets/flask", "README.md", 0.87),
        ("tiangolo/fastapi", "docs/tutorial/first-steps.md", 0.71),
    ]
    for i, (repo, path, score) in enumerate(repos):
        excerpt = ""
        if i < len(data["contextes"]):
            excerpt = data["contextes"][i][:160] + ("…" if len(data["contextes"][i]) > 160 else "")
        sources_html += f"""
        <div class="src">
          <div>
            <div class="src-title">{repo} · {path}</div>
            <div class="src-excerpt">{excerpt}</div>
          </div>
          <span class="badge">{score:.0%}</span>
        </div>"""

    # Expand sources for the figure (visible)
    body = f"""
<div class="chat" style="padding-top:28px;">
  <div class="row user">
    <div class="avatar">U</div>
    <div class="bubble-user">{data['question']}</div>
  </div>
  <div class="row">
    <div class="avatar">A</div>
    <div>
      <div class="bubble-ai">{data['reponse']}</div>
      <div class="meta">500 tokens · mode technique · corpus 3 · confiance 83%</div>
      <div class="sources">
        <div class="sources-h">Sources & confiance</div>
        {sources_html}
      </div>
    </div>
  </div>
</div>
"""
    return page_shell(body, "AssistDoc — Réponse avec sources")


def capture_with_playwright(html_path: Path, png_path: Path) -> None:
    from playwright.sync_api import sync_playwright

    uri = html_path.resolve().as_uri()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 800}, device_scale_factor=2)
        page.goto(uri, wait_until="networkidle")
        page.wait_for_timeout(800)
        page.screenshot(path=str(png_path), full_page=False)
        browser.close()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    accueil = OUT / "figure_4_2_accueil.html"
    reponse = OUT / "figure_4_3_reponse_sources.html"
    accueil.write_text(html_accueil(), encoding="utf-8")
    reponse.write_text(html_reponse(), encoding="utf-8")
    print(f"HTML ecrits -> {OUT}")

    try:
        capture_with_playwright(accueil, OUT / "figure_4_2_accueil.png")
        capture_with_playwright(reponse, OUT / "figure_4_3_reponse_sources.png")
    except Exception as exc:
        print(f"Playwright indisponible ({exc}). Installation...")
        import subprocess

        subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright", "-q"])
        subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])
        capture_with_playwright(accueil, OUT / "figure_4_2_accueil.png")
        capture_with_playwright(reponse, OUT / "figure_4_3_reponse_sources.png")

    print("PNG :")
    print(f"  - {OUT / 'figure_4_2_accueil.png'}")
    print(f"  - {OUT / 'figure_4_3_reponse_sources.png'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
