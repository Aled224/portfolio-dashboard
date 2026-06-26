# -*- coding: utf-8 -*-
"""Dashboard portafoglio (Streamlit), condivisa e privata.

Accesso protetto da password. Tutti i dati personali (titoli, importi, storico)
vivono in un repository GitHub PRIVATO e sono letti tramite una chiave segreta.
In questo file NON c'e' nessun dato personale: solo il programma generico.
"""
import datetime
import os

import altair as alt
import pandas as pd
import streamlit as st

from github_store import load_data, save_data, refresh
import prices
import news

st.set_page_config(page_title="Portafoglio", page_icon="📊", layout="wide")

PALETTE = ["#3b82f6", "#a78bfa", "#22d3ee", "#fb923c", "#34d399",
           "#f472b6", "#facc15", "#f87171", "#38bdf8", "#c084fc"]
GREEN, RED, MUTED, LINE, GOLD = "#2ecc71", "#ff5d6c", "#9aa0d0", "#2b3168", "#ffcf5c"


# --------------------------------------------------------------- formattazione
def eur(n):
    return "–" if n is None else "€ " + f"{round(n):,}".replace(",", ".")


def eur2(n):
    if n is None:
        return "–"
    return "€ " + f"{n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


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


@st.cache_data(ttl=1800, show_spinner=False)
def asset_hist_cached(sym, ccy, rng):
    return prices.asset_price_history({"sym": sym, "ccy": ccy}, rng)


