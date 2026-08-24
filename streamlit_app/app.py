"""AirAlert Monitor — widok Streamlit (MVP read-only).

Reuzywa RDZEN logiki z backend/app (normalizacja, dedup, scoring, poziomy)
- moduly czysto funkcyjne, bez bazy danych.

TO NIE JEST OFICJALNY SYSTEM ALARMOWANIA.
Zagrozenie: dzwoń 112, stosuj sie do komunikatow RCB i wladz lokalnych.
"""
from __future__ import annotations

import os
import sys
import datetime as dt

import feedparser
import httpx
import streamlit as st

# --- dolaczenie rdzenia backendu ---
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO_ROOT, "backend"))

from app import DISCLAIMER_ALERT_FOOTER, DISCLAIMER_SHORT  # noqa: E402
from app.dedup.engine import match_against, ExistingEvent  # noqa: E402
from app.ingest.sources import SEEDS  # noqa: E402
from app.normalize.pipeline import canonical_text, content_hash, normalize  # noqa: E402
from app.scoring.alert_level import LevelInput, decide_level, global_level  # noqa: E402
from app.scoring.credibility import ScoreInput, compute_score, verification_status_for  # noqa: E402

st.set_page_config(page_title="AirAlert Monitor (demo)", page_icon="🛰️", layout="wide")

LEVEL_EMOJI = {"green": "🟢", "yellow": "🟡", "orange": "🟠", "red": "🔴"}
LEVEL_LABEL = {"green": "ZIELONY", "yellow": "ŻÓŁTY", "orange": "POMARAŃCZOWY", "red": "CZERWONY"}

# Zrodla automatyczne = wyłącznie legalne kanaly RSS.
AUTO_SOURCES = [s for s in SEEDS if s.ingest_kind == "rss"]


# ---------------------------------------------------------------- pobieranie
@st.cache_data(ttl=300, show_spinner=False)
def fetch_source(url: str, domain_pin: str) -> tuple[str, list[dict]]:
    """Pobiera RSS zrodel. Zwraca (status, wpisy). ttl=5 min - kultura wobec zrodel."""
    try:
        resp = httpx.get(
            url, timeout=15, follow_redirects=True,
            headers={"User-Agent": "AirAlertMonitor/0.1 (+public-data-monitoring)"},
        )
        resp.raise_for_status()
        host = resp.url.host or ""
        if domain_pin and not (host == domain_pin or host.endswith("." + domain_pin)):
            return f"spoofing? ({host})", []
        feed = feedparser.parse(resp.text)
        items = []
        for e in getattr(feed, "entries", [])[:20]:
            pub = e.get("published_parsed") or e.get("updated_parsed")
            items.append({
                "external_id": e.get("id") or e.get("link") or e.get("title", ""),
                "url": e.get("link"),
                "title": e.get("title", ""),
                "text": e.get("summary", "") or e.get("description", ""),
                "published_at": dt.datetime(*pub[:6], tzinfo=dt.timezone.utc) if pub else None,
            })
        return "ok", items
    except Exception as exc:  # noqa: BLE001
        return f"błąd: {str(exc)[:80]}", []


def collect() -> dict[str, list[dict]]:
    out = {}
    for s in AUTO_SOURCES:
        status, items = fetch_source(s.url, s.domain_pin)
        if status == "ok" and items:
            out[s.slug] = items
    return out


