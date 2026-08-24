# Model zagrożeń STRIDE + plan reakcji

Zakres: backend API, worker ingestu, panel admina, kanały danych, aplikacje klientów.

| Element | S (Spoofing) | T (Tampering) | R (Repudiation) | I (Info disclosure) | D (DoS) | E (Elevation) |
|---|---|---|---|---|---|---|
| Kanały danych (RSS/WWW instytucji) | DNS hijack / fałszywa domena → `domain_pin` + TLS pinning + walidacja treści | Modyfikacja treści w tranzycie → HTTPS + hash treści w `raw_messages` | — | — | Niedostępność źródła → health-check, baner w UI, brak interpretacji jako „brak zagrożenia" | — |
| Webhooki (przyszłość) | Podszycie nadawcy → podpis HMAC + timestamp anti-replay | — | — | — | Flood webhooków → limit per source | — |
| API publiczne | Brak kont ⇒ minimalna powierzchnia | — | — | Anonimowe zgłoszenia bez PII | Rate-limit (Redis token bucket), cache, WAF/CloudFront | — |
| Panel admina | Token/mTLS; pusty token = blokada | Korekty tylko z audytem before/after | `audit_log` append-only + actor | Osobna ścieżka `/admin-api`, IP allowlist, brak indeksowania | Limit prób, alert na nieudane logowania | RBAC: operator ≠ admin infra |
| Worker ingestu | Spoofing źródła wewn. → dedykowane konto DB z uprawnieniami INSERT-only poza audytem | Surowe dane immutable (brak UPDATE poza statusami) | Log każdej decyzji dedup/scoring | Raw payload zawiera treści publiczne — brak sekretów | Backoff + jitter; circuit breaker per źródło | Kontener non-root, read-only FS |
| Powiadomienia | Fałszywy push → podpisy serwera FCM/APNs, tokeny szyfrowane AES-GCM | — | Log wysyłek (`notification_log`) | Brak PII w treści push (tylko poziom+źródło+czas) | Token bucket 10/h/subskrypcja + scalanie | — |

## Priorytetowe ryzyka (spoza klasycznego STRIDE)

1. **Koordynowana dezinformacja** — patrz docs/04 (twarde reguły RED/korelacji).
2. **Przejęcie konta źródłowego** (np. kanał UA administracji):
   - detekcja: nagła zmiana stylu/tematyki + sprzeczność z drugim kanałem tej samej instytucji,
   - akcja: natychmiastowe `enabled=false` dla źródła, wycofanie zdarzeń wygenerowanych po czasie przejęcia (status_history), komunikat użytkownikom, ręczna weryfikacja.
3. **Compromise bazy**: szyfrowanie at-rest (disk/KMS), backupy szyfrowane, odtworzenie stanu (`state/replay` z audit_log).
4. **LLM abuse** (jeśli dodany do tłumaczeń): model nie ma uprawnień publikacji; jego output to propozycja do reguł.

## Rejestr kontrolny (minimum produkcyjne)

- [ ] mTLS/WAF przed `/admin-api`, IP allowlist
- [ ] rotacja `AIRALERT_ADMIN_API_TOKEN` (90 dni)
- [ ] Sentry + alerty Prometheus na: consecutive_failures>3, spike eventów 10x baseline
- [ ] backup PITR Postgres, test odtwarzania co miesiąc
- [ ] dependency scanning (pip-audit, npm audit) w CI
