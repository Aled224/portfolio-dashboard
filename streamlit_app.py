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


# --------------------------------------------------------------- formattazione
def eur(n):
    return "–" if n is None else "€ " + f"{round(n):,}".replace(",", ".")


def pct(n):
    return "–" if n is None else f"{n:+.1f}".replace(".", ",") + "%"


def itdate(iso):
    try:
        y, m, d = str(iso).split("-")
        return f"{d}/{m}/{y}"
    except Exception:
        return str(iso)


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

# -------------------------------------------------------------------- intestazione
top = st.columns([5, 1, 1])
with top[0]:
    st.title("📊 Il mio portafoglio")
    sub = f"Investimento iniziale del **{itdate(base_date)}**"
    if last_update:
        sub += f" · prezzi al **{itdate(last_update)}**"
    st.caption(sub)
with top[1]:
    if st.button("🔄 Ricarica", use_container_width=True, help="Rilegge gli ultimi dati salvati"):
        refresh()
        st.rerun()
with top[2]:
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
df = pd.DataFrame([{
    "Titolo": r["Titolo"], "Categoria": r["Categoria"],
    "Iniziale": eur(r["iniziale"]),
    "Aggiunte": eur(r["aggiunte"]) if r["aggiunte"] else "–",
    "Investito": eur(r["investito"]), "Valore attuale": eur(r["valore"]),
    "Variazione": pct(r["var"]),
} for r in rows])
df.loc[len(df)] = ["TOTALE", "", eur(totals["iniz"]), eur(totals["add"]),
                   eur(totals["init"]), eur(totals["now"]), pct(totals["plpct"])]
st.dataframe(df, hide_index=True, use_container_width=True)

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

# ------------------------------------------------------------------ elenco versamenti
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
else:
    st.caption("Nessun versamento registrato finora.")

st.divider()

# ------------------------------------------------------------------ categorie
st.subheader("🎯 Peso e Target per categoria")
cat_now = {}
for r in rows:
    cat_now[r["Categoria"]] = cat_now.get(r["Categoria"], 0.0) + r["valore"]
tot_now = totals["now"] or 1
cat_rows = []
for name in sorted(cat_now, key=lambda n: -cat_now[n]):
    peso = cat_now[name] / tot_now * 100
    tgt = cat_target.get(name, 0)
    color = colors.get(name, "#888")
    cc = st.columns([2, 4, 2])
    cc[0].markdown(f"<span style='color:{color};font-weight:700'>{name}</span>", unsafe_allow_html=True)
    cc[1].progress(min(peso / 100, 1.0))
    cc[2].write(f"{peso:.1f}% / target {tgt}%".replace(".", ","))
    cat_rows.append({"Categoria": name, "Valore": eur(cat_now[name]),
                     "Peso": pct(peso).replace("+", ""), "Target": f"{tgt}%",
                     "Scostamento": pct(peso - tgt)})
st.dataframe(pd.DataFrame(cat_rows), hide_index=True, use_container_width=True)

st.divider()

# ------------------------------------------------------------------ storico
st.subheader("📈 Andamento del valore totale")
hist = data.get("history", [])
if len(hist) >= 2:
    hdf = pd.DataFrame([{"Data": itdate(h["date"]), "Valore (€)": h["total"]} for h in hist]).set_index("Data")
    st.line_chart(hdf, height=260)
    base_tot = hist[0]["total"]
    tbl = []
    for h in reversed(hist):
        d = (h["total"] - base_tot) / base_tot * 100 if base_tot else 0
        tbl.append({"Data": itdate(h["date"]), "Valore totale": eur(h["total"]), "Var. iniziale": pct(d)})
    st.dataframe(pd.DataFrame(tbl), hide_index=True, use_container_width=True)
else:
    st.caption("Il grafico crescerà a ogni aggiornamento dei prezzi.")

st.divider()
st.caption("🔒 Accesso privato: solo le persone con la password e invitate via email possono vedere e modificare "
           "questa dashboard. I tuoi dati sono conservati in un archivio privato.")