# ---------------------------------------------------------------- przetwarzanie
def process(store: list[dict], feeds: dict[str, list[dict]]) -> list[dict]:
    """Pelny cykl jak w backendzie: normalizacja -> dedup -> scoring -> poziom."""
    seeds = {s.slug: s for s in SEEDS}
    now = dt.datetime.now(dt.timezone.utc)
    known = [
        ExistingEvent(e["event_id"], e["title"], e["text"], e["event_type"],
                      e["published_at"], [l["name"].lower() for l in e["locations"]],
                      [l["source"] for l in e["links"]])
        for e in store
    ]
    for slug, items in feeds.items():
        src = seeds[slug]
        for it in items:
            norm = normalize(
                source_slug=slug, source_name=src.name, source_type=src.source_type,
                source_url=it["url"], trust_tier=src.trust_tier,
                external_id=it["external_id"], raw_payload={"title": it["title"]},
                title=it["title"], text=it["text"],
                published_at=it["published_at"] or now,
                fetched_at=now,
            )
            m = match_against(norm.title, norm.original_text, norm.content_hash_,
                              norm.event_type, norm.published_at, slug, known)
            if m.kind == "duplicate":
                continue
            if m.kind != "new":
                # dopisz jako zrodlo potwierdzajace do istniejacego zdarzenia
                for e in store:
                    if e["event_id"] == m.event_id:
                        e["links"].append({"source": slug, "type": src.source_type,
                                           "url": it["url"], "tier": src.trust_tier})
                        _rescore(e)
                        break
                continue
            ev = {
                "event_id": f"{slug}:{hashlib_short(norm.content_hash_)}",
                "title": norm.title, "text": norm.original_text,
                "language": norm.language, "event_type": norm.event_type,
                "published_at": norm.published_at, "url": it["url"],
                "locations": [{"name": l["name"], "voivodeship": l.get("voivodeship"),
                               "country": l["country"]} for l in norm.locations],
                "links": [{"source": slug, "type": src.source_type,
                           "url": it["url"], "tier": src.trust_tier}],
            }
            _rescore(ev)
            store.insert(0, ev)
            known.insert(0, ExistingEvent(
                ev["event_id"], ev["title"], ev["text"], ev["event_type"],
                ev["published_at"], [l["name"].lower() for l in ev["locations"]],
                [l["source"] for l in ev["links"]]))
    # retencja sesyjna: 24h
    cutoff = now - dt.timedelta(hours=24)
    return [e for e in store if e["published_at"] >= cutoff]


def _rescore(ev: dict) -> None:
    links = ev["links"]
    best = min(links, key=lambda l: l["tier"])
    independent = len({l["source"] for l in links})
    official = best["type"] in ("official_government", "official_military")
    score = compute_score(ScoreInput(
        trust_tiers=[l["tier"] for l in links], source_slugs=[l["source"] for l in links],
        has_location=bool(ev["locations"]), has_publish_time=True,
        has_original_link=bool(ev["url"]), officially_confirmed=official,
    ))
    vstatus = verification_status_for(
        source_type_max=best["type"], independent_sources=independent,
        officially_confirmed=official,
    )
    countries = sorted({l["country"] for l in ev["locations"]}) or ["other"]
    decision = decide_level(LevelInput(
        event_type=ev["event_type"],
        severity="moderate", urgency="routine",
        confidence=score.confidence, verification_status=vstatus,
        best_source_type=best["type"],
        best_source_country="PL" if best["source"] in {"rcb", "mon", "dorsz"} else "other",
        locations_countries=countries,
    ))
    ev.update(confidence=score.confidence, breakdown=score.as_dict(),
              verification=vstatus, level=decision.level, basis=decision.basis)


def hashlib_short(h: str) -> str:
    return h[:12]


# ---------------------------------------------------------------- UI
st.title("🛰️ AirAlert Monitor")
st.error(DISCLAIMER_SHORT, icon="⚠️")
st.caption("Widok Streamlit (MVP read-only). Dane prosto z publicznych kanałów źródeł "
           "— bez bazy, bez powiadomień. Pełna wersja: backend FastAPI w tym repo.")

if "store" not in st.session_state:
    st.session_state.store = []

left, right = st.columns([1, 4])
with left:
    if st.button("🔄 Odśwież dane", type="primary"):
        st.session_state.pop("feeds", None)
with right:
    st.caption(f"Ostatnie odświeżenie: {dt.datetime.now().strftime('%H:%M:%S')} · cache źródeł: 5 min")

if "feeds" not in st.session_state:
    with st.spinner("Pobieram publiczne komunikaty ze źródeł..."):
        st.session_state.feeds = collect()

st.session_state.store = process(st.session_state.store, st.session_state.feeds)
events = st.session_state.store

# ---- status globalny ----
lvl = global_level([e["level"] for e in events])
c1, c2, c3 = st.columns(3)
c1.metric("Status globalny", f"{LEVEL_EMOJI[lvl]} {LEVEL_LABEL[lvl]}")
fresh = any((dt.datetime.now(dt.timezone.utc) - e["published_at"]) < dt.timedelta(hours=6) for e in events)
c2.metric("Świeżość danych", "aktualne" if fresh else "brak świeżych wpisów",
          help="Brak danych NIE oznacza braku zagrożenia.")
