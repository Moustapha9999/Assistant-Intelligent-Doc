"""Capture live Streamlit : accueil + reponse avec sources."""
from __future__ import annotations

import sys
import time
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "docs" / "figures_chap4"
URL = "http://localhost:8501"


def main() -> int:
    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 900}, device_scale_factor=2)
        page.goto(URL, wait_until="networkidle", timeout=120_000)
        page.wait_for_timeout(2500)

        # Accueil
        accueil = OUT / "figure_4_2_accueil_live.png"
        page.screenshot(path=str(accueil), full_page=False)
        print(f"OK {accueil}")

        # Chercher la zone chat Streamlit
        selectors = [
            'textarea[data-testid="stChatInputTextArea"]',
            '[data-testid="stChatInput"] textarea',
            "textarea",
            '[contenteditable="true"]',
        ]
        box = None
        for sel in selectors:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible():
                box = loc
                break
        if box is None:
            print("INPUT introuvable — capture accueil seule")
            browser.close()
            return 1

        question = "Comment creer une API REST avec Flask en Python ?"
        box.click()
        box.fill(question)
        page.keyboard.press("Enter")
        print("Question envoyee, attente reponse...")

        # Attendre apparition sources / tokens / message assistant
        deadline = time.time() + 180
        ok = False
        while time.time() < deadline:
            content = page.content()
            if (
                "Sources" in content
                or "confiance" in content
                or "corpus" in content
                or "tokens" in content
            ):
                # laisser le rendu finir
                page.wait_for_timeout(2000)
                # ouvrir expander Sources si present
                for label in ["Sources & confiance", "Sources", "sources"]:
                    btn = page.get_by_text(label, exact=False).first
                    try:
                        if btn.count() and btn.is_visible():
                            btn.click(timeout=2000)
                            page.wait_for_timeout(800)
                            break
                    except Exception:
                        pass
                ok = True
                break
            if "Erreur" in content and "GROQ" in content.upper():
                print("Erreur Groq detectee")
                break
            page.wait_for_timeout(1500)

        reponse = OUT / "figure_4_3_reponse_sources_live.png"
        page.screenshot(path=str(reponse), full_page=False)
        print(f"OK {reponse} (sources_visibles={ok})")
        browser.close()
        return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
