# Architektura systemu

## 0. Nazwa i charakter systemu

**AirAlert Monitor** — monitoring publicznych komunikatów i wskaźników ryzyka.
System agreguje publiczne komunikaty instytucji, normalizuje je, ocenia wiarygodność
i prezentuje użytkownikowi z pełnym audytowalnym łańcuchem pochodzenia danych.

> To nie jest oficjalny system alarmowania. W sytuacji zagrożenia stosuj się do
> komunikatów RCB, władz lokalnych i służb państwowych. W bezpośrednim zagrożeniu dzwoń 112.

## 1. Widok ogólny

```
┌───────────────────────────  ŹRÓDŁA (legalne kanały) ──────────────────────────┐
│ RSS/HTML gov.pl • RCB • MON • DORsz/DGRsz • PSP • Policja                     │
│ UA: Ministerstwa, DSNS, administracje obwodowe (oficjalne publikacje)         │
│ NATO/EU komunikaty publiczne                                                  │
│ Telegram: TYLKO ręczne zatwierdzanie przez operatora (link do oryginału)      │
└──────────────┬────────────────────────────────────────────────────────────────┘
               │  fetch (HTTP, rate-limit, retry+backoff, health-check)
┌──────────────▼──────────────┐
│  MODUŁ POBIERANIA (ingest)  │  → raw_messages (surowa kopia JSONB, audyt)
└──────────────┬──────────────┘
┌──────────────▼──────────────┐
│  NORMALIZACJA               │  → model kanoniczny (event_type, lokalizacje,
│  tłumaczenie, geo, klasyf.  │    severity/urgency wstępnie, processing_notes)
└──────────────┬──────────────┘
┌──────────────▼──────────────┐        ┌──────────────────────────────┐
│  DEDUPLIKACJA / KORELACJA   │◄──────►│  REJESTR ŹRÓDEŁ (tier zaufania)│
│  SimHash + okno czasowe     │        └──────────────────────────────┘
└──────────────┬──────────────┘
┌──────────────▼──────────────┐
│  OCENA WIARYGODNOŚCI        │  confidence 0..1 + verification_status
│  + POZIOMY alertu           │  GREEN/YELLOW/ORANGE (+RED wg reguły tier-1 PL)
└──────────────┬──────────────┘
       ┌───────┴────────┬──────────────────┐
┌──────▼─────┐  ┌───────▼──────┐  ┌────────▼─────────┐
│ API FastAPI│  │ POWIADOMIENIA│  │ PANEL ADMINA      │
│ (read-only)│  │ FCM/APNs     │  │ kolejka, korekty, │
│            │  │ rate-limit   │  │ dziennik audytu   │
└──────┬─────┘  └──────────────┘  └───────────────────┘
┌──────▼──────────────────────────────────────────────┐
│ FRONTEND (Next.js): mapa województw, oś zdarzeń,     │
│ filtry, status globalny, disclaimer                  │
└──────────────────────────────────────────────────────┘
```

## 2. Komponenty

| Komponent | Technologia | Odpowiedzialność |
|---|---|---|
| `ingest` | Python/FastAPI worker | pobieranie z oficjalnych kanałów, retry, health |
| `normalize` | worker | model kanoniczny, geokodowanie administracyjne, klasyfikacja typów zdarzeń |
| `dedup` | worker | scalanie duplikatów, korelacja źródeł, wykrywanie odwołań/korekt |
| `scoring` | worker | confidence score (przejrzysty wzór), poziomy alertu |
| `api` | FastAPI | odczyt publiczny, zgłoszenia błędów, admin (ograniczony) |
| `notifier` | worker | FCM/APNs, scalanie, limity, domyślne wyciszenie nieoficjalnych |
| `db` | PostgreSQL 16 + PostGIS | dane + geometrie województw/powiatów |
| `cache` | Redis | cache odpowiedzi API, token bucket powiadomień, kolejka zdarzeń (Streams) |
| `web` | Next.js 14 | UI |
| `mobile` | Flutter (faza 2) | push, wybór województw |
| `observability` | Prometheus + Grafana + Sentry | metryki, alerty operatorskie |

