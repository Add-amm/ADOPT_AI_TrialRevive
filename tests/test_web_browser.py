"""Parcours du front réel dans Chromium, avec Internet bloqué.

Installer playwright pour exécuter ce contrôle supplémentaire.
Utilise Chromium système ou TRIALREVIVE_CHROMIUM si précisé.
"""
import json
import os
import shutil
from pathlib import Path
from urllib.parse import urlsplit

import pytest

pw = pytest.importorskip("playwright.sync_api")

import server
from frontend_matcher import BackendFrontendService
from tests.test_frontend_matcher import rich_fiches
from tests.test_web_api import running_app


def test_demo_to_dossier_comparison_and_safe_dom_without_internet(tmp_path, rich_fiches):
    executable = os.environ.get("TRIALREVIVE_CHROMIUM") or shutil.which("chromium") or shutil.which("google-chrome")
    if not executable:
        pytest.skip("Chromium absent ; renseigner TRIALREVIVE_CHROMIUM")
    errors, external, requested = [], [], []
    service = BackendFrontendService(fiches=rich_fiches)
    example = service.info()["exemple"]
    with running_app(server.create_app(baseline_dir=tmp_path / "baselines", service=service)) as base, pw.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=executable, headless=True,
                                    args=["--no-sandbox", "--disable-dev-shm-usage", "--use-angle=swiftshader",
                                          "--enable-unsafe-swiftshader"])
        context = browser.new_context(viewport={"width": 1440, "height": 1000})

        def local_only(route):
            url = route.request.url
            requested.append(url)
            if urlsplit(url).netloc == urlsplit(base).netloc:
                route.continue_()
            else:
                external.append(url)
                route.abort()
        context.route("**/*", local_only)
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base)
        pw.expect(page.get_by_role("heading", level=1)).to_contain_text("Trouvez les essais")
        # Le « Cas de démo » de la page d'accueil est une proposition de question.
        page.get_by_role("option").filter(has_text="Cas de démo").click()
        pw.expect(page).to_have_url(base + "/#/apercu")
        pw.expect(page.get_by_role("region", name="Chiffres clés").locator(".rpanel").first.locator(".v")).to_have_text("11")
        for label, heading in (("Essais retenus", "Essais retenus"), ("Essais écartés", "Essais écartés"),
                               ("À compléter", "À compléter"), ("En cours", "En cours"),
                               ("Patients", "Patients de l'essai interne"), ("Dossier", "Dossier de faisabilité")):
            page.get_by_role("navigation").get_by_role("link", name=label).click()
            pw.expect(page.locator("#main h2")).to_have_text(heading)
            if label == "Essais retenus":
                pw.expect(page.locator("#main")).to_contain_text("FICTIF-INT-01")
                page.locator("#main tbody tr").first.click()
                pw.expect(page.locator("#drawer")).to_be_visible()
                page.get_by_role("button", name="Fermer le détail").click()
            elif label == "À compléter":
                pw.expect(page.locator("#main")).to_contain_text("FICTIF-A-COMPLETER")
                page.locator("#main tbody tr").first.click()
                pw.expect(page.locator("#drawer")).to_contain_text("effectif_randomise")
                page.get_by_role("button", name="Fermer le détail").click()
            elif label == "En cours":
                pw.expect(page.locator("#main")).to_contain_text("FICTIF-EN-COURS")
            elif label == "Patients":
                pw.expect(page.locator("#main .hero-num")).to_contain_text("Non calculé")
                pw.expect(page.locator("#main")).to_contain_text("206 événements nécessaires au total")
        with page.expect_download() as download:
            page.get_by_role("link", name="Télécharger en Markdown").click()
        markdown = Path(download.value.path()).read_text(encoding="utf-8")
        assert "Dossier de faisabilité" in markdown and "206 événements nécessaires au total" in markdown
        assert "FICTIF-A-COMPLETER" in markdown and "FICTIF-EN-COURS" in markdown and "252" not in markdown
        artifact = Path(__file__).resolve().parent.parent / "outputs" / "front" / "dossier.png"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(artifact), full_page=True)

        # Le front ne doit pas exécuter une réponse IA contenant du balisage.
        record = {"question": example, "modele": "Fixture navigateur, pas une vraie évaluation",
                  "date": "2026-11-14", "reponse_ia": '<img src="https://example.invalid/pixel" onerror="window.injected=true"> NCT00364013'}
        page.get_by_role("navigation").get_by_role("link", name="Comparaison IA").click()
        pw.expect(page.get_by_text("Aucune réponse d'IA enregistrée", exact=True)).to_be_visible()
        page.locator("#importFile").set_input_files({"name": "fixture.json", "mimeType": "application/json",
                                                   "buffer": json.dumps(record).encode("utf-8")})
        pw.expect(page.get_by_role("textbox", name="Réponse brute de l'IA")).to_have_value(record["reponse_ia"])
        assert page.evaluate("window.injected") is None
        assert page.locator('img[src*="example.invalid"]').count() == 0
        page.get_by_role("button", name="Archiver cette réponse localement").click()
        pw.expect(page.get_by_role("status")).to_contain_text("Réponse archivée localement")
        archived = list((tmp_path / "baselines").glob("*.json"))
        assert len(archived) == 1 and json.loads(archived[0].read_text()) == record

        # Erreurs utilisateur et traitement sans bras interne : pas de crash du front.
        page.locator("#qCompact").fill("Le statut NRAS change-t-il l'effet du panitumumab ?")
        page.get_by_role("button", name="Analyser", exact=True).click()
        pw.expect(page.get_by_role("alert")).to_contain_text("SEH structurée")
        page.get_by_role("button", name="Cas de démo", exact=True).click()
        pw.expect(page).to_have_url(base + "/#/apercu")
        page.get_by_role("navigation").get_by_role("link", name="Comment ça marche").click()
        pw.expect(page.locator("#main")).to_contain_text("comptage individuel S0 à S4 n'est pas encore calculé")
        assert not errors, errors
        assert not external, external
        assert any("/assets/fonts/" in url for url in requested)
        assert any("/assets/brand/TrialRevive_logo_horizontal_noir.svg" in url for url in requested)
        assert not any("three.min.js" in url for url in requested)
        context.close()
        browser.close()