c3.metric("Aktywne zdarzenia (24h)", len(events))

if not fresh:
    st.warning("**Brak aktualnych danych — sprawdź oficjalne kanały.** "
               "Nie interpretuj braku wpisów jako braku zagrożenia.")

# ---- zdrowie zrodel ----
with st.expander("Źródła i ich stan"):
    rows = []
    for s in AUTO_SOURCES:
        got = s.slug in st.session_state.feeds and len(st.session_state.feeds[s.slug]) > 0
        rows.append({"źródło": s.name, "typ": s.source_type,
                     "wpisów": len(st.session_state.feeds.get(s.slug, [])),
                     "stan": "ok" if got else "brak danych / niedostępne"})
    st.dataframe(rows, use_container_width=True, hide_index=True)

# ---- filtry ----
st.subheader("Oś zdarzeń")
f1, f2, f3, f4 = st.columns(4)
level_f = f1.multiselect("Poziom", list(LEVEL_LABEL), default=None,
                         format_func=lambda x: f"{LEVEL_EMOJI[x]} {LEVEL_LABEL[x]}")
type_f = f2.multiselect("Typ zdarzenia", sorted({e["event_type"] for e in events} or {"unknown"}))
conf_f = f3.slider("Min. pewność", 0.0, 1.0, 0.0, 0.05)
voiv_f = f4.multiselect("Województwo", sorted({l["voivodeship"] for e in events for l in e["locations"] if l.get("voivodeship")}))

filtered = events
if level_f:
    filtered = [e for e in filtered if e["level"] in level_f]
if type_f:
    filtered = [e for e in filtered if e["event_type"] in type_f]
if conf_f > 0:
    filtered = [e for e in filtered if e["confidence"] >= conf_f]
if voiv_f:
    filtered = [e for e in filtered if any(l.get("voivodeship") in voiv_f for l in e["locations"])]

# ---- mapa schematyczna (poziomy wg wojewodztw) ----
by_voiv: dict[str, str] = {}
order = {"green": 0, "yellow": 1, "orange": 2, "red": 3}
for e in events:
    for l in e["locations"]:
        v = l.get("voivodeship")
        if v and order.get(by_voiv.get(v, "green"), -1) < order[e["level"]]:
            by_voiv[v] = e["level"]
if by_voiv:
    st.markdown("**Województwa z aktywnymi zdarzeniami:**  " + "  ·  ".join(
        f"{LEVEL_EMOJI[lvl]} {v}" for v, lvl in sorted(by_voiv.items())))

# ---- karty zdarzen ----
for e in filtered[:30]:
    color = {"green": "🟢", "yellow": "🟡", "orange": "🟠", "red": "🔴"}[e["level"]]
    age_min = int((dt.datetime.now(dt.timezone.utc) - e["published_at"]).total_seconds() // 60)
    with st.container(border=True):
        st.markdown(
            f"### [{LEVEL_LABEL[e['level']]}] {color} {e['title']}  \n"
            f"**Obszar:** {', '.join(l['name'] for l in e['locations']) or 'nie określono'} · "
            f"**Publikacja:** {e['published_at'].strftime('%Y-%m-%d %H:%M UTC')} · "
            f"**Wiek:** {age_min} min  \n"
            f"**Źródła:** {' + '.join(sorted({l['source'] for l in e['links']})[:3])} · "
            f"**Weryfikacja:** {e['verification']} · **Pewność:** {round(e['confidence']*100)}%  \n"
            f"**Podstawa klasyfikacji:** {'; '.join(e['basis'])}"
        )
        col_a, col_b = st.columns([1, 6])
        if e["url"]:
            col_a.link_button("🔗 Otwórz źródło oryginalne", e["url"])
        with col_b:
            st.caption(DISCLAIMER_ALERT_FOOTER)

if not filtered:
    st.info("Brak zdarzeń spełniających filtry.")

st.divider()
st.markdown(
    "<sub>Monitoring publicznych komunikatów i wskaźników ryzyka. "
    "System klasyfikuje już opublikowane komunikaty — nie przewiduje ataków.</sub>",
    unsafe_allow_html=True,
)
