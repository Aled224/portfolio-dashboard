# -*- coding: utf-8 -*-
"""Radar di news sul mercato per la dashboard.

Raccoglie notizie pubbliche da piu' fonti gratuite e affidabili:
- Google News (aggrega centinaia di testate: Sole 24 Ore, Reuters, Bloomberg,
  Milano Finanza, ecc.), su molti temi che muovono o possono muovere i corsi;
- feed RSS diretti di siti finanziari (MarketWatch), per un flusso "dai mercati".

Niente social (LinkedIn/X non offrono accesso pubblico gratuito e stabile).
Niente dato personale: sono solo notizie pubbliche, usate come spunto.
Le richieste vengono fatte in parallelo per restare veloci anche con molti temi.
"""
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

import requests

_UA = {"User-Agent": "Mozilla/5.0 (compatible; PortfolioRadar/1.0)"}

# Temi cercati su Google News: (etichetta, emoji, query).
# L'idea: tutto cio' che muove (o potrebbe muovere) il valore di un titolo.
TEMI_QUERY = [
    ("IPO / Quotazioni", "🆕",
     'IPO OR "quotazione in borsa" OR collocamento OR "debutto in borsa"'),
    ("Acquisizioni / Fusioni", "🤝",
     'acquisizione OR fusione OR "merger" OR "takeover" OR "rileva"'),
    ("OPA / Vendite", "💸",
     '"OPA" OR "offerta pubblica di acquisto" OR "cede quota" OR '
     '"cede partecipazione" OR "vende la divisione" OR "cessione partecipazione"'),
    ("Partnership / Accordi", "🔗",
     '"partnership" OR "accordo strategico" OR "joint venture" OR alleanza OR '
     '"collaborazione" azienda OR "sigla un accordo"'),
    ("Espansione / Nuove aperture", "🌍",
     '"nuovo stabilimento" OR "nuova fabbrica" OR "nuova sede" OR '
     '"apre un nuovo" OR "entra nel mercato" OR "espansione" azienda'),
    ("Trimestrali / Utili", "📊",
     '"conti trimestrali" OR trimestrale OR utili OR "profit warning" OR earnings'),
    ("Lanci / Innovazione", "💡",
     '"lancia il nuovo" OR "nuovo prodotto" OR "presenta il nuovo" OR '
     'brevetto OR "via libera" OR approvazione FDA'),
    ("Startup / Nuovi round", "🚀",
     '"round di finanziamento" OR "funding round" OR "aumento di capitale" OR '
     '"startup raccoglie" OR "raccoglie" investimento'),
    ("Dividendi / Buyback", "💰",
     'dividendo OR "buyback" OR "riacquisto di azioni" OR cedola OR "stacco cedola"'),
    ("Rating analisti", "🎯",
     '"alza il target" OR "taglia il target" OR upgrade OR downgrade OR '
     '"raccomandazione" analisti OR "rating" azione'),
]

# Feed RSS diretti, raggruppati nel tema "Dai mercati": (etichetta_fonte, url)
FEED_DIRETTI = [
    ("MarketWatch", "http://feeds.marketwatch.com/marketwatch/topstories/"),
    ("MarketWatch (real-time)", "http://feeds.marketwatch.com/marketwatch/realtimeheadlines/"),
]


def _parse(content, fonte_default=""):
    """Estrae le voci da un XML RSS (Google News o feed standard)."""
    root = ET.fromstring(content)
    out = []
    for item in root.iter("item"):
        titolo = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not titolo or not link:
            continue
        src_el = item.find("source")
        fonte = (src_el.text.strip() if src_el is not None and src_el.text
                 else fonte_default)
        pub = item.findtext("pubDate") or ""
        try:
            dt = parsedate_to_datetime(pub)
            ts, data_it = dt.timestamp(), dt.strftime("%d/%m/%Y")
        except Exception:
            ts, data_it = 0, ""
        out.append({"titolo": titolo, "link": link, "fonte": fonte,
                    "data": data_it, "ts": ts})
    return out


def _google(query, lingua, paese):
    ceid = f"{paese}:{lingua}"
    url = ("https://news.google.com/rss/search"
           f"?q={urllib.parse.quote(query)}"
           f"&hl={lingua}&gl={paese}&ceid={urllib.parse.quote(ceid)}")
    try:
        r = requests.get(url, headers=_UA, timeout=20)
        r.raise_for_status()
        return _parse(r.content)
    except Exception:
        return []


def _diretto(fonte, url):
    try:
        r = requests.get(url, headers=_UA, timeout=20)
        r.raise_for_status()
        return _parse(r.content, fonte_default=fonte)
    except Exception:
        return []


def _dedup(notizie, limite):
    viste, uniche = set(), []
    for n in sorted(notizie, key=lambda x: x["ts"], reverse=True):
        chiave = n["titolo"].lower()[:60]
        if chiave in viste:
            continue
        viste.add(chiave)
        uniche.append(n)
    return uniche[:limite]


def market_news(per_tema=5):
    """Restituisce una lista di temi: {etichetta, emoji, notizie:[...]}.

    Tutte le fonti vengono interrogate in parallelo; una fonte che fallisce
    viene semplicemente saltata (mai solleva eccezioni).
    """
    # prepara i job: ogni tema -> ricerca italiana + inglese
    jobs = []  # (indice_tema, funzione)
    for i, (_, _, query) in enumerate(TEMI_QUERY):
        jobs.append((i, lambda q=query: _google(q, "it", "IT")))
        jobs.append((i, lambda q=query: _google(q, "en", "US")))
    idx_mercati = len(TEMI_QUERY)
    for fonte, url in FEED_DIRETTI:
        jobs.append((idx_mercati, lambda f=fonte, u=url: _diretto(f, u)))

    secchi = {i: [] for i in range(idx_mercati + 1)}
    with ThreadPoolExecutor(max_workers=8) as ex:
        esiti = list(ex.map(lambda j: (j[0], j[1]()), jobs))
    for i, notizie in esiti:
        secchi[i] += notizie

    risultato = []
    for i, (etichetta, emoji, _) in enumerate(TEMI_QUERY):
        risultato.append({"etichetta": etichetta, "emoji": emoji,
                          "notizie": _dedup(secchi[i], per_tema)})
    risultato.append({"etichetta": "Dai mercati (live)", "emoji": "📰",
                      "notizie": _dedup(secchi[idx_mercati], per_tema)})
    return risultato