@st.cache_data(ttl=1800, show_spinner=False)
def momentum_cached(sym):
    return prices.momentum(sym)


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
.tblwrap{overflow-x:auto;-webkit-overflow-scrolling:touch;width:100%}
.catbar{display:grid;grid-template-columns:150px 1fr 120px;gap:12px;align-items:center;margin:9px 0}
@media (max-width:640px){
  .ptbl{font-size:12px}
  .ptbl th,.ptbl td{padding:6px 5px;white-space:nowrap}
  .autobar{font-size:11px;padding:5px 10px;white-space:normal}
  .catbar{grid-template-columns:78px 1fr 58px;gap:6px;font-size:11px}
  .catbar>div:first-child{font-size:11px;line-height:1.1}
  .pill{font-size:10px;padding:1px 7px}
}
.advgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:12px;margin-top:6px}
.advcard{background:#1c2046;border:1px solid #2b3168;border-radius:14px;padding:14px 16px}
.advt{font-weight:700;margin-bottom:6px;font-size:14px}
.advx{color:#c7cbe8;font-size:13px;line-height:1.5}
@media (max-width:640px){.advgrid{grid-template-columns:1fr}}
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
    body += (f"<tr><td>{dot}{r['Titolo']}</td>"
             f"<td style='text-align:left'>{pill}</td>"
             f"<td>{eur(r['iniziale'])}</td>"
             f"<td>{eur(r['aggiunte']) if r['aggiunte'] else '–'}</td>"
             f"<td>{eur(r['investito'])}</td>"
             f"<td><b>{eur(r['valore'])}</b></td>"
             f"<td>{vspan(r['var'])}</td></tr>")
body += (f"<tr class='tot'><td>TOTALE</td><td></td><td>{eur(totals['iniz'])}</td>"
         f"<td>{eur(totals['add'])}</td><td>{eur(totals['init'])}</td>"
         f"<td>{eur(totals['now'])}</td><td>{vspan(totals['plpct'])}</td></tr>")
sub = "<span style='font-weight:400;text-transform:none;font-size:10px'>"
st.markdown(
    "<div class='tblwrap'><table class='ptbl'><thead><tr><th>Titolo</th><th>Categoria</th>"
    f"<th>Valore iniziale<br>{sub}{itdate(base_date)}</span></th><th>Aggiunte</th>"
    f"<th>Investito</th><th>Valore attuale<br>{sub}al {itdate(last_update)}</span></th>"
    f"<th>Variazione<br>{sub}al {itdate(last_update)}</span></th></tr></thead>"
    f"<tbody>{body}</tbody></table></div>", unsafe_allow_html=True)

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
        "<div class='catbar'>"
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
            "<div class='tblwrap'><table class='ptbl'><thead><tr><th>Titolo</th><th>Valore attuale</th><th>Peso</th>"
            f"<th>Variazione valore</th></tr></thead><tbody>{srows}</tbody></table></div>",
            unsafe_allow_html=True)

st.divider()

# ------------------------------------------------------------------ storico
st.subheader("📈 Andamento del valore totale")
hist = data.get("history", [])
if len(hist) >= 2:
    hpts = pd.DataFrame([{"data": pd.to_datetime(h["date"]), "valore": h["total"]} for h in hist])
    vmax = hpts["valore"].max()
    step = 1000
    lo = 0
    hi = max(5000, -(-int(vmax) // step) * step)   # almeno 5000, si estende se serve
    ticks = list(range(lo, hi + step, step))
    chart = (alt.Chart(hpts)
             .mark_line(point=alt.OverlayMarkDef(color="#6c8cff", size=55), color="#6c8cff", strokeWidth=2.5)
             .encode(
                 x=alt.X("data:T", sort="ascending", title=None,
                         axis=alt.Axis(format="%d/%m", labelColor="#9aa0d0", grid=False)),
                 y=alt.Y("valore:Q", title="€", scale=alt.Scale(domain=[lo, hi]),
                         axis=alt.Axis(values=ticks, labelColor="#9aa0d0", titleColor="#9aa0d0",
                                       gridColor="#2b3168")),
                 tooltip=[alt.Tooltip("data:T", title="Data", format="%d/%m/%Y"),
                          alt.Tooltip("valore:Q", title="Valore €", format=",.0f")])
             .properties(height=300)
             .configure_view(strokeOpacity=0))
    st.altair_chart(chart, use_container_width=True)
    base_tot = hist[0]["total"]
    trows = ""
    for h in reversed(hist):
        d = (h["total"] - base_tot) / base_tot * 100 if base_tot else 0
        trows += f"<tr><td>{itdate(h['date'])}</td><td>{eur(h['total'])}</td><td>{vspan(d)}</td></tr>"
    st.markdown(
        "<div class='tblwrap'><table class='ptbl'><thead><tr><th>Data</th><th>Valore totale</th>"
        f"<th>Var. dall'inizio</th></tr></thead><tbody>{trows}</tbody></table></div>",
        unsafe_allow_html=True)
else:
    st.caption("Il grafico crescerà a ogni aggiornamento dei prezzi.")

st.divider()

# ------------------------------------------------------------------ singolo titolo
st.subheader("🔍 Andamento di un singolo titolo")
asset_id = st.selectbox("Scegli un titolo", options=[h["id"] for h in holdings],
                        format_func=lambda i: by_id(holdings, i)["nome"], key="asset_sel")
ah = by_id(holdings, asset_id)
baseline_price = data.get("baseline_prices", {}).get(asset_id)

rng_label = st.radio("Periodo", ["1 mese", "6 mesi", "1 anno", "5 anni", "Max"],
                     horizontal=True, index=2, key="asset_rng")
rng_map = {"1 mese": "1mo", "6 mesi": "6mo", "1 anno": "1y", "5 anni": "5y", "Max": "max"}
axis_cfg = {
    "1 mese": {"format": "%d/%m", "tickCount": 7},
    "6 mesi": {"format": "%b", "tickCount": {"interval": "month", "step": 1}},
    "1 anno": {"format": "%b %y", "tickCount": {"interval": "month", "step": 2}},
    "5 anni": {"format": "%Y", "tickCount": {"interval": "year", "step": 1}},
    "Max":    {"format": "%Y", "tickCount": {"interval": "year", "step": 1}},
}

try:
    with st.spinner("Carico lo storico di mercato..."):
        ahist = asset_hist_cached(ah["sym"], ah["ccy"], rng_map[rng_label])
except Exception as e:
    ahist = []
    st.warning(f"Storico non disponibile ora: {e}")

cur_price = ahist[-1]["price"] if ahist else baseline_price
cur_date = itdate(ahist[-1]["date"]) if ahist else itdate(last_update)
var_price = ((cur_price / baseline_price - 1) * 100) if (baseline_price and cur_price) else 0.0
m1, m2, m3 = st.columns(3)
m1.metric(f"Valore attuale singolo asset (al {cur_date})", eur2(cur_price))
m2.metric(f"Valore iniziale singolo asset ({itdate(base_date)})", eur2(baseline_price))
m3.metric("Variazione", pct(var_price))

if len(ahist) >= 2:
    adf = pd.DataFrame([{"data": pd.to_datetime(p["date"]), "valore": p["price"]} for p in ahist])
    line_color = GREEN if adf["valore"].iloc[-1] >= adf["valore"].iloc[0] else RED
    cfg = axis_cfg[rng_label]
    xenc = alt.X("data:T", sort="ascending", title=None,
                 axis=alt.Axis(format=cfg["format"], tickCount=cfg["tickCount"],
                               labelColor="#9aa0d0", grid=False))
    yenc = alt.Y("valore:Q", title="€", scale=alt.Scale(zero=False, nice=True),
                 axis=alt.Axis(labelColor="#9aa0d0", titleColor="#9aa0d0", gridColor="#2b3168"))
    base = alt.Chart(adf)
    line = base.mark_line(color=line_color, strokeWidth=2).encode(x=xenc, y=yenc)
    nearest = alt.selection_point(nearest=True, on="pointerover", fields=["data"],
                                  empty=False, clear="pointerout")
    selectors = base.mark_point().encode(
        x=xenc, opacity=alt.value(0),
        tooltip=[alt.Tooltip("data:T", title="Data", format="%d/%m/%Y"),
                 alt.Tooltip("valore:Q", title="Valore (€)", format=",.2f")]
    ).add_params(nearest)
    pts = line.mark_point(size=75, color=line_color, filled=True).encode(
        opacity=alt.condition(nearest, alt.value(1), alt.value(0)))
    text = line.mark_text(align="left", dx=7, dy=-10, color="#eef0ff",
                          fontSize=13, fontWeight="bold").encode(
        text=alt.condition(nearest, alt.Text("valore:Q", format=",.2f"), alt.value("")))
    rule = base.mark_rule(color="#9aa0d0").encode(x=xenc).transform_filter(nearest)
    achart = alt.layer(line, selectors, pts, rule, text).properties(height=300).configure_view(strokeOpacity=0)
    st.altair_chart(achart, use_container_width=True)
    st.caption("Valore (prezzo) del titolo in euro, su prezzi reali di mercato (fonte: Yahoo Finance).")
else:
    st.caption("Storico non disponibile per questo titolo al momento.")

st.divider()

# ------------------------------------------------------------------ spunti
st.subheader("💡 Spunti di portafoglio", anchor=False)
st.caption("Spunti automatici basati sui tuoi target e sullo **storico completo dei titoli** (1 mese, 3, 6, 1 anno e "
           "intero storico disponibile), non solo sul tuo breve periodo di possesso. Ispirati a metodi di gestione del "
           "portafoglio e del rischio. **Non sono consigli finanziari**: sono osservazioni oggettive per ragionare.")

tot = totals["now"] or 1
advice = []
devs = sorted(((n, cat_now[n] / tot * 100 - cat_target.get(n, 0)) for n in cat_now), key=lambda x: x[1])
if devs and devs[0][1] <= -3:
    n = devs[0][0]
    advice.append(("🎯", "blue", f"Sotto target: {n}",
                   f"Pesa il {num1(cat_now[n]/tot*100)}% contro un target del {cat_target.get(n, 0)}%. "
                   "È la categoria più sotto i tuoi obiettivi: possibile candidata per il prossimo versamento."))
if devs and devs[-1][1] >= 3:
    n = devs[-1][0]
    advice.append(("⚖️", "gold", f"Sopra target: {n}",
                   f"Pesa il {num1(cat_now[n]/tot*100)}% contro un target del {cat_target.get(n, 0)}%. "
                   "Aggiungere altro qui ti allontanerebbe dall'equilibrio che hai scelto per le categorie."))
if rows:
    mr = max(rows, key=lambda r: r["valore"])
    w = mr["valore"] / tot * 100
    mr_tgt = cat_target.get(mr["Categoria"], 0)
    if w >= 30 and w > mr_tgt:
        advice.append(("⚠️", "red", f"Concentrazione: {mr['Titolo']}",
                       f"Da solo pesa il {num1(w)}% del portafoglio, più del target della sua categoria ({mr_tgt}%): "
                       "una posizione così grande amplifica gli effetti, in bene e in male, di un singolo titolo."))
    ps = sorted(rows, key=lambda r: r["var"])
    if ps[0]["var"] <= -3:
        advice.append(("🔻", "red", f"In calo dal 29/05: {ps[0]['Titolo']} ({pct(ps[0]['var'])})",
                       "È il titolo più in calo da quando hai investito. Pochi giorni dicono poco: "
                       "guarda anche l'andamento di lungo periodo qui sopra prima di trarre conclusioni."))
    if ps[-1]["var"] >= 3:
        advice.append(("🚀", "green", f"In rialzo dal 29/05: {ps[-1]['Titolo']} ({pct(ps[-1]['var'])})",
                       "È quello salito di più da quando hai investito: occhio a non lasciarlo diventare "
                       "una fetta troppo grande del portafoglio."))
advice.append(("📊", "green" if totals["plpct"] >= 0 else "red", "Andamento generale",
               f"Portafoglio a {eur(totals['now'])} ({pct(totals['plpct'])} dal {itdate(base_date)}). " +
               ("In positivo: di solito la cosa più utile è la costanza dei versamenti."
                if totals["plpct"] >= 0 else
                "In rosso nel breve è normale: contano l'orizzonte lungo e la disciplina.")))

# spunti avanzati: visione completa (1m/3m/6m/1a + intero storico),
# calcolati e salvati a ogni aggiornamento dei dati (niente download in diretta)
moms = data.get("momentum", {})
name_of = {h["id"]: h["nome"] for h in holdings}
valid = {hid: m for hid, m in moms.items() if m and m.get("m12") is not None}


def _fmt_h(m):
    parts = [f"{lab} {pct(m[k])}" for k, lab in
             [("m1", "1m"), ("m3", "3m"), ("m6", "6m"), ("m12", "1a")] if m.get(k) is not None]
    return " · ".join(parts)


def _hz(m, *keys):
    return all(m.get(k) is not None for k in keys)


if valid:
    # 1) Forte e COSTANTE: su a 3, 6 e 12 mesi (non un singolo colpo)
    solid = [hid for hid in valid if _hz(valid[hid], "m3", "m6", "m12")
             and valid[hid]["m12"] > 0 and valid[hid]["m6"] > 0 and valid[hid]["m3"] > 0]
    if solid:
        hid = max(solid, key=lambda k: valid[k]["m6"])
        advice.append(("📈", "green", f"Forte e costante: {name_of[hid]}",
                       f"In rialzo su tutti gli orizzonti ({_fmt_h(valid[hid])}): trend coerente, "
                       "non un rimbalzo isolato."))
    # 2) Corsa poi RITRACCIAMENTO: su sull'anno ma giù a 6 mesi (es. titoli volatili)
    runpull = [hid for hid in valid if _hz(valid[hid], "m6", "m12")
               and valid[hid]["m12"] > 0 and valid[hid]["m6"] < 0]
    if runpull:
        hid = max(runpull, key=lambda k: valid[k]["m12"])
        allp = valid[hid].get("all")
        st_txt = (f" Sull'intero storico ({valid[hid]['years']} anni): {pct(allp)}."
                  if allp is not None else "")
        advice.append(("🎢", "gold", f"Corsa e ritracciamento: {name_of[hid]}",
                       f"Ha corso sull'anno ({pct(valid[hid]['m12'])}) ma sta ritracciando "
                       f"({pct(valid[hid]['m6'])} a 6 mesi → {_fmt_h(valid[hid])}).{st_txt} "
                       "Tipico dei titoli volatili/speculativi: occhio agli alti e bassi, non guardare solo il +1 anno."))
    # 3) Debole nell'ultimo anno: giù a 12 mesi (con contesto sull'intero storico)
    weak = min((hid for hid in valid if valid[hid].get("m12") is not None),
               key=lambda k: valid[k]["m12"], default=None)
    if weak is not None and valid[weak]["m12"] < 0:
        allp = valid[weak].get("all")
        if allp is not None and allp >= 0:
            tone = "gold"
            ctx = (f" Sull'intero storico ({valid[weak]['years']} anni) resta però positivo ({pct(allp)}): "
                   "un calo recente dentro una storia più lunga in crescita, da leggere nel contesto.")
        elif allp is not None:
            tone = "red"
            ctx = (f" Anche sull'intero storico ({valid[weak]['years']} anni) è in perdita ({pct(allp)}): "
                   "debolezza più strutturale, chiediti se la tesi iniziale regge ancora.")
        else:
            tone = "red"
            ctx = " Vale la pena chiedersi se la tesi iniziale regge ancora."
        advice.append(("📉", tone, f"Debole nell'ultimo anno: {name_of[weak]}",
                       f"{pct(valid[weak]['m12'])} in 12 mesi ({_fmt_h(valid[weak])}).{ctx}"))
    # 4) Ampiezza dell'ultimo mese
    m1_vals = {hid: m["m1"] for hid, m in valid.items() if m.get("m1") is not None}
    if m1_vals:
        up = sum(1 for v in m1_vals.values() if v > 0)
        n = len(m1_vals)
        if up / n >= 0.7:
            advice.append(("🌅", "green", "Ampiezza positiva (ultimo mese)",
                           f"{up} titoli su {n} in rialzo: forza diffusa, fase favorevole."))
        elif up / n <= 0.3:
            advice.append(("🛡️", "gold", "Fase difensiva (ultimo mese)",
                           f"Solo {up} su {n} in rialzo: mercato debole, meglio esposizione prudente."))
        else:
            advice.append(("🔀", "blue", "Quadro misto (ultimo mese)",
                           f"{up} su {n} in rialzo: nessuna direzione netta nel breve."))
    # 5) In raffreddamento: solido (anno e 6 mesi su) ma giù nell'ultimo mese
    cooling = [hid for hid in valid if _hz(valid[hid], "m1", "m6", "m12")
               and valid[hid]["m12"] > 0 and valid[hid]["m6"] > 0 and valid[hid]["m1"] < 0]
    if cooling:
        hid = min(cooling, key=lambda k: valid[k]["m1"])
        advice.append(("🌡️", "gold", f"In raffreddamento: {name_of[hid]}",
                       f"Solido sull'anno e a 6 mesi ma in calo nell'ultimo mese "
                       f"({pct(valid[hid]['m1'])}): rallentamento recente da tenere d'occhio."))
    # 6) Possibile ripresa: debole sull'anno ma su nell'ultimo mese
    rec = [hid for hid in valid if _hz(valid[hid], "m1", "m12")
           and valid[hid]["m12"] < 0 and valid[hid]["m1"] > 0]
    if rec:
        hid = max(rec, key=lambda k: valid[k]["m1"])
        advice.append(("🌱", "green", f"Possibile ripresa: {name_of[hid]}",
                       f"Debole sull'anno ({pct(valid[hid]['m12'])}) ma in rialzo nell'ultimo mese "
                       f"({pct(valid[hid]['m1'])}): primo segnale di inversione, da confermare."))

tone_col = {"green": GREEN, "red": RED, "blue": "#6c8cff", "gold": GOLD}
cards = ""
for icon, tone, title, text in advice:
    c = tone_col.get(tone, "#6c8cff")
    cards += (f"<div class='advcard' style='border-left:4px solid {c}'>"
              f"<div class='advt'>{icon} {title}</div><div class='advx'>{text}</div></div>")
st.markdown(f"<div class='advgrid'>{cards}</div>", unsafe_allow_html=True)
st.caption("⚠️ Informazioni a scopo educativo, non consulenza finanziaria. Le decisioni restano tue.")

st.divider()

# ------------------------------------------------------------------ radar news
st.subheader("🔭 Nuovi spunti dal mercato", anchor=False)
st.caption("Notizie pubbliche in tempo reale (Google News, centinaia di testate) **agganciate ai tuoi ambiti**: "
           "ogni blocco mostra solo **eventi rilevanti per un investimento** (IPO, acquisizioni, fusioni, "
           "partnership, round, aperture…) **dentro i settori in cui hai investito** — AI/Cloud, Auto "
           "elettriche/Batterie, Mercati emergenti, Sanità, Azionario globale — più le **grandi operazioni "
           "globali** lontane ma significative. Sono **spunti da approfondire, non consigli finanziari**.")


@st.cache_data(ttl=10800, show_spinner=False)  # aggiorna ogni 3 ore
def _carica_news():
    return news.market_news(per_tema=5)


col_a, col_b = st.columns([1, 4])
with col_a:
    if st.button("🔄 Aggiorna news"):
        _carica_news.clear()

try:
    with st.spinner("Cerco notizie sul mercato…"):
        temi = _carica_news()
except Exception:
    temi = []

if not any(t["notizie"] for t in temi):
    st.info("Nessuna notizia recuperata al momento. Riprova tra poco con «🔄 Aggiorna news».")
else:
    for t in temi:
        if not t["notizie"]:
            continue
        st.markdown(f"**{t['emoji']} {t['etichetta']}**")
        cards = ""
        for n in t["notizie"]:
            meta = " · ".join(x for x in (n["fonte"], n["data"]) if x)
            cards += (
                "<div class='advcard' style='border-left:4px solid #6c8cff'>"
                f"<div class='advt'><a href='{n['link']}' target='_blank' "
                f"style='color:#e8ebff;text-decoration:none'>{n['titolo']}</a></div>"
                f"<div class='advx'>{meta}<br>"
                f"<a href='{n['link']}' target='_blank' style='color:#6c8cff'>↗ leggi la notizia</a>"
                "</div></div>")
        st.markdown(f"<div class='advgrid'>{cards}</div>", unsafe_allow_html=True)
        st.write("")

st.caption("⚠️ Fonti giornalistiche di terze parti, riportate automaticamente. "
           "Non è consulenza finanziaria: fai sempre le tue verifiche.")

st.divider()
st.caption("🔒 Accesso privato: solo le persone con la password e invitate via email possono vedere e modificare "
           "questa dashboard. I tuoi dati sono conservati in un archivio privato.")
