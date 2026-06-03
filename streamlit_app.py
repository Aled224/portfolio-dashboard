# -*- coding: utf-8 -*-
"""Dashboard portafoglio (Streamlit), condivisa e privata.

Accesso protetto da password. Tutti i dati personali (titoli, importi, storico)
vivono in un repository GitHub PRIVATO e sono letti tramite una chiave segreta.
In questo file NON c'e' nessun dato personale: solo il programma generico.
"""
import datetime
import os

import pandas as pd
import streamlit as st

from github_store import load_data, save_data, refresh
import prices

st.set_page_config(page_title="Portafoglio", page_icon="📊", layout="wide")

PALETTE = ["#3b82f6", "#a78bfa", "#22d3ee", "#fb923c", "#34d399",
           "#f472b6", "#facc15", "#f87171", "#38bdf8", "#c084fc"]
GREEN, RED, MUTED, LINE, GOLD = "#2ecc71", "#ff5d6c", "#9aa0d0", "#2b3168", "#ffcf5c"


# --------------------------------------------------------------- formattazione
def eur(n):
    return "–" if n is None else "€ " + f"{round(n):,}".replace(",", ".")


def pct(n):
    return "–" if n is None else f"{n:+.1f}".replace(".", ",") + "%"


def num1(n):
    return f"{n:.1f}".replace(".", ",")


def itdate(iso):
    try:
        y, m, d = str(iso).split("-")
        return f"{d}/{m}/{y}"
    except Exception:
        return str(iso)


def vspan(v):
    c = GREEN if v >= 0 else RED
    return f"<span style='color:{c};font-weight:600'>{pct(v)}</span>"


def next_monday(iso):
    try:
        d = datetime.date.fromisoformat(iso)
        ahead = (0 - d.weekday()) % 7
        ahead = 7 if ahead == 0 else ahead
        return (d + datetime.timedelta(days=ahead)).isoformat()
    except Exception:
        return ""


# ----------------------------------------------------------------------- login
def _password():
    try:
        if "app_password" in st.secrets:
            return st.secrets["app_password"]
    except Exception:
        pass
    return os.environ.get("APP_PASSWORD", "")


def check_password():
    def _entered():
        st.session_state["authed"] = (st.session_state.get("pwd_input", "") == str(_password()))
        st.session_state["bad_pwd"] = not st.session_state["authed"]
        st.session_state.pop("pwd_input", None)

    if st.session_state.get("authed"):
        return True
    st.title("📊 Portafoglio")
    st.write("Accesso privato. Inserisci la password per continuare.")
    st.text_input("Password", type="password", key="pwd_input", on_change=_entered)
    if st.session_state.get("bad_pwd"):
        st.error("Password errata. Riprova.")
    return False


if not check_password():
    st.stop()


# --------------------------------------------------------------------- calcoli
def by_id(holdings, hid):
    for h in holdings:
        if h["id"] == hid:
            return h
    return None


def cat_colors(holdings):
    cats = []
    for h in holdings:
        if h["cat"] not in cats:
            cats.append(h["cat"])
    return {c: PALETTE[i % len(PALETTE)] for i, c in enumerate(cats)}


def compute(data):
    holdings = data.get("holdings", [])
    current = data.get("current", {})
    pac = data.get("pac", {})
    rows = []
    tot_iniz = tot_add = tot_init = tot_now = 0.0
    for h in holdings:
        hid, iniz = h["id"], h["iniziale"]
        valnow = float(current.get(hid, iniz))
        idxnow = (valnow / iniz) if iniz else 1.0
        tranches = pac.get(hid) or []
        if not isinstance(tranches, list):
            tranches = []
        addcost = sum(float(t.get("a", 0)) for t in tranches)
        addvalue = sum(float(t.get("a", 0)) * (idxnow / (t.get("idx", 1) or 1)) for t in tranches)
        invtot = iniz + addcost
        valtot = valnow + addvalue
        chg = (valtot - invtot) / invtot * 100 if invtot else 0.0
        rows.append({"id": hid, "Titolo": h["nome"], "Categoria": h["cat"],
                     "iniziale": iniz, "aggiunte": addcost, "investito": invtot,
                     "valore": valtot, "var": chg, "n_tranche": len(tranches)})
        tot_iniz += iniz
        tot_add += addcost
        tot_init += invtot
        tot_now += valtot
    pl = tot_now - tot_init
    plpct = (pl / tot_init * 100) if tot_init else 0.0
    return rows, {"iniz": tot_iniz, "add": tot_add, "init": tot_init,
                  "now": tot_now, "pl": pl, "plpct": plpct}


try:
    data = load_data()
except Exception as e:
    st.error(f"Non riesco a leggere i dati. Controlla i Secrets (github_token, github_repo). Dettaglio: {e}")
    st.stop()

holdings = data.get("holdings", [])
cat_target = data.get("cat_target", {})
colors = cat_colors(holdings)
rows, totals = compute(data)
last_update = data.get("last_update", "")
base_date = data.get("base_date", "2026-05-29")

