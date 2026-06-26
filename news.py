# -*- coding: utf-8 -*-
"""Radar di news sul mercato (IPO, acquisizioni/fusioni, OPA/vendite).

Legge i feed RSS di Google News (gratis, nessuna chiave) e restituisce una
lista di notizie con titolo, fonte, data, link alla notizia originale e un
link di ricerca del possibile ticker. NIENTE dato personale qui dentro:
sono solo notizie pubbliche, usate come spunto, non come consiglio.
"""
import urllib.parse
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

import requests

# Temi monitorati: (etichetta, emoji, query Google News)
TEMI = [
    ("IPO / Quotazioni", "🆕",
     'IPO OR "quotazione in borsa" OR collocamento OR "debutto in borsa"'),
    ("Acquisizioni / Fusioni", "🤝",
     'acquisizione OR fusione OR "merger" OR "takeover" OR "rileva"'),
    ("OPA / Vendite", "💸",
     '"OPA" OR "offerta pubblica di acquisto" OR "cede quota" OR '
     '"cede partecipazione" OR "vende la divisione" OR "cessione partecipazione"'),
]

_STOP = {"la", "il", "lo", "le", "i", "gli", "un", "una", "di", "del", "della",
         "dei", "delle", "in", "su", "con", "per", "the", "a", "of", "to", "and"}


def _yahoo_lookup(titolo):
    """Costruisce un link di ricerca ticker su Yahoo Finance a partire dal titolo."""
    testo = titolo.split(" - ")[0]
    parole = [p for p in testo.replace(",", " ").split()
              if p.lower() not in _STOP and len(p) > 2]
    query = " ".join(parole[:4]) or testo
    return "https://finance.yahoo.com/lookup/?s=" + urllib.parse.quote(query)


def _feed(query, lingua="it", paese="IT", limite=6):
    base = "https://news.google.com/rss/search"
    ceid = f"{paese}:{lingua}"
    url = (f"{base}?q={urllib.parse.quote(query)}"
           f"&hl={lingua}&gl={paese}&ceid={urllib.parse.quote(ceid)}")
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    out = []
    for item in root.iter("item"):
        titolo = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not titolo or not link:
            continue
        src_el = item.find("source")
        fonte = (src_el.text.strip() if src_el is not None and src_el.text else "")
        pub = item.findtext("pubDate") or ""
        try:
            dt = parsedate_to_datetime(pub)
            ts = dt.timestamp()
            data_it = dt.strftime("%d/%m/%Y")
        except Exception:
            ts, data_it = 0, ""
        out.append({"titolo": titolo, "link": link, "fonte": fonte,
                    "data": data_it, "ts": ts, "ticker": _yahoo_lookup(titolo)})
        if len(out) >= limite:
            break
    return out


def market_news(per_tema=5):
    """Restituisce {etichetta_tema: [notizie...]} per ogni tema monitorato.

    Mescola feed in italiano e in inglese per coprire anche i mercati esteri.
    Non solleva eccezioni: se un feed fallisce, quel tema resta (eventualmente) vuoto.
    """
    risultato = []
    for etichetta, emoji, query in TEMI:
        notizie = []
        for lingua, paese in (("it", "IT"), ("en", "US")):
            try:
                notizie += _feed(query, lingua, paese, limite=per_tema + 2)
            except Exception:
                continue
        # dedup per titolo, piu' recenti prima
        viste, uniche = set(), []
        for n in sorted(notizie, key=lambda x: x["ts"], reverse=True):
            chiave = n["titolo"].lower()[:60]
            if chiave in viste:
                continue
            viste.add(chiave)
            uniche.append(n)
        risultato.append({"etichetta": etichetta, "emoji": emoji,
                          "notizie": uniche[:per_tema]})
    return risultato
