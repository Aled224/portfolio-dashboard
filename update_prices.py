# -*- coding: utf-8 -*-
"""Robottino: aggiorna i prezzi nel repo PRIVATO dei dati e manda l'email recap.

Gira su GitHub Actions. Legge data.json dal repository privato via API,
aggiorna i prezzi (prices.py), riscrive il file e invia l'email.
Nessun dato personale e' presente in questo file: arriva tutto da data.json.

Variabili d'ambiente richieste:
  DATA_TOKEN  - token con accesso (Contents read/write) al repo privato dei dati
  DATA_REPO   - es. "utente/personal-dashboard"
  DATA_PATH   - di solito "data.json"
  DATA_BRANCH - di solito "main"
Facoltative (per l'email):
  EMAIL_USER, EMAIL_APP_PASSWORD, EMAIL_TO, APP_URL
"""
import base64
import json
import os

import requests

import prices


def log(msg):
    try:
        print(msg)
    except Exception:
        print(str(msg).encode("ascii", "replace").decode("ascii"))


def _headers():
    return {
        "Authorization": f"Bearer {os.environ['DATA_TOKEN']}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _repo():
    return os.environ["DATA_REPO"], os.environ.get("DATA_PATH", "data.json"), os.environ.get("DATA_BRANCH", "main")


def load_data():
    repo, path, branch = _repo()
    url = f"https://api.github.com/repos/{repo}/contents/{path}?ref={branch}"
    r = requests.get(url, headers=_headers(), timeout=25)
    r.raise_for_status()
    j = r.json()
    content = base64.b64decode(j["content"]).decode("utf-8")
    return json.loads(content), j["sha"]


def save_data(data, sha):
    repo, path, branch = _repo()
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    payload = {
        "message": "Aggiornamento prezzi settimanale",
        "content": base64.b64encode(json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")).decode("ascii"),
        "branch": branch,
        "sha": sha,
    }
    r = requests.put(url, headers=_headers(), json=payload, timeout=25)
    r.raise_for_status()


def _eur(x):
    return "€ " + f"{int(round(x)):,}".replace(",", ".")


def _pct(p):
    return f"{p:+.1f}".replace(".", ",") + "%"


def itdate(iso):
    try:
        y, m, d = str(iso).split("-")
        return f"{d}/{m}/{y}"
    except Exception:
        return str(iso)


def build_recap(data, info):
    holdings = data.get("holdings", [])
    names = {h["id"]: h["nome"] for h in holdings}
    iniz = {h["id"]: h["iniziale"] for h in holdings}
    current = data.get("current", {})
    hist = data.get("history", [])
    pac = data.get("pac", {})
    total = info["total"]
    today = info["today"]
    base = hist[0] if hist else None
    prev = hist[-2] if len(hist) >= 2 else None
    L = []
    L.append(f"📅 Aggiornamento al {itdate(today)}")
    parts = []
    if prev:
        d = total - prev["total"]
        parts.append(f"{_eur(d)} / {_pct((d/prev['total']*100) if prev['total'] else 0)} dall'ultima volta")
    if base:
        d = total - base["total"]
        parts.append(f"{_eur(d)} / {_pct((d/base['total']*100) if base['total'] else 0)} dall'inizio")
    L.append(f"💼 Valore totale: {_eur(total)}" + (f"  ({' · '.join(parts)})" if parts else ""))
    perf = [(names[h["id"]], current[h["id"]] / iniz[h["id"]] - 1)
            for h in holdings if h["id"] in current and iniz[h["id"]]]
    good = sorted([p for p in perf if p[1] > 0], key=lambda x: -x[1])
    bad = sorted([p for p in perf if p[1] < 0], key=lambda x: x[1])
    if good:
        L.append("✅ Vanno bene: " + " · ".join(f"{n} {_pct(c*100)}" for n, c in good))
    if bad:
        L.append("🔻 In difficoltà: " + " · ".join(f"{n} {_pct(c*100)}" for n, c in bad))
    if info.get("add_tot", 0) > 0:
        L.append(f"💰 Versamenti inclusi: {_eur(info['add_tot'])}")
    return L


def send_email(recap_lines, today):
    user = os.environ.get("EMAIL_USER")
    pwd = os.environ.get("EMAIL_APP_PASSWORD")
    to = os.environ.get("EMAIL_TO")
    if not (user and pwd and to):
        log("Email: variabili non configurate, salto invio.")
        return
    import smtplib
    import ssl
    from email.message import EmailMessage
    msg = EmailMessage()
    msg["Subject"] = f"📊 REPORT PORTAFOGLIO — {itdate(today)}"
    msg["From"] = user
    msg["To"] = to
    body = "Report del portafoglio:\n\n" + "\n".join(recap_lines)
    if os.environ.get("APP_URL"):
        body += f"\n\n🔗 Apri la dashboard: {os.environ['APP_URL']}\n"
    msg.set_content(body)
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context()) as s:
            s.login(user, pwd)
            s.send_message(msg)
        log("Email inviata a " + to)
    except Exception as e:
        log("Email errore: " + repr(e)[:150])


def main():
    data, sha = load_data()
    data, info = prices.update_prices_in_data(data, log=log)
    cinfo = None
    if isinstance(data.get("crypto"), dict) and data["crypto"].get("holdings"):
        try:
            data["crypto"], cinfo = prices.update_prices_in_data(data["crypto"], log=log)
        except Exception as e:
            log("Cripto: aggiornamento non riuscito: " + repr(e)[:120])
    save_data(data, sha)
    log(f"Totale: {_eur(info['total'])} (al {itdate(info['today'])})")
    recap = build_recap(data, info)
    if cinfo:
        recap.append(f"🪙 Cripto: {_eur(cinfo['total'])}")
    for r in recap:
        log("RECAP • " + r)
    send_email(recap, info["today"])
    log("Fatto.")


if __name__ == "__main__":
    main()
