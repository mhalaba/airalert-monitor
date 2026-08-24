# Uruchomienie lokalne i wdrożenie produkcyjne

## A. Lokalnie (backend + testy)

```bash
# 1. Wymagany Python >= 3.10 (sprawdzono na 3.12)
cd backend
python3.12 -m venv .venv
./.venv/bin/pip install -e ".[test]"

# 2. Testy jednostkowe i integracyjne (SQLite in-memory, bez zależności zewn.)
./.venv/bin/python -m pytest tests/

# 3. Uruchom API (SQLite domyślnie; seed źródeł wykonuje się przy starcie)
./.venv/bin/uvicorn app.main:app --reload --port 8000

# 4. Sprawdź
curl -s localhost:8000/api/v1/status | head -c 400
open http://localhost:8000/docs
```

Zmienna środowiskowa `AIRALERT_ADMIN_API_TOKEN=...` odblokowuje `/admin-api`
(pusty/nieustawiony = panel administracyjny wyłączony — celowo).

## B. Lokalnie przez Docker Compose (Postgres+PostGIS, Redis, API, worker)

```bash
cp .env.example .env          # ustaw POSTGRES_PASSWORD i AIRALERT_ADMIN_API_TOKEN
docker compose up -d --build
docker compose logs -f api worker

# API:      http://localhost:8000/docs
# Frontend: http://localhost:3000
```

Schemat bazy (`backend/db/schema.sql`) aplikuje się automatycznie przy pierwszym
starcie kontenera Postgres.

## C. Frontend dev

```bash
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1 npm run dev   # port 3000
```

## D. Wdrożenie produkcyjne (checklist)

1. **Infrastruktura**: 2× app-node (API), 1× worker-node, managed Postgres 16 +
   PostGIS z PITR, managed Redis; load balancer + WAF/CDN przed API.
2. **Sekrety**: Vault/AWS Secrets Manager; `AIRALERT_ADMIN_API_TOKEN` rotowany
   co 90 dni; FCM server key tylko po stronie backendu.
3. **TLS**: certyfikaty ACME; HSTS; wymuszenie TLS 1.2+.
4. **Admin**: `/admin-api` wystawione TYLKO przez VPN/bastion lub IP allowlist;
   opcjonalnie mTLS.
5. **Obserwowalność**: Sentry (frontend+backend), Prometheus + Grafana
   (metryki: świeżość danych per źródło, liczba eventów/h, kolejka powiadomień),
   alerty do dyżurnego operatora.
6. **Backupy**: nightly full + WAL archiving; miesięczny test odtwarzania.
7. **CI/CD**: lint → testy → build obrazów → skan (pip-audit/npm audit) → deploy staging → smoke testy (`/api/v1/status`, health sources) → deploy prod (rolling).
8. **Skalowanie powiadomień**: worker notifikacji wsadowo (batch 500/s), scalanie
   5-minutowe chroni FCM/APNs przed lawiną.
9. **Replay stanu**: `audit_log` pozwala odtworzyć decyzje; snapshot bazy co godzinę
   do osobnego bucketa (retencja 30 dni).

## E. Pierwsze kroki operatorskie po wdrożeniu

```bash
# Ręczne dodanie wpisu Telegram (legalny tryb: operator wkleja link+tresc)
curl -X POST https://HOST/admin-api/messages/manual \
  -H "Authorization: Bearer $AIRALERT_ADMIN_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://t.me/przyklad/123","title":"...","text":"...","source_slug":"telegram-manual"}'

# Przeglad kolejki oczekujacych + zatwierdzenie
curl -H "Authorization: Bearer $TOKEN" .../admin-api/events/{id}/approve
```
