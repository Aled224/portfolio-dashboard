# -*- coding: utf-8 -*-
"""Magazzino dati condiviso.

I dati vivono in un file `data.json` dentro un repository GitHub PRIVATO.
Questo programma vi accede tramite le API di GitHub usando un token salvato
nei "secrets" di Streamlit. Qui dentro NON c'e' nessun dato personale: solo
il meccanismo di lettura/scrittura.
"""
import base64
import json
import os
import time

import requests
import streamlit as st


def _secret(key, default=None):
    try:
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return os.environ.get(key.upper(), default)


def _cfg():
    token = _secret("github_token")
    repo = _secret("github_repo")
    path = _secret("data_path", "data.json")
    branch = _secret("github_branch", "main")
    return token, repo, path, branch


def _headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


@st.cache_data(ttl=30, show_spinner=False)
def load_data():
    token, repo, path, branch = _cfg()
    if not (token and repo):
        raise RuntimeError("Configurazione mancante: imposta github_token e github_repo nei Secrets.")
    url = f"https://api.github.com/repos/{repo}/contents/{path}?ref={branch}"
    r = requests.get(url, headers=_headers(token), timeout=20)
    r.raise_for_status()
    content = base64.b64decode(r.json()["content"]).decode("utf-8")
    return json.loads(content)


def save_data(data):
    token, repo, path, branch = _cfg()
    if not (token and repo):
        raise RuntimeError("Configurazione mancante: imposta github_token e github_repo nei Secrets.")
    base = f"https://api.github.com/repos/{repo}/contents/{path}"
    content = base64.b64encode(
        json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
    ).decode("ascii")
    # GitHub ogni tanto risponde 500/502/503 per qualche minuto (successo il 07/10/2026),
    # oppure 409 se il file e' cambiato nel frattempo: riprovo da solo, rileggendo lo sha.
    for tentativo in range(4):
        g = requests.get(base + f"?ref={branch}", headers=_headers(token), timeout=20)
        sha = g.json().get("sha") if g.ok else None
        payload = {"message": "Aggiorna dati dall'app", "content": content, "branch": branch}
        if sha:
            payload["sha"] = sha
        p = requests.put(base, headers=_headers(token), json=payload, timeout=20)
        if p.ok:
            load_data.clear()
            return
        if p.status_code not in (409, 500, 502, 503, 504) or tentativo == 3:
            break
        time.sleep(2 + 3 * tentativo)
    if p.status_code >= 500:
        raise RuntimeError("GitHub, dove sono salvati i dati, in questo momento non risponde. "
                           "Non è stato salvato niente: riprova tra qualche minuto.")
    p.raise_for_status()


def refresh():
    load_data.clear()
