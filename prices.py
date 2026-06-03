# -*- coding: utf-8 -*-
"""Logica di aggiornamento prezzi (condivisa tra l'app e il robottino).

Recupera i prezzi da Yahoo Finance, converte in EUR e aggiorna i valori
dentro la struttura `data`. Nessun dato personale qui dentro: la lista dei
titoli arriva sempre da `data["holdings"]`.
"""
import datetime
import json
import urllib.request


def yahoo(sym, rng="3mo"):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range={rng}&interval=1d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    d = json.loads(urllib.request.urlopen(req, timeout=25).read())
    r = d["chart"]["result"][0]
    cur = r["meta"].get("currency")
    now = r["meta"].get("regularMarketPrice")
    closes = {}
    ts = r.get("timestamp", []) or []
    cl = r["indicators"]["quote"][0].get("close", []) or []
    for t, c in zip(ts, cl):
        if c is not None:
            day = datetime.datetime.utcfromtimestamp(t).strftime("%Y-%m-%d")
            closes[day] = c
    return cur, now, closes


def fx_to_eur(ccy, rng="3mo"):
    if ccy == "EUR":
        return 1.0, {}
    try:
        _, now, closes = yahoo(f"{ccy}EUR=X", rng)
        if now:
            return now, closes
    except Exception:
        pass
    _, now2, closes2 = yahoo(f"EUR{ccy}=X", rng)
    inv = {d: (1.0 / v) for d, v in closes2.items() if v}
    return (1.0 / now2 if now2 else None), inv


def pac_val(pac, hid, iniziale, current):
    items = pac.get(hid)
    if not items:
        return 0.0
    if isinstance(items, (int, float)):
        return float(items)
    idx_now = (current[hid] / iniziale) if (hid in current and iniziale) else 1.0
    return sum(float(t.get("a", 0)) * (idx_now / (t.get("idx", 1) or 1)) for t in items)


def asset_value_history(h, baseline_price, rng="1mo"):
    """Storico reale (da Yahoo) del VALORE della posizione iniziale nel titolo.

    valore(t) = iniziale * (prezzo_in_eur(t) / prezzo_in_eur_al_29/05).
    Ritorna una lista di {date, value} ordinata per data.
    """
    sym, ccy, iniziale = h["sym"], h["ccy"], h["iniziale"]
    _, _, closes = yahoo(sym, rng)
    fx = {}
    if ccy != "EUR":
        _, fx = fx_to_eur(ccy, rng)
    fx_items = sorted(fx.items())

    def fx_at(day):
        if ccy == "EUR":
            return 1.0
        if day in fx:
            return fx[day]
        last = None
        for d, r in fx_items:
            if d <= day:
                last = r
            else:
                break
        return last if last is not None else (fx_items[0][1] if fx_items else 1.0)

    out = []
    if not baseline_price:
        return out
    for day in sorted(closes):
        p_eur = closes[day] * fx_at(day)
        out.append({"date": day, "value": round(iniziale * (p_eur / baseline_price), 2)})
    return out


def update_prices_in_data(data, log=print):
    """Aggiorna current / baseline_prices / history / last_update dentro `data`.

    Ritorna (data, riepilogo_valori). Non scrive niente su disco: pensa il
    chiamante a salvare.
    """
    base_date = data.get("base_date", "2026-05-29")
    holdings = data.get("holdings", [])
    baseline = data.get("baseline_prices", {})
    current_saved = data.get("current", {})
    pac = data.get("pac", {})
    today = datetime.date.today().isoformat()

    fx_now, fx_base = {}, {}
    for ccy in set(h["ccy"] for h in holdings):
        if ccy == "EUR":
            fx_now[ccy], fx_base[ccy] = 1.0, 1.0
            continue
        n, closes = fx_to_eur(ccy, rng="3mo")
        fx_now[ccy] = n
        fx_base[ccy] = closes.get(base_date) or n

    current = {}
    for h in holdings:
        hid, sym, ccy, iniziale = h["id"], h["sym"], h["ccy"], h["iniziale"]
        try:
            cur, now, closes = yahoo(sym, rng="3mo")
            now_eur = now * fx_now[ccy]
            if hid not in baseline or not baseline[hid]:
                c29 = closes.get(base_date)
                baseline[hid] = (c29 * fx_base[ccy]) if c29 else now_eur
            value = iniziale * (now_eur / baseline[hid])
            current[hid] = round(value, 2)
            log(f"OK  {h['nome']:20s} {sym:9s} -> EUR {current[hid]}  ({(value/iniziale-1)*100:+.1f}%)")
        except Exception as e:
            current[hid] = current_saved.get(hid, iniziale)
            log(f"ERRORE {h['nome']} ({sym}): {repr(e)[:80]} -> uso ultimo valore {current[hid]}")

    add_tot = sum(pac_val(pac, h["id"], h["iniziale"], current) for h in holdings)
    total = round(sum(current.values()) + add_tot)
    vals = {h["id"]: round(current.get(h["id"], h["iniziale"]) + pac_val(pac, h["id"], h["iniziale"], current))
            for h in holdings}

    hist = data.get("history", [])
    if not any(e["date"] == base_date for e in hist):
        hist.insert(0, {"date": base_date, "total": sum(h["iniziale"] for h in holdings),
                        "vals": {h["id"]: h["iniziale"] for h in holdings}})
    hist = [e for e in hist if e["date"] != today]
    if today != base_date:
        hist.append({"date": today, "total": total, "vals": vals})
    hist.sort(key=lambda e: e["date"])

    data["baseline_prices"] = baseline
    data["current"] = current
    data["history"] = hist
    data["last_update"] = today
    return data, {"total": total, "add_tot": add_tot, "today": today}
