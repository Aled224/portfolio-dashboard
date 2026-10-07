# -*- coding: utf-8 -*-
"""Dashboard portafoglio (Streamlit), condivisa e privata.

Accesso protetto da password. Tutti i dati personali (titoli, importi, storico)
vivono in un repository GitHub PRIVATO e sono letti tramite una chiave segreta.
In questo file NON c'e' nessun dato personale: solo il programma generico.
"""
import datetime
import hmac
import html
import time
import os

import altair as alt
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from github_store import load_data, save_data, refresh
import prices
import news

st.set_page_config(page_title="Portafoglio", page_icon="📊", layout="wide")

PALETTE = ["#3b82f6", "#a78bfa", "#22d3ee", "#fb923c", "#0f7a3d",
           "#f472b6", "#facc15", "#f87171", "#38bdf8", "#c084fc"]
GREEN, RED, MUTED, LINE, GOLD = "#0f7a3d", "#c42a3a", "#475569", "#d5dbe6", "#9a6a00"


def done(msg):
    """Conferma che resta visibile: la salvo, ricarico la pagina e la mostro in cima
    (senza questo il messaggio sparirebbe subito con il ricaricamento)."""
    st.session_state["flash"] = msg
    st.rerun()


def show_flash():
    msg = st.session_state.pop("flash", None)
    if msg:
        st.toast(f"✅ {msg}")
        st.markdown(f"<div class='flash'><span class='fic'>✓</span><div><b>Fatto.</b> {html.escape(msg)}</div></div>",
                    unsafe_allow_html=True)


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


def qtyfmt(n):
    """Numero di azioni/monete: fino a 4 decimali, senza zeri inutili (5 · 0,7812 · 411,82)."""
    if n is None:
        return "–"
    dec = 0 if abs(n - round(n)) < 1e-9 else (2 if abs(n) >= 100 else 5)
    s = f"{n:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return s.rstrip("0").rstrip(",") if "," in s else s


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
            return str(st.secrets["app_password"])
    except Exception:
        pass
    return os.environ.get("APP_PASSWORD", "")


def check_password():
    # Secondo lucchetto, dopo il login Google di Streamlit. Se il segreto manca,
    # l'app si chiude a tutti invece di lasciar passare chi non digita nulla.
    attesa = _password()
    if not attesa:
        st.title("📊 Portafoglio")
        st.error("Configurazione incompleta: manca il segreto `app_password`. "
                 "L'app resta chiusa finche' non viene impostato nei Secrets di Streamlit.")
        st.stop()

    ora = time.time()
    if st.session_state.get("authed"):
        # l'accesso scade dopo 12 ore (es. telefono rimasto con l'app aperta)
        if ora - st.session_state.get("authed_at", 0) < 12 * 3600:
            return True
        st.session_state.pop("authed", None)

    # --- schermata d'accesso: una scheda al centro, un campo, un bottone
    st.markdown("""
<style>
[data-testid="stHeader"]{background:transparent}
.block-container{max-width:480px !important;padding:9vh 1.25rem 3rem !important}
.lg-logo{width:64px;height:64px;border-radius:18px;margin:0 auto 18px;display:flex;align-items:center;justify-content:center;
  background:linear-gradient(135deg,#1d3bb3,#3a5bd9);box-shadow:0 10px 24px rgba(36,70,200,.30)}
.lg-title{text-align:center;font-size:32px !important;line-height:1.15;font-weight:800;letter-spacing:-.6px;color:#0f172a;margin:0}
.lg-sub{text-align:center;font-size:18px !important;color:#475569;margin:6px 0 26px}
[data-testid="stForm"]{background:#fff;border:1px solid #d5dbe6 !important;border-radius:18px;padding:26px 24px 22px;
  box-shadow:0 1px 2px rgba(15,23,42,.05),0 12px 32px rgba(15,23,42,.08)}
[data-testid="stForm"] input{font-size:18px !important;height:50px}
[data-testid="stForm"] [data-testid="stWidgetLabel"] p{font-size:16px;font-weight:600;color:#334155}
[data-testid="stForm"] button{min-height:52px;font-size:18px !important;font-weight:700}
[data-testid="stForm"] button p{color:#fff !important;font-size:18px !important;font-weight:700}
.lg-foot{text-align:center;font-size:15px !important;color:#64748b;margin-top:18px;line-height:1.5}
@media (max-width:640px){.block-container{padding:6vh 1rem 2rem !important}.lg-title{font-size:28px !important}}
</style>
<div class="lg-logo"><svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.4"
 stroke-linecap="round" stroke-linejoin="round"><polyline points="3 17 9 11 13 15 21 7"/><polyline points="15 7 21 7 21 13"/></svg></div>
<div class="lg-title">Il mio portafoglio</div>
<div class="lg-sub">Azioni e crypto, a colpo d'occhio.</div>
""", unsafe_allow_html=True)
    with st.form("login", border=True):
        digitata = st.text_input("Password", type="password", placeholder="Scrivi la password")
        entra = st.form_submit_button("Entra", type="primary", use_container_width=True)
    bloccato_fino = st.session_state.get("lock_until", 0)
    if entra and ora < bloccato_fino:
        st.error(f"Troppi tentativi sbagliati. Riprova tra {int((bloccato_fino - ora) // 60) + 1} minuti.")
    elif entra:
        if digitata and hmac.compare_digest(digitata.encode("utf-8"), attesa.encode("utf-8")):
            st.session_state["authed"] = True
            st.session_state["authed_at"] = ora
            st.session_state["fails"] = 0
            st.rerun()
        fails = st.session_state.get("fails", 0) + 1
        st.session_state["fails"] = fails
        time.sleep(min(1.0 * fails, 5))          # rallenta chi prova password a raffica
        if fails >= 5:
            st.session_state["lock_until"] = ora + 600
            st.session_state["fails"] = 0
            st.error("Troppi tentativi sbagliati. Accesso bloccato per 10 minuti.")
        else:
            st.error("Password non corretta. Riprova.")
    st.markdown("<div class='lg-foot'>🔒 Accesso privato. I dati restano in un archivio protetto.</div>",
                unsafe_allow_html=True)
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


def qty_of(data, h):
    """Quante azioni/monete avevi il giorno di partenza.
    Soldi messi quel giorno / prezzo di quel giorno (100 € a 1 € = 100 azioni).
    Da qui in poi: valore = azioni x prezzo di oggi."""
    base = float(data.get("baseline_prices", {}).get(h["id"]) or 0)
    return (float(h["iniziale"]) / base) if base else None


