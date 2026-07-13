# -*- coding: utf-8 -*-
"""Tiene sveglia la dashboard e controlla che sia viva.

Perche' un browser e non un semplice curl: Streamlit considera "traffico" una
sessione vera (websocket), non una richiesta HTTP secca. Qui apriamo davvero la
pagina, come farebbe una persona, e aspettiamo di vedere il campo password.

Non serve nessuna password: ci fermiamo davanti al cancello. Se l'app e'
addormentata clicchiamo il bottone di risveglio. Se non riusciamo a vederla,
usciamo con errore, cosi' il workflow diventa rosso e arriva la mail di avviso.
"""
import os
import sys

from playwright.sync_api import sync_playwright

URL = os.environ.get("APP_URL") or "https://portfolio-dashboard-ciao.streamlit.app"

# Il bottone che Streamlit mostra quando l'app e' in pausa da inattivita'.
BOTTONE_RISVEGLIO = "button:has-text('get this app back up')"
# La prova che l'app e' viva: il nostro cancello e' stato disegnato.
CANCELLO = "input[type='password']"


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        print(f"Apro {URL}")
        page.goto(URL, wait_until="domcontentloaded", timeout=60_000)

        risveglio = page.locator(BOTTONE_RISVEGLIO).first
        if risveglio.count() and risveglio.is_visible():
            print("L'app era addormentata: clicco per risvegliarla.")
            risveglio.click()

        try:
            # Il risveglio da zero puo' richiedere un paio di minuti.
            page.wait_for_selector(CANCELLO, timeout=180_000)
        except Exception:
            titolo = page.title()
            testo = page.inner_text("body")[:400].replace("\n", " | ")
            print(f"::error::App non raggiungibile. Titolo pagina: '{titolo}'. Testo: {testo}")
            print("::error::Se compare una richiesta di login, l'app e' tornata privata: "
                  "il keep-alive non puo' raggiungerla.")
            browser.close()
            return 1

        print("App sveglia: il cancello password e' visibile. Tutto a posto.")
        browser.close()
        return 0


if __name__ == "__main__":
    sys.exit(main())