## 3. Przepływ zdarzenia (happy path)

1. **Fetch**: scheduler uruchamia fetchera źródła → zapis `raw_messages` (JSONB oryginału, hash treści).
2. **Normalize**: parsowanie daty/treści/języka → klasyfikacja `event_type` (reguły słownikowe) → ekstrakcja lokalizacji (słownik TERC województw/powiatów; precyzja = `region`/`city`/`approximate`) → zapis `events` ze statusem `pending_review`, jeśli źródło wymaga ręcznego zatwierdzenia.
3. **Dedup**: dopasowanie do istniejącego aktywnego zdarzenia (hash/SimHash ≥ próg, okno 24 h, nakładanie lokalizacji). Duplikat → dowiązanie jako corroborating source; sprzeczność → flaga konfliktu dla operatora.
4. **Score**: wyliczenie `confidence` (jawna formuła, szczegóły w `scoring/credibility.py`) i `verification_status`; wyznaczenie poziomu alertu z zapisaną podstawą (`alert_level_basis`).
5. **Publish**: zdarzenie widoczne w API/UI; notifier wysyła powiadomienia zgodnie z preferencjami (domyślnie cicho dla niezweryfikowanych).
6. **Lifecycle**: zdarzenie może przejść w `resolved` / `superseded` / `retracted`; historia zmian w `status_history`.

## 4. Kontrakty API (v1)

Wspólny nagłówek błędów: RFC 7807 (`application/problem+json`). Paginacja: `?limit=50&offset=0` (max 200).

### Publiczne

```
GET /api/v1/status
→ { "global_level": "green|yellow|orange|red",
    "level_basis": {...}, "updated_at": "...", "data_age_minutes": 4,
    "sources_health": [ {"slug":"rcb","status":"ok","last_success_at":"..."} ],
    "disclaimer": "To nie jest oficjalny system alarmowania..." }

GET /api/v1/events?level=&event_type=&source_type=&min_confidence=
              &voivodeship=&since=&limit=&offset=
→ { "items": [Event], "total": 123 }

GET /api/v1/events/{id}
→ Event (pełny, zawiera sources[], locations[], status_history[], confidence_breakdown)

POST /api/v1/reports   { "event_id": "...", "category": "wrong_classification|wrong_location|other",
                         "message": "..." }   # anonimowe, rate-limited
→ 202 { "id": "..." }

POST /api/v1/push/register  { "token": "<FCM/APNs>", "platform":"android|ios|web",
                              "voivodeships":["MAZOWIECKIE"], "min_level":"orange",
                              "official_only": true }
→ 201 { "subscription_id": "..." }

DELETE /api/v1/push/{subscription_id}   → 204
```

### Administracyjne (mTLS/JWT operatora, osobna ścieżka `/admin-api`, IP allowlist)

```
GET    /admin-api/sources                      → lista + health
PATCH  /admin-api/sources/{slug}               { enabled, trust_tier_override }
POST   /admin-api/messages/manual              { url, text, published_at }  # ręczny ingest (Telegram itp.)
POST   /admin-api/events/{id}/approve          # zwolnienie z kolejki pending_review
PATCH  /admin-api/events/{id}/corrections      { severity?, urgency?, event_type?, note }  # audytowane
POST   /admin-api/events/{id}/red-confirm      { justification }           # wymagane dla RED spoza reguły
GET    /admin-api/audit?from=&to=&actor=       → dziennik audytu
POST   /admin-api/state/replay                 { as_of }                   # odtworzenie stanu (dry-run)
```

### Model Event (kanoniczny) — zgodny ze specyfikacją użytkownika

Pola jak w wymaganiach + rozszerzenia:
`status`, `alert_level`, `alert_level_basis[]`, `confidence_breakdown{}`, `sources[]{source_name,source_type,source_url,published_at}`, `status_history[]`, `is_stale`, `disclaimer`.