st.markdown("""
<style>
.ptbl{width:100%;border-collapse:collapse;font-size:14px;margin-top:4px}
.ptbl th{color:#9aa0d0;text-align:right;padding:9px 8px;font-size:11px;text-transform:uppercase;letter-spacing:.4px;border-bottom:1px solid #2b3168}
.ptbl td{text-align:right;padding:9px 8px;border-bottom:1px solid #2b3168}
.ptbl th:first-child,.ptbl td:first-child{text-align:left}
.ptbl tr.tot td{font-weight:700;border-top:2px solid #2b3168;border-bottom:none}
.pill{display:inline-block;padding:2px 9px;border-radius:999px;font-size:11px;font-weight:700}
.autobar{display:inline-block;background:#1c2046;border:1px solid #2b3168;border-radius:999px;padding:6px 14px;font-size:12.5px;color:#9aa0d0;margin:2px 0 6px}
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------------------------- intestazione
top = st.columns([5, 1.2])
with top[0]:
    st.title("📊 Il mio portafoglio")
    nm = next_monday(last_update)
    st.markdown(
        f"<div class='autobar'>📅 Investimento iniziale del <b>{itdate(base_date)}</b> · "
        f"prezzi al <b>{itdate(last_update)}</b> · aggiornamento automatico ogni lunedì"
        + (f" · prossimo <b>{itdate(nm)}</b>" if nm else "") + "</div>",
        unsafe_allow_html=True)
with top[1]:
    st.write("")
    if st.button("📈 Aggiorna prezzi", use_container_width=True, type="primary",
                 help="Scarica subito i prezzi di mercato aggiornati"):
        with st.spinner("Scarico i prezzi di mercato..."):
            try:
                fresh = load_data()
                fresh, _info = prices.update_prices_in_data(fresh, log=lambda *_: None)
                save_data(fresh)
                refresh()
                st.success("Prezzi aggiornati!")
                st.rerun()
            except Exception as e:
                st.error(f"Aggiornamento non riuscito: {e}")

# -------------------------------------------------------------------------- cards
c1, c2, c3, c4 = st.columns(4)
c1.metric("Investito totale", eur(totals["init"]))
c2.metric("Valore attuale", eur(totals["now"]))
c3.metric("Guadagno / Perdita", eur(totals["pl"]), pct(totals["plpct"]))
c4.metric("Posizioni", len(holdings))

st.divider()

# ------------------------------------------------------------------ tabella titoli
st.subheader("🧾 I tuoi titoli")
body = ""
for r in rows:
    col = colors.get(r["Categoria"], "#888")
    dot = (f"<span style='display:inline-block;width:10px;height:10px;border-radius:50%;"
           f"background:{col};margin-right:8px;vertical-align:middle'></span>")
    pill = f"<span class='pill' style='background:{col}22;color:{col}'>{r['Categoria']}</span>"
    body += (f"<tr><td>{dot}{r['Titolo']} &nbsp; {pill}</td>"
             f"<td>{eur(r['iniziale'])}</td>"
             f"<td>{eur(r['aggiunte']) if r['aggiunte'] else '–'}</td>"
             f"<td>{eur(r['investito'])}</td>"
             f"<td><b>{eur(r['valore'])}</b></td>"
             f"<td>{vspan(r['var'])}</td></tr>")
body += (f"<tr class='tot'><td>TOTALE</td><td>{eur(totals['iniz'])}</td>"
         f"<td>{eur(totals['add'])}</td><td>{eur(totals['init'])}</td>"
         f"<td>{eur(totals['now'])}</td><td>{vspan(totals['plpct'])}</td></tr>")
st.markdown(
    "<table class='ptbl'><thead><tr><th>Titolo</th><th>Iniziale</th><th>Aggiunte</th>"
    "<th>Investito</th><th>Valore attuale</th><th>Variazione</th></tr></thead>"
    f"<tbody>{body}</tbody></table>", unsafe_allow_html=True)

# ------------------------------------------------------------------ aggiungi PAC
st.subheader("➕ Registra un versamento (piano d'accumulo)")
with st.form("add_pac", clear_on_submit=True):
    fc = st.columns([3, 2, 2])
    sel = fc[0].selectbox("Titolo", options=[h["id"] for h in holdings],
                          format_func=lambda i: by_id(holdings, i)["nome"])
    amount = fc[1].number_input("Importo (€)", min_value=0.0, step=10.0, value=0.0)
    fc[2].write("")
    fc[2].write("")
    if fc[2].form_submit_button("Conferma versamento", use_container_width=True):
        if amount and amount > 0:
            h = by_id(holdings, sel)
            cur = float(data.get("current", {}).get(sel, h["iniziale"]))
            idx = (cur / h["iniziale"]) if h["iniziale"] else 1.0
            today = datetime.date.today().isoformat()
            ts = int(datetime.datetime.now().timestamp() * 1000)
            data.setdefault("pac", {})
            lst = data["pac"].get(sel)
            if not isinstance(lst, list):
                lst = []
            lst.append({"a": float(amount), "d": today, "idx": idx, "ts": ts})
            data["pac"][sel] = lst
            try:
                save_data(data)
                st.success(f"Aggiunto + {eur(amount)} su {h['nome']}.")
                st.rerun()
            except Exception as e:
                st.error(f"Errore nel salvataggio: {e}")
        else:
            st.warning("Inserisci un importo maggiore di zero.")

tranches_all = []
for h in holdings:
    for i, t in enumerate(data.get("pac", {}).get(h["id"], []) or []):
        tranches_all.append((h, i, t))
if tranches_all:
    with st.expander(f"📋 Versamenti registrati ({len(tranches_all)})"):
        for h, i, t in sorted(tranches_all, key=lambda x: x[2].get("ts", 0), reverse=True):
            lc = st.columns([6, 1])
            lc[0].write(f"📅 {itdate(t.get('d'))} · **{h['nome']}** · + {eur(t.get('a', 0))}")
            if lc[1].button("Rimuovi", key=f"rm_{h['id']}_{i}", use_container_width=True):
                lst = data["pac"].get(h["id"], [])
                if 0 <= i < len(lst):
                    lst.pop(i)
                    if lst:
                        data["pac"][h["id"]] = lst
                    else:
                        data["pac"].pop(h["id"], None)
                    try:
                        save_data(data)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Errore: {e}")

st.divider()

# ------------------------------------------------------------------ categorie
st.subheader("🎯 Peso e Target per categoria")
cat_now = {}
for r in rows:
    cat_now[r["Categoria"]] = cat_now.get(r["Categoria"], 0.0) + r["valore"]
tot_now = totals["now"] or 1
order = sorted(cat_now, key=lambda n: -cat_now[n])
scale = max([cat_now[n] / tot_now * 100 for n in order] + [cat_target.get(n, 0) for n in order] + [1])

bars = ""
for name in order:
    peso = cat_now[name] / tot_now * 100
    tgt = cat_target.get(name, 0)
    col = colors.get(name, "#888")
    bars += (
        "<div style='display:grid;grid-template-columns:150px 1fr 120px;gap:12px;align-items:center;margin:9px 0'>"
        f"<div style='color:{col};font-weight:700'>{name}</div>"
        "<div style='background:#171a35;border-radius:999px;height:20px;position:relative;overflow:hidden'>"
        f"<div style='height:100%;width:{peso/scale*100:.1f}%;background:{col};border-radius:999px'></div>"
        f"<div style='position:absolute;top:-2px;bottom:-2px;left:{tgt/scale*100:.1f}%;width:2px;background:{GOLD}'></div>"
        "</div>"
        f"<div style='color:{MUTED};font-size:13px'>{num1(peso)}% <span style='opacity:.6'>/ {tgt}%</span></div>"
        "</div>")
st.markdown(bars + f"<div style='color:{MUTED};font-size:12px;margin-top:6px'>"
            f"La linea oro indica il target di ogni categoria.</div>", unsafe_allow_html=True)

st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
st.caption("Apri una categoria per vederne la composizione:")
for name in order:
    peso = cat_now[name] / tot_now * 100
    tgt = cat_target.get(name, 0)
    scost = peso - tgt
    seg = "🟢" if scost >= 0 else "🔴"
    with st.expander(f"{name}  ·  {num1(peso)}% / target {tgt}%  ·  scostamento {pct(scost)} {seg}"):
        sub = [r for r in rows if r["Categoria"] == name]
        srows = ""
        for r in sub:
            wp = r["valore"] / tot_now * 100
            srows += (f"<tr><td>{r['Titolo']}</td><td>{eur(r['valore'])}</td>"
                      f"<td>{num1(wp)}%</td><td>{vspan(r['var'])}</td></tr>")
        st.markdown(
            "<table class='ptbl'><thead><tr><th>Titolo</th><th>Valore</th><th>Peso</th>"
            f"<th>Variazione</th></tr></thead><tbody>{srows}</tbody></table>",
            unsafe_allow_html=True)

st.divider()

# ------------------------------------------------------------------ storico
st.subheader("📈 Andamento del valore totale")
hist = data.get("history", [])
if len(hist) >= 2:
    hdf = pd.DataFrame([{"Data": itdate(h["date"]), "Valore (€)": h["total"]} for h in hist]).set_index("Data")
    st.line_chart(hdf, height=260)
    base_tot = hist[0]["total"]
    trows = ""
    for h in reversed(hist):
        d = (h["total"] - base_tot) / base_tot * 100 if base_tot else 0
        trows += f"<tr><td>{itdate(h['date'])}</td><td>{eur(h['total'])}</td><td>{vspan(d)}</td></tr>"
    st.markdown(
        "<table class='ptbl'><thead><tr><th>Data</th><th>Valore totale</th>"
        f"<th>Var. dall'inizio</th></tr></thead><tbody>{trows}</tbody></table>",
        unsafe_allow_html=True)
else:
    st.caption("Il grafico crescerà a ogni aggiornamento dei prezzi.")

st.divider()
st.caption("🔒 Accesso privato: solo le persone con la password e invitate via email possono vedere e modificare "
           "questa dashboard. I tuoi dati sono conservati in un archivio privato.")