@pytest.mark.parametrize("width,height", [(390, 844), (820, 1180)])
def test_every_navigation_tab_is_reachable_on_mobile_and_tablet(tmp_path, width, height):
    executable = os.environ.get("TRIALREVIVE_CHROMIUM") or shutil.which("chromium") or shutil.which("google-chrome")
    if not executable:
        pytest.skip("Chromium absent ; renseigner TRIALREVIVE_CHROMIUM")
    from frontend_matcher import BACKEND

    service = BackendFrontendService(fiches=BACKEND / "data/fiches_essais_fictives.json")
    with running_app(server.create_app(service=service, baseline_dir=tmp_path)) as base, pw.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=executable, headless=True,
                                    args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = browser.new_page(viewport={"width": width, "height": height}, reduced_motion="reduce")
        page.goto(base)
        page.get_by_role("option").first.click()
        pw.expect(page).to_have_url(base + "/#/apercu")
        for route in ("apercu", "essais", "ecartes", "completer", "encours", "patients", "dossier", "comparaison", "guide"):
            tab = page.locator(f'#nav a[href="#/{route}"]')
            tab.click()
            pw.expect(page).to_have_url(base + "/#/" + route)
            pw.expect(tab).to_be_in_viewport()
        if width == 390:
            assert page.locator(".rail").evaluate("el => el.scrollLeft") > 0
        dimensions = page.evaluate("() => ({content: document.documentElement.scrollWidth, viewport: innerWidth})")
        assert dimensions["content"] <= dimensions["viewport"] + 2
        browser.close()
