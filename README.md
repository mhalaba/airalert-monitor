# AirAlert Monitor

**Monitoring publicznych komunikatów i wskaźników ryzyka (OSINT)** dla terytorium Polski.

> ⚠️ **To nie jest oficjalny system alarmowania.** W sytuacji zagrożenia stosuj się do
> komunikatów RCB, władz lokalnych i służb państwowych. W bezpośrednim zagrożeniu dzwoń **112**.

## 🎬 Live demo (GitHub Pages)

Interfejs z danymi **w pełni symulowanymi**: https://mhalaba.github.io/airalert-monitor/

Demo działa w trybie statycznym (`NEXT_PUBLIC_DEMO_MODE=1`) — nie odpytuje żadnych źródeł,
pokazuje wyłącznie prezentację UI: mapę, karty alertów, scoring, filtry.

## 🐍 Wariant Streamlit (`streamlit_app/`)

Lekki widok **read-only** działający na [Streamlit Community Cloud](https://share.streamlit.io):
pobiera publiczne RSS źródeł na żywo i przetwarza je **tym samym rdzeniem logiki**
(normalizacja → dedup → scoring → poziomy) co backend FastAPI — moduły `app.normalize`,
`app.dedup`, `app.scoring` są czysto funkcyjne i reużyte 1:1.

Ograniczenia wariantu: brak bazy/powiadomień/panelu admina; stan sesyjny (24 h).
Deploy: share.streamlit.io → *New app* → repo `mhalaba/airalert-monitor` → main → `streamlit_app/app.py`.

## Co robi (i czego nie robi)

| Robi | Nie robi |
|---|---|
| Agreguje publiczne komunikaty instytucji PL/UA/NATO z legalnych kanałów | Nie przewiduje ataków ani tras pocisków |
| Normalizuje, deduplikuje i ocenia wiarygodność (jawna formuła) | Nie zastępuje RCB / 112 / służb |
| Prezentuje zdarzenia z poziomami ZIELONY–CZERWONY + pełną podstawą klasyfikacji | Nie podnosi CZERWONEGO na podstawie Telegramu — tylko po potwierdzeniu władz PL |
| Zapisuje surowe kopie komunikatów do audytu | Nie pobiera danych prywatnych; bez kont, bez GPS |

Szybki start: `make install && make test && make run` (szczegóły: `docs/07`).

## CI/CD

- **CI** (`.github/workflows/ci.yml`) — testy backendu przy każdym push/PR.
- **Demo** (`.github/workflows/deploy-pages.yml`) — statyczny build frontendu
  w trybie demo i deploy na GitHub Pages.

## Struktura repozytorium

```
docs/
  01-ryzyka-prawne-techniczne-operacyjne.md   # ryzyka PRZED kodem (wymóg projektu)
  02-architektura-i-api.md                    # architektura + kontrakty API v1
  03-model-zagrozen-stride.md                 # STRIDE + plan reakcji na przejęcie konta
  04-plan-testow-falszywe-alarmy.md           # scenariusze F1-F10 (automatyzowane)
  05-retencja-i-prywatnosc.md                 # retencja, RODO, minimalizacja danych
  06-ograniczenia-systemu.md                  # jawne ograniczenia - obowiązkowa lektura
  07-uruchomienie-i-wdrozenie.md              # local dev + produkcja
backend/          # FastAPI + SQLAlchemy (ingest, normalizacja, dedup, scoring, API)
  app/normalize/    # klasyfikator typow zdarzen, geolokalizacja administracyjna
  app/dedup/        # SimHash, okno czasowe, retrakcje, konflikty
  app/scoring/      # wiarygodnosc (breakdown) + reguly poziomow (RED tylko tier-1 PL)
  app/api/          # publiczne (read-only) + admin (token, audyt)
  db/schema.sql     # PostgreSQL 16 + PostGIS
  tests/            # 40 testow jednostkowych i integracyjnych
frontend/         # Next.js 14: mapa schematyczna wojewodztw, karta alertu wg specyfikacji
docker-compose.yml# Postgres+PostGIS, Redis, API, worker, web
```

## Kluczowe zasady bezpieczeństwa treści (wbudowane w kod)

1. **CZERWONY wyłącznie po oficjalnym potwierdzeniu polskich władz/służb**
   (`app/scoring/alert_level.py`) — doniesienia TG/OSINT max ŻÓŁTY/POMARAŃCZOWY.
2. **Telegram tylko ręcznie** — operator dodaje link+tresc przez `/admin-api/messages/manual`,
   wpis trafia do kolejki `pending_review`.
3. **Anti-spoofing** — `domain_pin` per źródło; treść spoza oczekiwanej domeny = odrzucenie.
4. **Jawny scoring** — każde zdarzenie publikuje `confidence_breakdown` i `alert_level_basis`
   ("Co wiadomo / Czego nie potwierdzono").
5. **Powiadomienia**: głośne tylko dla oficjalnych; nieoficjalne zawsze ciche z tekstem
   „Niezweryfikowana informacja do sprawdzenia"; scalanie 5 min + limit 10/h.
6. **Stopka OSINT z 112** na każdym alercie; baner „Brak aktualnych danych" przy awarii źródeł;
   brak danych nigdy nie jest interpretowany jako „brak zagrożenia".

## Status projektu

MVP referencyjne: backend kompletny i przetestowany (40 testów), frontend jako
implementacja wzorcowa. Przed produkcją wymagane (patrz `docs/01`): podmiot prawny,
kontakt z instytucjami ws. kanałów, audyt bezpieczeństwa, adaptory produkcyjne dla
konkretnych stron instytucji oraz granice PRG/GUGiK na mapie.