def tranche_qty(data, h, t):
    """Azioni comprate con un versamento: euro versati / prezzo del giorno del versamento."""
    base = float(data.get("baseline_prices", {}).get(h["id"]) or 0)
    p = base * float(t.get("idx", 1) or 1)
    return (float(t.get("a", 0)) / p) if p else 0.0


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
        q0 = qty_of(data, h)
        qtot = (q0 + sum(tranche_qty(data, h, t) for t in tranches)) if q0 is not None else None
        # titolo comprato DOPO la partenza ("dal" = data d'acquisto): non e' valore di
        # partenza, sono soldi versati dopo
        if h.get("dal") and h["dal"] > data.get("base_date", ""):
            addcost += iniz
            iniz = 0.0
        rows.append({"id": hid, "Titolo": html.escape(h["nome"]), "Categoria": html.escape(h["cat"]),
                     "iniziale": iniz, "aggiunte": addcost, "investito": invtot,
                     "qty": q0, "qty_tot": qtot,
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
def asset_hist_cached(sym, ccy, cg_id, source, rng):
    return prices.asset_price_history({"sym": sym, "ccy": ccy, "cg_id": cg_id, "source": source}, rng)


# --------------------------------------------- aggiunta nuovo titolo / versamenti
def _fetch_now_eur(sym, source=None, cg_id=None):
    """Prezzo unitario ATTUALE in EUR + valuta rilevata. Serve anche a validare il simbolo."""
    if source == "coingecko" and cg_id:
        now, _ = prices.coingecko_chart(cg_id, days="1")
        if not now:
            raise ValueError("nessun prezzo")
        return float(now), "EUR"
    cur, now, _ = prices.yahoo(sym, rng="5d")
    if not now:
        raise ValueError("nessun prezzo")
    cur = cur or "EUR"
    if cur != "EUR":
        fx, _ = prices.fx_to_eur(cur, rng="5d")
        return float(now) * float(fx or 1.0), cur
    return float(now), cur


def _slug(text, existing):
    base = "".join(ch for ch in text.lower() if ch.isalnum())[:12] or "asset"
    hid, i = base, 2
    while hid in existing:
        hid = f"{base}{i}"
        i += 1
    return hid


def add_holding(data, nome, sym, cat, qty, is_crypto, source=None, cg_id=None):
    """Aggiunge un nuovo titolo/crypto al piano partendo dal NUMERO di azioni/monete.
    Baseline = prezzo di oggi: la posizione parte oggi e vale azioni x prezzo."""
    sym = sym.strip().upper()
    if is_crypto and source != "coingecko" and "-" not in sym:
        sym = sym + "-EUR"
    now_eur, ccy = _fetch_now_eur(sym, source=source, cg_id=cg_id)   # valida e prende il prezzo
    amount = float(qty) * now_eur
    existing = {h["id"] for h in data.get("holdings", [])}
    hid = _slug(nome, existing)
    h = {"id": hid, "nome": nome.strip(), "sym": sym, "ccy": ccy,
         "iniziale": round(float(amount), 2), "cat": (cat.strip() or "Altro"),
         "dal": datetime.date.today().isoformat()}
    if source == "coingecko" and cg_id:
        h["cg_id"] = cg_id
        h["source"] = "coingecko"
        h["ccy"] = "EUR"
    data.setdefault("holdings", []).append(h)
    data.setdefault("baseline_prices", {})[hid] = round(float(amount), 2) / float(qty)   # azioni esatte
    data.setdefault("current", {})[hid] = round(float(amount), 2)
    return h


@st.cache_data(ttl=3600, show_spinner=False)
def search_assets_cached(q, is_crypto):
    return prices.search_coingecko(q) if is_crypto else prices.search_yahoo(q)


def hero_html(title, tot, parts_note):
    """Riquadro principale: quanto vale tutto, quanto ho guadagnato, da dove arriva."""
    pl, plpct = tot["pl"], tot["plpct"]
    cls, arrow = ("pos", "▲") if pl >= 0 else ("neg", "▼")
    return (
        "<div class='hero'>"
        f"<div class='h-lab'>{title}</div>"
        f"<div class='h-val'>{eur(tot['now'])}</div>"
        f"<div class='h-chg {cls}'>{arrow} {eur(abs(pl))} <span>{pct(plpct)}</span></div>"
        "<div class='h-grid'>"
        f"<div><span>Valore di partenza</span><b>{eur(tot['iniz'])}</b><small>{parts_note}</small></div>"
        f"<div><span>Versato dopo</span><b>{eur(tot['add'])}</b><small>acquisti successivi</small></div>"
        f"<div><span>Totale messo</span><b>{eur(tot['init'])}</b><small>partenza + versato</small></div>"
        "</div></div>")


def pcard(name, dot, value, var, line2, tag=""):
    """Una posizione come scheda: si legge sul telefono senza scorrere di lato."""
    cls = "pos" if var >= 0 else "neg"
    return (
        "<div class='pcard'>"
        f"<div class='pc-top'><span class='pc-dot' style='background:{dot}'></span>"
        f"<span class='pc-name'>{name}{tag}</span><span class='pc-val'>{eur(value)}</span></div>"
        f"<div class='pc-bot'><span>{line2}</span><span class='chg {cls}'>{pct(var)}</span></div>"
        "</div>")


def price_bar(last_update, key, on_refresh, info=""):
    """Riga sotto il riquadro principale: data dei prezzi + bottone Aggiorna."""
    c = st.columns([3, 1.3])
    nm = next_monday(last_update)
    c[0].markdown(
        f"<div class='autobar'>🕒 Prezzi al <b>{itdate(last_update)}</b>"
        + (f" · prossimo aggiornamento automatico <b>{itdate(nm)}</b>" if nm else "")
        + (f"<br>{info}" if info else "") + "</div>", unsafe_allow_html=True)
    if c[1].button("🔄 Aggiorna prezzi", key=key, use_container_width=True, type="primary",
                   help="Scarica subito i prezzi di mercato"):
        with st.spinner("Scarico i prezzi di mercato..."):
            try:
                on_refresh()
                refresh()
                done("Prezzi aggiornati.")
            except Exception as e:
                st.error(f"Aggiornamento non riuscito: {e}")


def render_history_list(data, doc, holdings, ns, unit):
    """Elenco degli acquisti fatti dopo la partenza, con possibilita' di toglierne uno."""
    tranches_all = []
    for h in holdings:
        for i, t in enumerate(data.get("pac", {}).get(h["id"], []) or []):
            tranches_all.append((h, i, t))
    if not tranches_all:
        return
    with st.expander(f"📋 Acquisti registrati dopo la partenza ({len(tranches_all)})"):
        st.caption("Se ne hai registrato uno per sbaglio, toglilo da qui.")
        for h, i, t in sorted(tranches_all, key=lambda x: x[2].get("ts", 0), reverse=True):
            lc = st.columns([5, 1.3])
            q = tranche_qty(data, h, t)
            lc[0].markdown(f"**{h['nome']}** · {itdate(t.get('d'))}  \n"
                           f"{qtyfmt(q)} {unit} · {eur2(float(t.get('a', 0)))}")
            if lc[1].button("Togli", key=f"{ns}_rm_{h['id']}_{i}", use_container_width=True):
                lst = data["pac"].get(h["id"], [])
                if 0 <= i < len(lst):
                    lst.pop(i)
                    if lst:
                        data["pac"][h["id"]] = lst
                    else:
                        data["pac"].pop(h["id"], None)
                    try:
                        save_data(doc)
                        done(f"Tolto l'acquisto del {itdate(t.get('d'))} su {h['nome']}.")
                    except Exception as e:
                        st.error(f"Errore: {e}")


def _render_add_existing(data, doc, holdings, ns, unit):
    """Aggiunge azioni/monete a una posizione gia' nel piano: o dici quante ne hai
    comprate, o dici quanto vale ora tutto quello che hai e il conto lo fa l'app.
    Si registra come versamento in euro, cosi' 'Versato dopo' resta in soldi."""
    fmt = "%.6f" if ns == "cry" else "%.5f"
    sel = st.selectbox("Scegli", options=[h["id"] for h in holdings],
                       format_func=lambda i: by_id(holdings, i)["nome"], key=f"{ns}_ex_sel")
    h = by_id(holdings, sel)
    _, tr = _invested_of(data, sel, h)
    valtot = _value_of(data, sel, h)
    qtot = (qty_of(data, h) or 0.0) + sum(tranche_qty(data, h, t) for t in tr)
    price = (valtot / qtot) if qtot else 0.0     # prezzo di una azione all'ultimo aggiornamento
    mc = st.columns(2)
    mc[0].metric(f"{unit.capitalize()} che hai", qtyfmt(qtot))
    mc[1].metric("Valgono oggi", eur(valtot))

    PER_NUM = f"Ti dico quante {unit} ho comprato"
    PER_EUR = "Ti dico quanti soldi in più ho investito"
    PER_VAL = "Ti dico quanto vale ora tutto quello che ho"
    how = st.radio("Come preferisci", [PER_NUM, PER_EUR, PER_VAL], key=f"{ns}_ex_how_{sel}")
    una = "azione" if unit == "azioni" else "moneta"
    if how == PER_EUR:
        spent = st.number_input("Quanti soldi in più hai investito (€)", min_value=0.0, step=10.0, value=0.0,
                                key=f"{ns}_ex_inv_{sel}")
        qty = (spent / price) if price else 0.0
        if qty > 0:
            st.caption(f"Al prezzo dell'ultimo aggiornamento ({eur2(price)} per {una}) "
                       f"sono {qtyfmt(qty)} {unit}.")
    else:
        if how == PER_NUM:
            qty = st.number_input(f"Quante {unit} hai comprato", min_value=0.0, step=1.0, value=0.0,
                                  format=fmt, key=f"{ns}_ex_qty_{sel}")
        else:
            tot_now = st.number_input("Quanto vale ora tutto quello che hai (€)", min_value=0.0, step=10.0,
                                      value=float(round(valtot, 2)), key=f"{ns}_ex_tot_{sel}",
                                      help="Lo trovi nell'app della banca o del broker. Calcolo io quante "
                                           f"{unit} hai aggiunto, al prezzo dell'ultimo aggiornamento.")
            qty = max(0.0, (tot_now / price) - qtot) if price else 0.0
            if qty > 0:
                st.caption(f"Quindi ora hai {qtyfmt(qtot + qty)} {unit}: ne hai aggiunte {qtyfmt(qty)}.")
        spent = st.number_input("Quanto hai speso (€)", min_value=0.0, step=10.0,
                                value=float(round(qty * price, 2)),
                                key=f"{ns}_ex_eur_{sel}_{how[:8]}_{int(round(qty * 1e6))}",
                                help=f"Te lo propongo al prezzo dell'ultimo aggiornamento ({eur2(price)} "
                                     f"per {una}). Correggilo con quanto hai pagato davvero.")
    if st.button(f"Aggiungi {unit}", key=f"{ns}_ex_btn", type="primary", use_container_width=True):
        if qty <= 0 or spent <= 0:
            st.warning(f"Non risultano {unit} da aggiungere: controlla i numeri.")
        else:
            try:
                add_tranche(data, sel, spent, qty=qty)
                save_data(doc)
                done(f"Aggiunte {qtyfmt(qty)} {unit} a {h['nome']} ({eur(spent)}).")
            except Exception as e:
                st.error(f"Errore nel salvataggio: {e}")


def render_manage(data, doc, holdings, ns):
    """Tutte le modifiche in un posto: aggiungi a una posizione che hai, aggiungi una
    posizione nuova, togli/sposta. Scelta a pulsanti grandi, comodi anche col pollice."""
    is_crypto = (ns == "cry")
    unit = "monete" if is_crypto else "azioni"
    ESIST = "➕ Aggiungi a crypto che ho già" if is_crypto else "➕ Aggiungi a titolo che ho già"
    NUOVO = "🆕 Nuova crypto" if is_crypto else "🆕 Nuovo titolo"
    RIDUCI = "➖ Togli o sposta"
    st.markdown(f"<div class='sec'>✏️ Hai comprato o venduto?</div>", unsafe_allow_html=True)
    opts = [ESIST, NUOVO, RIDUCI] if holdings else [NUOVO]
    mode = st.segmented_control("Cosa vuoi fare", opts, key=f"{ns}_manage_mode",
                                label_visibility="collapsed")
    if mode is None:
        st.caption("Scegli qui sopra cosa vuoi fare.")
    else:
        with st.container(border=True):
            if mode == ESIST:
                _render_add_existing(data, doc, holdings, ns, unit)
            elif mode == NUOVO:
                render_add_asset(data, doc, holdings, ns)
            else:
                render_edit_asset(data, doc, holdings, ns)
    render_history_list(data, doc, holdings, ns, unit)


def render_add_asset(data, doc, holdings, ns):
    """Aggiungi un nuovo titolo/crypto: scrivi il nome, scegli dal menu (nome + simbolo
    compilati in automatico da Yahoo/CoinGecko), oppure inseriscilo a mano. Usato da entrambe le tab."""
    is_crypto = (ns == "cry")
    kind = "crypto" if is_crypto else "titolo"
    fonte = "CoinGecko" if is_crypto else "Yahoo Finance"
    with st.container():
        q = st.text_input("Scrivi nome", key=f"{ns}_q",
                          placeholder="Bitcoin" if is_crypto else "Apple",
                          help=f"Man mano che scrivi ti propongo i risultati reali di {fonte}. "
                               "Scegli sempre dall'elenco: così il nome combacia e il prezzo si trova di sicuro.")
        results = []
        if q and len(q.strip()) >= 2:
            try:
                results = search_assets_cached(q.strip(), is_crypto)
            except Exception:
                results = []

        chosen = None
        if results:
            idx = st.selectbox("Scegli dall'elenco reale",
                               options=list(range(len(results))),
                               format_func=lambda i: results[i]["label"], key=f"{ns}_pick")
            chosen = results[idx]
        elif q and len(q.strip()) >= 2:
            st.warning(f"Nessun risultato su {fonte}. Prova un altro nome, "
                       "oppure spunta «inserisci a mano».")

        manual = st.checkbox("Non lo trovo: inserisco nome e simbolo a mano", key=f"{ns}_manual")
        m_nome = m_sym = ""
        if manual:
            mc = st.columns(2)
            m_nome = mc[0].text_input("Nome", key=f"{ns}_mnome")
            m_sym = mc[1].text_input("Simbolo", key=f"{ns}_msym",
                                     help="Es. BTC, ETH" if is_crypto else "Es. AAPL, ENEL.MI, RO.SW")

        # categoria (ETF, Sanità, ...): SOLO azioni, tra quelle esistenti. Le crypto NON hanno categorie.
        cat = "Crypto" if is_crypto else ""
        if not is_crypto:
            cats = list(dict.fromkeys([h["cat"] for h in holdings]))
            NUOVA = "➕ Nuova categoria…"
            cat_pick = st.selectbox("Categoria", options=cats + [NUOVA], key=f"{ns}_catsel")
            cat = st.text_input("Nome nuova categoria", key=f"{ns}_catnew") if cat_pick == NUOVA else cat_pick

        unit = "monete" if is_crypto else "azioni"
        amount = st.number_input(f"Quante {unit} hai", min_value=0.0, step=1.0, value=0.0,
                                 format="%.6f" if is_crypto else "%.5f", key=f"{ns}_qty",
                                 help="La posizione parte da oggi: vale queste quantità per il prezzo di oggi.")

        if st.button(f"Aggiungi {kind}", key=f"{ns}_addbtn", type="primary", use_container_width=True):
            if manual:
                nome, sym, source, cg_id = m_nome.strip(), m_sym.strip(), None, None
            elif chosen:
                nome, sym = chosen["nome"], chosen["sym"]
                source, cg_id = chosen.get("source"), chosen.get("cg_id")
            else:
                nome = sym = ""
                source = cg_id = None
            if not nome or not sym:
                st.warning("Scegli un asset dall'elenco oppure inseriscilo a mano.")
            elif not is_crypto and not str(cat).strip():
                st.warning("Scegli una categoria.")
            elif amount <= 0:
                st.warning(f"Inserisci quante {unit} hai (maggiore di zero).")
            else:
                try:
                    h = add_holding(data, nome, sym, cat, amount, is_crypto, source=source, cg_id=cg_id)
                    save_data(doc)
                    done(f"Aggiunto {h['nome']} ({h['sym']}): {qtyfmt(amount)} {unit}. "
                               "Comparirà anche nella tabella e nei grafici di andamento.")
                except Exception as e:
                    st.error(f"Non riesco a recuperare il prezzo di «{sym.upper()}». "
                             f"Controlla il simbolo. Dettaglio: {repr(e)[:80]}")


def _invested_of(data, hid, h):
    """Investito = quota iniziale + versamenti registrati."""
    tr = data.get("pac", {}).get(hid) or []
    if not isinstance(tr, list):
        tr = []
    return float(h["iniziale"]) + sum(float(t.get("a", 0)) for t in tr), tr


def reduce_holding(data, hid, amount):
    """Toglie `amount` euro (la fetta di azioni vendute) da una posizione, in proporzione: scala
    allo stesso modo quota iniziale, versamenti e valore attuale. Cosi' la
    variazione percentuale della posizione resta identica (e' come vendere una
    fetta, o come correggere un importo inserito sbagliato).
    Torna True se la posizione e' stata svuotata del tutto (quindi rimossa)."""
    h = by_id(data.get("holdings", []), hid)
    invtot, tranches = _invested_of(data, hid, h)
    rest = invtot - float(amount)
    if rest < 0.01:
        remove_holding(data, hid)
        return True
    f = rest / invtot
    valnow = float(data.get("current", {}).get(hid, h["iniziale"]))
    h["iniziale"] = round(float(h["iniziale"]) * f, 2)
    data.setdefault("current", {})[hid] = round(valnow * f, 2)
    if tranches:
        kept = []
        for t in tranches:
            t["a"] = round(float(t.get("a", 0)) * f, 2)
            if t["a"] >= 0.01:
                kept.append(t)
        if kept:
            data["pac"][hid] = kept
        else:
            data["pac"].pop(hid, None)
    return False


def remove_holding(data, hid):
    """Toglie del tutto una posizione dal piano. Lo storico passato resta com'e':
    e' il registro di quello che c'era davvero in quei giorni."""
    data["holdings"] = [x for x in data.get("holdings", []) if x["id"] != hid]
    for key in ("current", "baseline_prices", "pac", "momentum"):
        d = data.get(key)
        if isinstance(d, dict):
            d.pop(hid, None)


def _value_of(data, hid, h):
    """Quanto vale oggi la posizione: quota iniziale + versamenti cresciuti."""
    valnow = float(data.get("current", {}).get(hid, h["iniziale"]))
    idxnow = (valnow / h["iniziale"]) if h["iniziale"] else 1.0
    _, tranches = _invested_of(data, hid, h)
    return valnow + sum(float(t.get("a", 0)) * idxnow / (t.get("idx", 1) or 1) for t in tranches)


def _all_positions(doc):
    """Tutte le posizioni del piano, azioni e crypto insieme: cosi' si puo' spostare
    un importo anche da un'azione a una crypto (e viceversa)."""
    out = []
    for emoji, ds in (("📈", doc), ("🪙", doc.get("crypto") or {})):
        for h in ds.get("holdings", []) or []:
            out.append({"ds": ds, "h": h, "label": f"{emoji} {h['nome']}"})
    return out


def add_tranche(ds, hid, amount, qty=None):
    """Registra un versamento su una posizione, alla quotazione di oggi.
    Con `qty` (azioni comprate) il prezzo pagato e' amount / qty: cosi' le azioni
    aggiunte sono esattamente quelle, anche se hai pagato un prezzo diverso."""
    h = by_id(ds.get("holdings", []), hid)
    cur = float(ds.get("current", {}).get(hid, h["iniziale"]))
    idx = (cur / h["iniziale"]) if h["iniziale"] else 1.0
    base = float(ds.get("baseline_prices", {}).get(hid) or 0)
    if qty and base:
        idx = float(amount) / (float(qty) * base)
    lst = ds.setdefault("pac", {}).get(hid)
    if not isinstance(lst, list):
        lst = []
    lst.append({"a": float(amount), "d": datetime.date.today().isoformat(), "idx": idx,
                "ts": int(datetime.datetime.now().timestamp() * 1000)})
    ds["pac"][hid] = lst
    return h


def _dest_picker(doc, escludi_id, ns, suffix, default_amount):
    """Chiede se l'importo e' stato spostato su un'altra posizione gia' nel piano.
    Torna (dataset_destinazione, id, nome, importo) oppure None."""
    opts = [p for p in _all_positions(doc) if p["h"]["id"] != escludi_id]
    if not opts:
        return None
    FUORI = "Fuori dal piano: li ho ritirati"
    pick = st.selectbox("Dove sono finiti questi soldi?",
                        options=[-1] + list(range(len(opts))),
                        format_func=lambda i: FUORI if i < 0 else "Spostati su " + opts[i]["label"],
                        key=f"{ns}_{suffix}_dest",
                        help="Se li hai spostati su un titolo o una crypto che hai già nel piano, "
                             "li registro lì come versamento di oggi. Se invece hai comprato "
                             "qualcosa di nuovo, aggiungilo dal pannello qui sopra.")
    if pick < 0:
        return None
    d = opts[pick]
    amt = st.number_input(f"Quanto ne hai messo su {d['h']['nome']} (€)", min_value=0.0, step=10.0,
                          value=float(round(default_amount, 2)),
                          key=f"{ns}_{suffix}_damt_{escludi_id}_{pick}_{int(round(default_amount * 100))}",
                          help="Di solito è quanto hai ricavato dalla vendita. Correggilo se hai "
                               "spostato solo una parte o se il prezzo di scambio era diverso.")
    return d["ds"], d["h"]["id"], d["h"]["nome"], amt


def render_edit_asset(data, doc, holdings, ns):
    """Togli azioni da una posizione (per numero o per valore che ti resta) oppure
    toglila tutta dal piano, con un clic. Usato da entrambe le tab."""
    if not holdings:
        return
    unit = "monete" if ns == "cry" else "azioni"
    fmt = "%.6f" if ns == "cry" else "%.5f"
    sel = st.selectbox("Scegli", options=[h["id"] for h in holdings],
                       format_func=lambda i: by_id(holdings, i)["nome"], key=f"{ns}_ed_sel")
    h = by_id(holdings, sel)
    invtot, tr = _invested_of(data, sel, h)
    valtot = _value_of(data, sel, h)
    q0 = qty_of(data, h)
    qtot = (q0 or 0.0) + sum(tranche_qty(data, h, t) for t in tr)
    price = (valtot / qtot) if qtot else 0.0
    mc = st.columns(2)
    mc[0].metric(f"{unit.capitalize()} che hai", qtyfmt(qtot))
    mc[1].metric("Valgono oggi", eur(valtot))

    PER_NUM = f"Ho venduto un numero di {unit}"
    PER_VAL = "Ti dico quanto vale ora quello che mi resta"
    TUTTO = "Togli tutto dal piano"
    how = st.radio("Cosa hai fatto", [PER_NUM, PER_VAL, TUTTO], key=f"{ns}_ed_how_{sel}")

    if how == TUTTO:
        st.caption(f"Tolgo {h['nome']} dalla tabella e dai grafici, con tutti i suoi versamenti. "
                   "Lo storico dei giorni passati resta com'è.")
        dest_rm = _dest_picker(doc, sel, ns, "rm", valtot)
        if st.button(f"Togli {h['nome']} dal piano" + (" e sposta" if dest_rm else ""),
                     key=f"{ns}_ed_del_{sel}", use_container_width=True):
            try:
                remove_holding(data, sel)
                msg = f"{h['nome']} tolto dal piano."
                if dest_rm:
                    ds_d, hid_d, nome_d, amt_d = dest_rm
                    if amt_d > 0:
                        add_tranche(ds_d, hid_d, amt_d)
                        msg += f" Registrati {eur(amt_d)} su {nome_d}."
                save_data(doc)
                done(msg)
            except Exception as e:
                st.error(f"Errore nel salvataggio: {e}")
        return

    if how == PER_NUM:
        sold = st.number_input(f"Quante {unit} hai venduto", min_value=0.0, max_value=float(qtot),
                               step=1.0, value=0.0, format=fmt, key=f"{ns}_ed_qty_{sel}")
    else:
        left = st.number_input("Quanto vale ora quello che ti resta (€)", min_value=0.0,
                               max_value=float(round(valtot, 2)), step=10.0, value=float(round(valtot, 2)),
                               key=f"{ns}_ed_left_{sel}",
                               help="Lo trovi nell'app della banca o del broker. Calcolo io quante "
                                    f"{unit} hai venduto, al prezzo dell'ultimo aggiornamento.")
        sold = max(0.0, qtot - (left / price)) if price else 0.0
        if sold > 0:
            st.caption(f"Quindi ti restano {qtyfmt(qtot - sold)} {unit}: ne hai vendute {qtyfmt(sold)}.")
    frac = (sold / qtot) if qtot else 0.0
    amount = invtot * frac
    ricavo = valtot * frac
    if sold > 0 and how == PER_NUM:
        st.caption(f"Vendendo {qtyfmt(sold)} {unit} ricavi circa {eur(ricavo)} ai prezzi di oggi.")
    dest = _dest_picker(doc, sel, ns, "red", ricavo)
    if st.button("Togli e sposta" if dest else "Togli", key=f"{ns}_ed_btn_{sel}", use_container_width=True):
        if sold <= 0:
            st.warning(f"Non risultano {unit} vendute: controlla il numero.")
        else:
            try:
                svuotata = reduce_holding(data, sel, amount)
                msg = (f"{h['nome']} era tutto qui: l'ho tolto dal piano."
                       if svuotata else
                       f"Tolte {qtyfmt(sold)} {unit} da {h['nome']}. Ne restano {qtyfmt(qtot - sold)}.")
                if dest:
                    ds_d, hid_d, nome_d, amt_d = dest
                    if amt_d > 0:
                        add_tranche(ds_d, hid_d, amt_d)
                        msg += f" Registrati {eur(amt_d)} su {nome_d}."
                save_data(doc)
                done(msg)
            except Exception as e:
                st.error(f"Errore nel salvataggio: {e}")


# --------------------------------------------------------------- dati cripto
CRYPTO_DEFAULT = {
    "base_date": "2026-06-26",
    "last_update": "2026-06-26",
    "holdings": [
        {"id": "sol", "nome": "Solana (SOL)", "sym": "SOL-EUR", "ccy": "EUR", "cg_id": "solana", "source": "coingecko", "iniziale": 2856.22, "cat": "Layer 1"},
        {"id": "wld", "nome": "Worldcoin (WLD)", "sym": "WLD-USD", "ccy": "USD", "cg_id": "worldcoin-wld", "source": "coingecko", "iniziale": 167.14, "cat": "AI / Identity"},
    ],
    "baseline_prices": {"sol": 62.40, "wld": 0.405853},
    "current": {"sol": 2856.22, "wld": 167.14},
    "pac": {},
    "history": [],
    "momentum": {},
}

try:
    # Il documento vive in memoria per tutta la sessione: cosi' quando aggiungi/rimuovi
    # qualcosa lo vedi SUBITO (senza aspettare che GitHub propaghi la scrittura, che per
    # qualche secondo restituisce ancora la versione vecchia). Un F5 ricarica dal cloud.
    if "doc" not in st.session_state:
        st.session_state["doc"] = load_data()
except Exception as e:
    st.error(f"Non riesco a leggere i dati. Controlla i Secrets (github_token, github_repo). Dettaglio: {e}")
    st.stop()
doc = st.session_state["doc"]
_cry = doc.get("crypto")
if not isinstance(_cry, dict) or not _cry.get("holdings"):
    doc["crypto"] = CRYPTO_DEFAULT
    try:
        save_data(doc); refresh()
    except Exception:
        pass
else:
    _strk = next((h for h in _cry["holdings"] if h.get("id") == "strk"), None)
    if _strk:
        _sol = next((h for h in _cry["holdings"] if h.get("id") == "sol"), None)
        _cur = _cry.setdefault("current", {})
        _bp = _cry.setdefault("baseline_prices", {})
        if _sol:
            _sol["iniziale"] = round(float(_sol.get("iniziale", 0)) + float(_strk.get("iniziale", 0)), 2)
            _cur["sol"] = round(float(_cur.get("sol", _sol["iniziale"])) + float(_cur.get("strk", 0)), 2)
        _cry["holdings"] = [h for h in _cry["holdings"] if h.get("id") != "strk"]
        _cur.pop("strk", None); _bp.pop("strk", None)
        _cry.get("cat_target", {}).pop("Layer 2 / ZK", None)
        _cry.get("pac", {}).pop("strk", None)
        try:
            save_data(doc); refresh()
        except Exception:
            pass

st.markdown("""
<style>
/* =========================================================================
   Tema chiaro ad alto contrasto. Scala: testo 18px, tabelle 17px, note 15px.
   Testo #0f172a, secondario #475569 (contrasto AA su bianco e sul fondo).
   ========================================================================= */
html, body, .stApp, .ptbl, .hero, .pcard, .scard, .autobar, .advcard, .sec, button, input, textarea{
  font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif !important}
.stApp{font-feature-settings:"cv11","tnum" 0;-webkit-font-smoothing:antialiased}
:root{--ink:#0f172a;--ink2:#334155;--mute:#475569;--line:#d5dbe6;--soft:#f6f8fb;--card:#ffffff;--brand:#2446c8}
.block-container{max-width:1180px;padding-top:2.2rem !important;padding-bottom:4rem !important}
h1{font-size:2.15rem !important;font-weight:800 !important;letter-spacing:-.5px;color:var(--ink) !important}
h2,h3{color:var(--ink) !important;font-weight:750 !important;letter-spacing:-.3px}
h3{font-size:1.45rem !important;margin:.4rem 0 .5rem !important}
p, li, label{color:var(--ink)}
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p{font-size:15.5px !important;color:var(--mute) !important;line-height:1.5}
[data-testid="stWidgetLabel"] p{font-size:16px !important;font-weight:600;color:var(--ink2) !important}
hr{margin:2rem 0 !important;border-color:var(--line) !important}

/* schede Azioni / Crypto / Panoramica */
[data-testid="stTabs"] [role="tablist"]{gap:6px;border-bottom:2px solid var(--line)}
[data-testid="stTabs"] button[role="tab"]{padding:10px 18px;border-radius:10px 10px 0 0}
[data-testid="stTabs"] button[role="tab"] p{font-size:18px !important;font-weight:700;color:var(--mute)}
[data-testid="stTabs"] button[role="tab"][aria-selected="true"] p{color:var(--brand)}

/* riquadri numerici */
[data-testid="stMetric"]{background:var(--card);border:1px solid var(--line);border-radius:14px;
  padding:16px 18px;box-shadow:0 1px 2px rgba(15,23,42,.05),0 4px 14px rgba(15,23,42,.04);height:100%}
[data-testid="stMetricLabel"] p{font-size:15px !important;font-weight:600;color:var(--mute) !important}
[data-testid="stMetricValue"]{font-size:30px !important;font-weight:800;color:var(--ink);letter-spacing:-.5px}
[data-testid="stMetricDelta"]{font-size:15px !important;font-weight:700}

/* pannelli apribili */
[data-testid="stExpander"] details{background:var(--card);border:1px solid var(--line) !important;border-radius:14px;
  box-shadow:0 1px 2px rgba(15,23,42,.04)}
[data-testid="stExpander"] summary p{font-size:17px !important;font-weight:700;color:var(--ink)}

/* pulsanti */
.stButton button, .stFormSubmitButton button{min-height:46px;font-size:16.5px !important;font-weight:700;border-radius:10px}
.stButton button p, .stFormSubmitButton button p{font-size:16.5px !important;font-weight:700}
/* bottoni blu (es. Aggiorna prezzi): testo bianco */
button[kind="primary"], button[kind="primaryFormSubmit"],
button[kind="primary"] p, button[kind="primaryFormSubmit"] p,
button[data-testid="stBaseButton-primary"] p{color:#ffffff !important}
/* bottoni bianchi: testo scuro */
button[kind="secondary"] p, button[kind="secondaryFormSubmit"] p,
button[data-testid="stBaseButton-secondary"] p{color:var(--ink) !important}

/* tabelle */
.tblwrap{overflow-x:auto;-webkit-overflow-scrolling:touch;width:100%;background:var(--card);
  border:1px solid var(--line);border-radius:14px;box-shadow:0 1px 2px rgba(15,23,42,.05)}
.ptbl{width:100%;border-collapse:collapse;font-size:17px;color:var(--ink)}
.ptbl th{background:var(--soft);color:var(--ink2);text-align:right;padding:12px 14px;font-size:13px;font-weight:700;
  text-transform:uppercase;letter-spacing:.3px;border-bottom:1px solid var(--line);vertical-align:bottom;line-height:1.3}
.ptbl td{text-align:right;padding:13px 14px;border-bottom:1px solid #e6eaf1;font-variant-numeric:tabular-nums}
.ptbl tbody tr:nth-child(even) td{background:#fafbfd}
.ptbl tbody tr:hover td{background:#eef3ff}
.ptbl th:first-child,.ptbl td:first-child{text-align:left;font-weight:600}
.ptbl tr.tot td{font-weight:800;border-top:2px solid #b9c2d3;border-bottom:none;background:var(--soft) !important}
.pill{display:inline-block;padding:4px 11px;border-radius:999px;font-size:13.5px;font-weight:700;white-space:nowrap}
.autobar{display:inline-block;background:var(--card);border:1px solid var(--line);border-radius:12px;
  padding:9px 16px;font-size:15.5px;color:var(--ink2);margin:2px 0 8px;line-height:1.45}
.autobar b{color:var(--ink)}

/* titoli di sezione */
.sec{font-size:22px;font-weight:800;color:var(--ink);letter-spacing:-.3px;margin:6px 0 12px}
.thsub{font-weight:500;text-transform:none;font-size:12px;color:#64748b}

/* riquadro principale */
.hero{background:linear-gradient(135deg,#1d3bb3 0%,#2446c8 55%,#3a5bd9 100%);color:#fff;border-radius:20px;
  padding:24px 26px 20px;margin:6px 0 12px;box-shadow:0 10px 30px rgba(36,70,200,.25)}
.h-lab{font-size:16px;font-weight:600;opacity:.9}
.h-val{font-size:46px;font-weight:800;letter-spacing:-1px;line-height:1.1;margin:4px 0 6px;font-variant-numeric:tabular-nums}
.h-chg{display:inline-block;font-size:18px;font-weight:800;padding:5px 12px;border-radius:999px;background:rgba(255,255,255,.16)}
.h-chg.pos{color:#b9f6cf}.h-chg.neg{color:#ffd0d4}
.h-chg span{font-weight:700;opacity:.95;margin-left:4px}
.h-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:18px}
.h-grid div{background:rgba(255,255,255,.12);border-radius:12px;padding:10px 12px}
.h-grid span{display:block;font-size:13px;opacity:.85;font-weight:600}
.h-grid b{display:block;font-size:20px;font-variant-numeric:tabular-nums}
.h-grid small{display:block;font-size:12px;opacity:.75}

/* posizioni: tabella su computer, schede su telefono */
.mcards{display:none}
.pcard{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:13px 15px;margin-bottom:9px;
  box-shadow:0 1px 2px rgba(15,23,42,.04)}
.pc-top{display:flex;align-items:center;gap:10px}
.pc-dot{flex:0 0 10px;height:10px;border-radius:50%}
.pc-name{flex:1;font-weight:700;font-size:17px;color:var(--ink);line-height:1.25}
.pc-val{font-weight:800;font-size:18px;font-variant-numeric:tabular-nums}
.pc-bot{display:flex;justify-content:space-between;align-items:center;margin-top:5px;padding-left:20px;
  font-size:14.5px;color:var(--mute)}
.chg{font-weight:800;padding:2px 9px;border-radius:999px;font-size:14px}
.chg.pos{color:#0f7a3d;background:#e3f4ea}.chg.neg{color:#c42a3a;background:#fbe6e8}

/* azioni vs crypto */
.splitbar{display:flex;height:14px;border-radius:999px;overflow:hidden;margin:2px 0 12px}
.split{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.scard{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 16px}
.s-lab{font-weight:700;color:var(--ink2);display:flex;justify-content:space-between}
.s-lab span{color:var(--mute);font-weight:700}
.s-val{font-size:26px;font-weight:800;margin:4px 0;font-variant-numeric:tabular-nums}
.s-sub{font-size:14.5px;color:var(--mute)}

/* pulsanti di scelta (aggiungi / nuovo / togli) */
[data-testid="stButtonGroup"] button{min-height:46px;font-size:16px !important;font-weight:700}
[data-testid="stButtonGroup"] button p{font-size:16px !important;font-weight:700}
[data-testid="stButtonGroup"] button[kind*="Active"] p{color:var(--brand) !important}

/* conferma dopo ogni operazione */
.flash{display:flex;gap:12px;align-items:center;background:#e8f6ee;border:1px solid #8fd1a9;border-left:6px solid #0f7a3d;
  border-radius:12px;padding:14px 18px;margin:4px 0 14px;font-size:17px;color:#0f172a;animation:flin .35s ease-out}
.flash b{color:#0f7a3d}
.fic{flex:0 0 32px;height:32px;border-radius:50%;background:#0f7a3d;color:#fff;font-weight:800;font-size:18px;
  display:flex;align-items:center;justify-content:center}
@keyframes flin{from{opacity:0;transform:translateY(-6px)}to{opacity:1;transform:none}}

/* spunti */
.advgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:14px;margin-top:10px}
.advcard{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px 20px;
  box-shadow:0 1px 2px rgba(15,23,42,.04)}
.advt{font-weight:750;margin-bottom:8px;font-size:17px;color:var(--ink)}
.advx{color:var(--ink2);font-size:16px;line-height:1.6}

/* grafici su carta bianca */
[data-testid="stVegaLiteChart"], [data-testid="stArrowVegaLiteChart"]{background:var(--card);border:1px solid var(--line);
  border-radius:14px;padding:12px 10px 4px}

/* ============================== TELEFONO ============================== */
@media (max-width:640px){
  .block-container{padding:1.1rem .8rem 3rem !important}
  h1{font-size:1.7rem !important}
  h3{font-size:1.25rem !important}
  [data-testid="stHorizontalBlock"]{flex-wrap:wrap !important;gap:10px !important}
  [data-testid="stHorizontalBlock"] > div{flex:1 1 145px !important;min-width:145px !important}
  [data-testid="stMetric"]{padding:12px 14px}
  [data-testid="stMetricLabel"] p{font-size:13.5px !important}
  [data-testid="stMetricValue"]{font-size:23px !important}
  [data-testid="stMetricDelta"]{font-size:13.5px !important}
  [data-testid="stTabs"] button[role="tab"]{padding:8px 10px}
  [data-testid="stTabs"] button[role="tab"] p{font-size:16px !important}
  /* tabelle: il nome resta fermo a sinistra, il resto scorre di lato */
  .ptbl{font-size:15.5px}
  .ptbl th,.ptbl td{padding:11px 10px;white-space:nowrap}
  .ptbl th{font-size:12px}
  .ptbl th:first-child,.ptbl td:first-child{position:sticky;left:0;z-index:1;background:var(--card);
    box-shadow:2px 0 0 var(--line);max-width:150px;white-space:normal}
  .ptbl tbody tr:nth-child(even) td:first-child{background:#fafbfd}
  .ptbl th:first-child{background:var(--soft)}
  .dtbl{display:none}
  .mcards{display:block}
  .hero{padding:18px 16px 14px;border-radius:16px}
  .h-val{font-size:36px}
  .h-chg{font-size:16px}
  .h-grid{grid-template-columns:1fr 1fr 1fr;gap:6px}
  .h-grid div{padding:8px 8px}
  .h-grid b{font-size:15.5px}
  .h-grid span{font-size:11.5px}
  .h-grid small{display:none}
  .sec{font-size:19px}
  .split{gap:8px}
  .scard{padding:12px}
  .s-val{font-size:20px}
  .s-sub{font-size:13px}
  [data-testid="stButtonGroup"] button{flex:1 1 100%}
  .autobar{font-size:14.5px;padding:9px 12px;white-space:normal}
  .pill{font-size:12.5px;padding:3px 9px}
  .advgrid{grid-template-columns:1fr}
  .advx{font-size:15.5px}
  [role="radiogroup"]{flex-wrap:wrap !important}
  .main .block-container{overflow-x:hidden}
}
</style>
""", unsafe_allow_html=True)

_th = st.columns([6, 1.4])
_th[0].title("📊 Il mio portafoglio")
show_flash()
with _th[1]:
    st.write("")
    if st.button("🔄 Ricarica dal cloud", use_container_width=True,
                 help="Riscarica i dati più recenti dal cloud (utile dopo l'aggiornamento del lunedì)"):
        st.session_state.pop("doc", None)
        refresh()
        st.rerun()

_CG_IDS = {"sol": "solana", "wld": "worldcoin-wld"}
_cg_chg = False
for _h in doc.get("crypto", {}).get("holdings", []):
    if _h.get("id") in _CG_IDS and _h.get("source") != "coingecko":
        _h["cg_id"] = _CG_IDS[_h["id"]]
        _h["source"] = "coingecko"
        _cg_chg = True
if _cg_chg:
    try:
        save_data(doc); refresh()
    except Exception:
        pass


SCROLL_TBL = """
<style>
 @font-face{font-family:"Inter";src:url("/app/static/Inter-latin.woff2") format("woff2");font-weight:400 800}
 *{box-sizing:border-box}
 body{margin:0;background:transparent;color:#0f172a;
      font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
 .wrap{display:flex;gap:8px;align-items:stretch}
 .box{flex:1;min-width:0;height:__H__px;overflow-y:auto;overflow-x:auto;
      -webkit-overflow-scrolling:touch;border-radius:10px}
 .box::-webkit-scrollbar{width:6px;height:6px}
 .box::-webkit-scrollbar-thumb{background:#e3e6ef;border-radius:999px}
 .box::-webkit-scrollbar-track{background:transparent}
 table{width:100%;border-collapse:collapse;font-size:17px;background:#ffffff;font-variant-numeric:tabular-nums}
 th{color:#475569;text-align:right;padding:0 8px;height:32px;font-size:12.5px;font-weight:600;text-transform:uppercase;
    letter-spacing:.3px;border-bottom:1px solid #e3e6ef;position:sticky;top:0;background:#f5f6fa;z-index:2}
 td{text-align:right;padding:0 8px;height:36px;border-bottom:1px solid #e3e6ef;white-space:nowrap}
 th:first-child,td:first-child{text-align:left}
 .nav{display:flex;flex-direction:column;justify-content:center;gap:6px;flex:0 0 auto}
 .nav button{width:34px;height:38px;border-radius:10px;background:#ffffff;border:1px solid #e3e6ef;
             color:#475569;font-size:12px;line-height:1;cursor:pointer;transition:.15s}
 .nav button:hover:not(:disabled){color:#0f172a;border-color:#2446c8}
 .nav button:disabled{opacity:.3;cursor:default}
 @media (max-width:640px){table{font-size:15.5px} th{font-size:12px} th,td{padding:0 9px}
   .nav button{width:30px;height:34px}}
</style>
<div class="wrap">
  <div class="box" id="box"><table>__HEAD____BODY__</table></div>
  __NAV__
</div>
<script>
 var box = document.getElementById('box'),
     up = document.getElementById('up'), dn = document.getElementById('dn');
 if (up) {
   var STEP = 36 * 3;   // tre righe per clic: si vede sempre qualcosa di gia' letto
   function upd() {
     up.disabled = box.scrollTop <= 1;
     dn.disabled = box.scrollTop >= box.scrollHeight - box.clientHeight - 1;
   }
   up.onclick = function () { box.scrollBy({top: -STEP, behavior: 'smooth'}); };
   dn.onclick = function () { box.scrollBy({top: STEP, behavior: 'smooth'}); };
   box.addEventListener('scroll', upd);
   upd();
 }
</script>
"""


def render_scroll_table(head_html, rows, visible=5):
    """Tabella alta poche righe con due frecce a destra per scorrere (e scroll normale
    col dito o la rotella). Lo storico si allunga a ogni lunedi': senza questo si
    mangerebbe tutta la pagina. Vive in un iframe, quindi scorre senza ricaricare nulla."""
    if not rows:
        return
    n_vis = min(visible, len(rows))
    h = 32 + n_vis * 36 + 2
    nav = ("" if len(rows) <= visible else
           '<div class="nav"><button id="up" title="Su">&#9650;</button>'
           '<button id="dn" title="Giù">&#9660;</button></div>')
    html = (SCROLL_TBL.replace("__H__", str(h)).replace("__HEAD__", head_html)
            .replace("__BODY__", "<tbody>" + "".join(rows) + "</tbody>").replace("__NAV__", nav))
    components.html(html, height=h + 4, scrolling=False)


def render_dashboard(ds, doc, ns):
    data = ds
    holdings = data.get("holdings", [])
    colors = cat_colors(holdings)
    rows, totals = compute(data)
    last_update = data.get("last_update", "")
    base_date = data.get("base_date", "2026-05-29")
    unit = "Monete" if ns == "cry" else "Azioni"
    # ------------------------------------------------------------- riquadro principale
    st.markdown(hero_html("Le tue crypto valgono" if ns == "cry" else "Le tue azioni valgono",
                          totals, f"{unit.lower()} al {itdate(base_date)}"), unsafe_allow_html=True)
    price_bar(last_update, f"{ns}_refresh",
              lambda: (prices.update_prices_in_data(ds, log=lambda *_: None), save_data(doc)))

    # ------------------------------------------------------------------ posizioni
    st.markdown(f"<div class='sec'>{'🪙 Le tue crypto' if ns == 'cry' else '🧾 I tuoi titoli'}</div>",
                unsafe_allow_html=True)
    body, cards = "", ""
    for r in sorted(rows, key=lambda x: -x["valore"]):
        col = colors.get(r["Categoria"], "#888")
        dot = (f"<span style='display:inline-block;width:10px;height:10px;border-radius:50%;"
               f"background:{col};margin-right:8px;vertical-align:middle'></span>")
        pill = f"<span class='pill' style='background:{col}1f;color:{col}'>{r['Categoria']}</span>"
        catcell = f"<td style='text-align:left'>{pill}</td>" if ns != "cry" else ""
        body += (f"<tr><td>{dot}{r['Titolo']}</td>" + catcell
                 + f"<td>{qtyfmt(r['qty_tot'])}</td>"
                 f"<td>{eur(r['iniziale']) if r['iniziale'] else '–'}</td>"
                 f"<td>{eur(r['aggiunte']) if r['aggiunte'] else '–'}</td>"
                 f"<td><b>{eur(r['valore'])}</b></td>"
                 f"<td>{vspan(r['var'])}</td></tr>")
        cards += pcard(r["Titolo"], col, r["valore"], r["var"],
                       f"{qtyfmt(r['qty_tot'])} {unit.lower()} · messi {eur(r['investito'])}")
    body += (f"<tr class='tot'><td>TOTALE</td>" + ("<td></td>" if ns != "cry" else "")
             + f"<td></td><td>{eur(totals['iniz'])}</td>"
             f"<td>{eur(totals['add'])}</td>"
             f"<td>{eur(totals['now'])}</td><td>{vspan(totals['plpct'])}</td></tr>")
    sub = "<span class='thsub'>"
    st.markdown(
        "<div class='dtbl'><div class='tblwrap'><table class='ptbl'><thead><tr><th>Titolo</th>"
        + ("<th>Categoria</th>" if ns != "cry" else "")
        + f"<th>{unit}</th>"
        f"<th>Valore di partenza<br>{sub}al {itdate(base_date)}</span></th>"
        f"<th>Versato dopo</th>"
        f"<th>Valore attuale</th>"
        f"<th>Variazione</th></tr></thead>"
        f"<tbody>{body}</tbody></table></div></div>"
        f"<div class='mcards'>{cards}</div>", unsafe_allow_html=True)
    with st.expander("ℹ️ Come si calcolano questi numeri"):
        st.markdown(
            f"- **{unit} di partenza** = soldi che avevi il {itdate(base_date)} ÷ prezzo di quel giorno.\n"
            f"- **Valore attuale** = {unit.lower()} che hai × prezzo di oggi.\n"
            f"- **Versato dopo** = soldi degli acquisti fatti dopo la partenza.\n"
            f"- **Variazione** = valore attuale rispetto a quanto hai messo in tutto (partenza + versato).")

    render_manage(data, doc, holdings, ns)
    st.divider()

    # ------------------------------------------------------------------ storico
    st.markdown("<div class='sec'>📈 Andamento del valore totale</div>", unsafe_allow_html=True)
    hist = data.get("history", [])
    if len(hist) >= 2:
        hpts = pd.DataFrame([{"data": pd.to_datetime(h["date"]), "valore": h["total"]} for h in hist])
        vmax = hpts["valore"].max()
        step = 1000
        lo = 0
        hi = max(5000, -(-int(vmax) // step) * step)   # almeno 5000, si estende se serve
        ticks = list(range(lo, hi + step, step))
        chart = (alt.Chart(hpts)
                 .mark_line(point=alt.OverlayMarkDef(color="#2446c8", size=55), color="#2446c8", strokeWidth=2.5)
                 .encode(
                     x=alt.X("data:T", sort="ascending", title=None,
                             axis=alt.Axis(format="%d/%m", labelColor="#475569", grid=False)),
                     y=alt.Y("valore:Q", title="€", scale=alt.Scale(domain=[lo, hi]),
                             axis=alt.Axis(values=ticks, labelColor="#475569", titleColor="#475569",
                                           gridColor="#e3e6ef")),
                     tooltip=[alt.Tooltip("data:T", title="Data", format="%d/%m/%Y"),
                              alt.Tooltip("valore:Q", title="Valore €", format=",.0f")])
                 .properties(height=300)
                 .configure_view(strokeOpacity=0))
        st.altair_chart(chart, use_container_width=True)
        base_tot = hist[0]["total"]
        trows = []
        for h in reversed(hist):
            d = (h["total"] - base_tot) / base_tot * 100 if base_tot else 0
            trows.append(f"<tr><td>{itdate(h['date'])}</td><td>{eur(h['total'])}</td><td>{vspan(d)}</td></tr>")
        render_scroll_table(
            "<thead><tr><th>Data</th><th>Valore totale</th><th>Var. dall'inizio</th></tr></thead>",
            trows, visible=5)
    else:
        st.caption("Il grafico crescerà a ogni aggiornamento dei prezzi.")

    st.divider()

    # ------------------------------------------------------------------ singolo titolo
    st.markdown("<div class='sec'>🔍 Andamento di un singolo titolo</div>", unsafe_allow_html=True)
    asset_id = st.selectbox("Scegli un titolo", options=[h["id"] for h in holdings],
                            format_func=lambda i: by_id(holdings, i)["nome"], key=f"{ns}_asset_sel")
    ah = by_id(holdings, asset_id)
    baseline_price = data.get("baseline_prices", {}).get(asset_id)

    rng_label = st.radio("Periodo", ["1 mese", "6 mesi", "1 anno", "5 anni", "Max"],
                         horizontal=True, index=2, key=f"{ns}_asset_rng")
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
            ahist = asset_hist_cached(ah["sym"], ah["ccy"], ah.get("cg_id"), ah.get("source"), rng_map[rng_label])
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
                                   labelColor="#475569", grid=False))
        yenc = alt.Y("valore:Q", title="€", scale=alt.Scale(zero=False, nice=True),
                     axis=alt.Axis(labelColor="#475569", titleColor="#475569", gridColor="#e3e6ef"))
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
        text = line.mark_text(align="left", dx=7, dy=-10, color="#0f172a",
                              fontSize=13, fontWeight="bold").encode(
            text=alt.condition(nearest, alt.Text("valore:Q", format=",.2f"), alt.value("")))
        rule = base.mark_rule(color="#475569").encode(x=xenc).transform_filter(nearest)
        achart = alt.layer(line, selectors, pts, rule, text).properties(height=300).configure_view(strokeOpacity=0)
        st.altair_chart(achart, use_container_width=True)
        _fonte = "CoinGecko (fallback Yahoo Finance)" if ns == "cry" else "Yahoo Finance"
        st.caption(f"Valore (prezzo) in euro, su prezzi reali di mercato (fonte: {_fonte}).")
    else:
        st.caption("Storico non disponibile per questo titolo al momento.")

    if ns != "cry":
        st.divider()

        # ------------------------------------------------------------------ spunti
        st.subheader("💡 Spunti di portafoglio", anchor=False)
        st.caption("Spunti automatici basati sulle tue posizioni e sullo **storico completo dei titoli** (1 mese, 3, 6, 1 anno e "
                   "intero storico disponibile), non solo sul tuo breve periodo di possesso. Ispirati a metodi di gestione del "
                   "portafoglio e del rischio. **Non sono consigli finanziari**: sono osservazioni oggettive per ragionare.")

        tot = totals["now"] or 1
        advice = []
        if rows:
            mr = max(rows, key=lambda r: r["valore"])
            w = mr["valore"] / tot * 100
            # un ETF globale diversifica da solo: la concentrazione conta sui titoli singoli
            if w >= 30 and mr["Categoria"] != "Core ETF":
                advice.append(("⚠️", "red", f"Concentrazione: {mr['Titolo']}",
                               f"Da solo pesa il {num1(w)}% del portafoglio: "
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
        name_of = {h["id"]: html.escape(h["nome"]) for h in holdings}
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

        tone_col = {"green": GREEN, "red": RED, "blue": "#2446c8", "gold": GOLD}
        cards = ""
        for icon, tone, title, text in advice:
            c = tone_col.get(tone, "#2446c8")
            cards += (f"<div class='advcard' style='border-left:4px solid {c}'>"
                      f"<div class='advt'>{icon} {title}</div><div class='advx'>{text}</div></div>")
        st.markdown(f"<div class='advgrid'>{cards}</div>", unsafe_allow_html=True)
        st.caption("⚠️ Informazioni a scopo educativo, non consulenza finanziaria. Le decisioni restano tue.")



@st.cache_data(ttl=10800, show_spinner=False)
def _carica_news():
    return news.market_news(per_tema=5)


@st.cache_data(ttl=10800, show_spinner=False)
def _carica_crypto_news():
    return news.crypto_news(per_tema=5)


def _render_temi(temi):
    if not any(t["notizie"] for t in temi):
        st.info("Nessuna notizia recuperata al momento. Riprova tra poco con il tasto Aggiorna news.")
        return
    for t in temi:
        if not t["notizie"]:
            continue
        st.markdown(f"**{t['emoji']} {t['etichetta']}**")
        cards = ""
        for n in t["notizie"]:
            meta = html.escape(" · ".join(x for x in (n["fonte"], n["data"]) if x))
            link = str(n.get("link") or "")
            link = html.escape(link, quote=True) if link.startswith(("https://", "http://")) else "#"
            cards += (
                "<div class='advcard' style='border-left:4px solid #2446c8'>"
                f"<div class='advt'><a href='{link}' target='_blank' rel='noopener noreferrer' "
                f"style='color:#0f172a;text-decoration:none'>{html.escape(n['titolo'])}</a></div>"
                f"<div class='advx'>{meta}<br>"
                f"<a href='{link}' target='_blank' rel='noopener noreferrer' style='color:#2446c8'>↗ leggi la notizia</a>"
                "</div></div>")
        st.markdown(f"<div class='advgrid'>{cards}</div>", unsafe_allow_html=True)
        st.write("")
    st.caption("⚠️ Fonti giornalistiche di terze parti, riportate automaticamente. "
               "Non è consulenza finanziaria: fai sempre le tue verifiche.")


STAKING_RATES = {"sol": 0.0572, "wld": 0.1368}
STAKING_HORIZONS = {"6 mesi": 0.5, "1 anno": 1, "2 anni": 2, "5 anni": 5, "10 anni": 10}


def render_staking_projection(ds):
    st.divider()
    st.subheader("🌱 Proiezione staking", anchor=False)
    st.caption("Le tue crypto sono in **staking**: Solana **5,72%/anno**, Worldcoin **13,68%/anno**. "
               "Scegli l'orizzonte: proiezione a interesse composto, solo rendimento staking (prezzi fermi). "
               "Stima indicativa, non garanzia: il valore di mercato può variare molto.")
    sel = st.selectbox("Orizzonte", list(STAKING_HORIZONS.keys()), index=1, key="cry_stake_horizon")
    yrs = STAKING_HORIZONS[sel]
    rws, _ = compute(ds)
    valmap = {r["id"]: r["valore"] for r in rws}
    holds = [h for h in ds.get("holdings", []) if h["id"] in STAKING_RATES]
    cols = st.columns(len(holds) or 1)
    for col, h in zip(cols, holds):
        now = valmap.get(h["id"], float(h.get("iniziale", 0)))
        rate = STAKING_RATES[h["id"]]
        val = now * ((1 + rate) ** yrs)
        rate_str = f"{rate*100:.2f}".replace(".", ",")
        with col:
            st.markdown(f"**{h['nome']}** · staking {rate_str}%/anno")
            st.metric(f"Proiezione a {sel}", eur(val), f"+ {eur(val - now)}")
            st.caption(f"Valore attuale: {eur(now)}")


def render_stock_news():
    st.divider()
    st.subheader("🔭 Nuovi spunti dal mercato", anchor=False)
    st.caption("Notizie pubbliche in tempo reale (Google News) **agganciate ai tuoi settori azionari** "
               "(AI/Cloud, Auto elettriche/Batterie, Mercati emergenti, Sanità, Azionario globale) più grandi "
               "operazioni globali e macro. **Spunti, non consigli finanziari**.")
    if st.button("🔄 Aggiorna news", key="stk_news_refresh"):
        _carica_news.clear()
    try:
        with st.spinner("Cerco notizie sul mercato…"):
            temi = _carica_news()
    except Exception:
        temi = []
    _render_temi(temi)


def render_crypto_news():
    st.divider()
    st.subheader("🔭 Novità dal mondo crypto", anchor=False)
    st.caption("Notizie pubbliche in tempo reale (Google News) sul mondo **crypto**: nuove crypto e listing, "
               "Stati e regolatori che approvano o vietano, ETF e mosse istituzionali, e i tuoi asset "
               "(Solana, Worldcoin). **Spunti, non consigli finanziari**.")
    if st.button("🔄 Aggiorna news", key="cry_news_refresh"):
        _carica_crypto_news.clear()
    try:
        with st.spinner("Cerco notizie crypto…"):
            temi = _carica_crypto_news()
    except Exception:
        temi = []
    _render_temi(temi)


def _hist_total_at(hist, date):
    v = 0.0
    for e in sorted(hist, key=lambda x: x["date"]):
        if e["date"] <= date:
            v = e["total"]
        else:
            break
    return v


def render_overview(doc):
    stk = doc
    cry = doc.get("crypto", {}) or {}
    rows_s, tot_s = compute(stk)
    rows_c, tot_c = compute(cry)
    init = tot_s["init"] + tot_c["init"]
    now = tot_s["now"] + tot_c["now"]
    pl = now - init
    plpct = (pl / init * 100) if init else 0.0

    tot_all = {"iniz": tot_s["iniz"] + tot_c["iniz"], "add": tot_s["add"] + tot_c["add"],
               "init": init, "now": now, "pl": pl, "plpct": plpct}
    st.markdown(hero_html("Il tuo portafoglio vale", tot_all, "azioni 29/05 · crypto 26/06"),
                unsafe_allow_html=True)

    def _refresh_all():
        prices.update_prices_in_data(doc, log=lambda *_: None)
        if isinstance(doc.get("crypto"), dict) and doc["crypto"].get("holdings"):
            prices.update_prices_in_data(doc["crypto"], log=lambda *_: None)
        save_data(doc)
    price_bar(doc.get("last_update", ""), "all_refresh", _refresh_all)

    # --- azioni vs crypto: due schede affiancate + barra ---
    st.markdown("<div class='sec'>⚖️ Azioni e crypto</div>", unsafe_allow_html=True)
    ws = (tot_s["now"] / now * 100) if now else 0
    wc = 100 - ws if now else 0
    split = (
        "<div class='splitbar'>"
        f"<div style='width:{ws:.1f}%;background:#2446c8'></div>"
        f"<div style='width:{wc:.1f}%;background:#c76a00'></div></div>"
        "<div class='split'>")
    for label, tot, w, col in [("📈 Azioni", tot_s, ws, "#2446c8"), ("🪙 Crypto", tot_c, wc, "#c76a00")]:
        cls = "pos" if tot["plpct"] >= 0 else "neg"
        split += (f"<div class='scard' style='border-top:4px solid {col}'>"
                  f"<div class='s-lab'>{label} <span>{num1(w)}%</span></div>"
                  f"<div class='s-val'>{eur(tot['now'])}</div>"
                  f"<div class='s-sub'>messi {eur(tot['init'])} · <span class='chg {cls}'>{pct(tot['plpct'])}</span></div>"
                  "</div>")
    st.markdown(split + "</div>", unsafe_allow_html=True)

    # --- tutte le posizioni ---
    st.markdown("<div class='sec'>🧾 Tutte le posizioni</div>", unsafe_allow_html=True)
    allr = [(r, "Azioni", "#2446c8") for r in rows_s] + [(r, "Crypto", "#c76a00") for r in rows_c]
    allr.sort(key=lambda x: -x[0]["valore"])
    body, cards = "", ""
    for r, cls, col in allr:
        w = (r["valore"] / now * 100) if now else 0
        pill = f"<span class='pill' style='background:{col}1f;color:{col}'>{cls}</span>"
        body += (f"<tr><td>{r['Titolo']}</td><td style='text-align:left'>{pill}</td>"
                 f"<td>{eur(r['investito'])}</td><td><b>{eur(r['valore'])}</b></td>"
                 f"<td>{num1(w)}%</td><td>{vspan(r['var'])}</td></tr>")
        cards += pcard(r["Titolo"], col, r["valore"], r["var"],
                       f"{cls} · {num1(w)}% del totale")
    st.markdown(
        "<div class='dtbl'><div class='tblwrap'><table class='ptbl'><thead><tr><th>Titolo</th><th>Classe</th>"
        "<th>Messi in tutto</th><th>Valore attuale</th><th>Peso</th><th>Variazione</th></tr></thead>"
        f"<tbody>{body}</tbody></table></div></div>"
        f"<div class='mcards'>{cards}</div>", unsafe_allow_html=True)
    st.divider()

    # --- andamento totale combinato ---
    st.markdown("<div class='sec'>📈 Andamento totale (azioni + crypto)</div>", unsafe_allow_html=True)
    h_s = stk.get("history", []) or []
    h_c = cry.get("history", []) or []
    # le crypto contano al loro valore iniziale gia' dall'inizio dello storico azioni:
    # cosi' l'inserimento di oggi NON crea un falso aumento, si vede solo la crescita reale.
    cry_base = sum(float(h.get("iniziale", 0)) for h in cry.get("holdings", []))

    def _cry_at(d):
        v = None
        for e in sorted(h_c, key=lambda x: x["date"]):
            if e["date"] <= d:
                v = e["total"]
            else:
                break
        return v if v is not None else cry_base

    dates = sorted(set([e["date"] for e in h_s] + [e["date"] for e in h_c]))
    merged = [{"date": d, "total": round(_hist_total_at(h_s, d) + _cry_at(d))} for d in dates]
    lu = stk.get("last_update") or (merged[-1]["date"] if merged else None)
    if lu:
        merged = [m for m in merged if m["date"] != lu] + [{"date": lu, "total": round(now)}]
        merged.sort(key=lambda x: x["date"])
    if len(merged) >= 2:
        hpts = pd.DataFrame([{"data": pd.to_datetime(m["date"]), "valore": m["total"]} for m in merged])
        vmax = hpts["valore"].max()
        hi = max(5000, -(-int(vmax) // 1000) * 1000)
        ticks = list(range(0, hi + 1000, 1000))
        chart = (alt.Chart(hpts)
                 .mark_line(point=alt.OverlayMarkDef(color="#0f7a3d", size=55), color="#0f7a3d", strokeWidth=2.5)
                 .encode(
                     x=alt.X("data:T", sort="ascending", title=None,
                             axis=alt.Axis(format="%d/%m", labelColor="#475569", grid=False)),
                     y=alt.Y("valore:Q", title="€", scale=alt.Scale(domain=[0, hi]),
                             axis=alt.Axis(values=ticks, labelColor="#475569", titleColor="#475569", gridColor="#e3e6ef")),
                     tooltip=[alt.Tooltip("data:T", title="Data", format="%d/%m/%Y"),
                              alt.Tooltip("valore:Q", title="Totale €", format=",.0f")])
                 .properties(height=300).configure_view(strokeOpacity=0))
        st.altair_chart(chart, use_container_width=True)
    else:
        st.caption("Il grafico combinato crescerà a ogni aggiornamento dei prezzi.")
    st.caption("Somma di azioni (Yahoo Finance) e crypto (CoinGecko). Le crypto sono conteggiate al loro "
               "valore iniziale fin dall'inizio: il grafico mostra la **crescita reale** degli asset, non "
               "l'effetto dell'averle inserite oggi.")


tab_all, tab_stk, tab_cry = st.tabs(["🏠 Riepilogo", "📈 Azioni", "🪙 Crypto"])
with tab_stk:
    render_dashboard(doc, doc, "stk")
    render_stock_news()
with tab_cry:
    render_dashboard(doc["crypto"], doc, "cry")
    render_staking_projection(doc["crypto"])
    render_crypto_news()
with tab_all:
    render_overview(doc)

st.divider()
st.caption("🔒 Accesso privato: solo le persone invitate via email e in possesso della password possono "
           "vedere e modificare questa dashboard. I tuoi dati sono conservati in un archivio privato.")
