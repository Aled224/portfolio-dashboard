# -*- coding: utf-8 -*-
"""Radar di news sul mercato, agganciato agli ambiti del portafoglio.

Ogni "area" corrisponde a un settore in cui l'utente ha investito (AI/Cloud,
Auto elettriche/Batterie, Mercati emergenti, Sanita', Azionario globale).
Per ciascuna area cerca SOLO notizie che siano anche eventi rilevanti per un
investimento (IPO, acquisizioni, fusioni, partnership, round, aperture, ...),
cosi' le news sono pertinenti e vicine a cio' che gia' possiede.
In piu' un'area "Grandi operazioni globali" cattura i grandi affari lontani
dai suoi settori ma comunque significativi.

Fonti: Google News RSS (aggrega centinaia di testate, italiano + inglese).
Niente social (LinkedIn/X non offrono accesso pubblico gratuito e stabile).
Niente dato personale: solo notizie pubbliche, usate come spunto.
"""
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

import requests

_UA = {"User-Agent": "Mozilla/5.0 (compatible; PortfolioRadar/1.0)"}

# Filtro "evento da investimento": una notizia entra solo se parla anche di questo.
EVENTI = ('IPO OR quotazione OR acquisizione OR fusione OR merger OR acquisition OR '
          'partnership OR "joint venture" OR "aumento di capitale" OR '
          '"round di finanziamento" OR investimento OR "nuovo stabilimento" OR '
          'buyback OR "profit warning"')

# Aree del portafoglio: (etichetta, emoji, parole-chiave del settore).
# La query finale e' (EVENTI) AND (settore): evento d'investimento DENTRO il settore.
AREE = [
    ("AI / Cloud / Chip", "🤖",
     'semiconduttori OR chip OR "intelligenza artificiale" OR AI OR '
     '"data center" OR cloud OR Nvidia OR Microsoft'),
    ("Auto elettriche / Batterie", "🔋",
     '"auto elettriche" OR "veicoli elettrici" OR batterie OR "stato solido" OR '
     'EV OR Tesla OR BYD OR litio'),
    ("Mercati emergenti", "🌏",
     'India OR Vietnam OR Sudafrica OR "mercati emergenti" OR "emerging markets"'),
    ("Sanità / Farmaceutica", "💊",
     'farmaceutica OR farmaco OR pharma OR biotech OR "casa farmaceutica" OR '
     'Roche OR FDA OR vaccino'),
    ("Azionario globale / ETF", "🌐",
     '"mercato azionario" OR ETF OR "Wall Street" OR Nasdaq OR "S&P 500" OR '
     '"indice azionario"'),
]

# Aree speciali con query completa (non combinata con EVENTI):
# grandi operazioni lontane dai suoi settori ma significative ("con un senso").
AREE_SPECIALI = [
    ("Grandi operazioni globali", "🌟",
     '"maxi acquisizione" OR "mega merger" OR "blockbuster deal" OR '
     '"biggest IPO" OR "record IPO" OR ("miliardi" (acquisizione OR fusione OR IPO))'),
]


def _parse(content):
    root = ET.fromstring(content)
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
    """Restituisce una lista di aree: {etichetta, emoji, notizie:[...]}.

    Tutte le ricerche girano in parallelo; una fonte che fallisce viene saltata.
    """
    # ogni area produce una query (settore AND evento d'investimento);
    # l'AND esplicito serve perche' Google News in inglese altrimenti "allarga"
    # ignorando il settore. Le aree speciali usano la query cosi' com'e'.
    aree = [(et, em, f'({sett}) AND ({EVENTI})') for et, em, sett in AREE]
    aree += list(AREE_SPECIALI)

    jobs = []  # (indice_area, funzione)
    for i, (_, _, query) in enumerate(aree):
        jobs.append((i, lambda q=query: _google(q, "it", "IT")))
        jobs.append((i, lambda q=query: _google(q, "en", "US")))

    secchi = {i: [] for i in range(len(aree))}
    with ThreadPoolExecutor(max_workers=8) as ex:
        esiti = list(ex.map(lambda j: (j[0], j[1]()), jobs))
    for i, notizie in esiti:
        secchi[i] += notizie

    risultato = []
    for i, (etichetta, emoji, _) in enumerate(aree):
        risultato.append({"etichetta": etichetta, "emoji": emoji,
                          "notizie": _dedup(secchi[i], per_tema)})
    return risultato
