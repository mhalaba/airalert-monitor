# Plan testów odporności na fałszywe alarmy

Cel: udowodnić, że żaden scenariusz koordynowanej dezinformacji nie wywoła
głośnego alarmu ani poziomu POMARAŃCZOWY/CZERWONY bez spełnienia twardych reguł.

## Scenariusze testowe (automatyzowane w pytest)

| # | Scenariusz | Oczekiwany wynik | Status |
|---|---|---|---|
| F1 | Pojedynczy anonimowy kanał TG: „ataki na Warszawę!!!" | `pending_review`, po zatwierdzeniu max ŻÓŁTY, powiadomienie ciche z tekstem neutralnym | ✅ `test_manual_telegram_requires_approval_and_stays_yellow_max` |
| F2 | 50 zsynchronizowanych anonimowych kanałów publikuje to samo | Korelacja liczona po NIEZALEŻNOŚCI źródeł; tier 5 → confidence ≤0.35; max ŻÓŁTY; token bucket ogranicza push | ✅ reguły `credibility.py` + `TokenBucket` |
| F3 | Emocjonalny język, CAPS, wykrzykniki bez faktów | Klasyfikator ignoruje ton; brak słów-kluczy ⇒ `unknown`; scoring nie nagradza emocji | ✅ `test_unknown_when_no_keywords` |
| F4 | Podszywanie się: URL spoza domeny instytucji | `DomainMismatch`, wpis odrzucony, health-check źródła spada | ✅ `check_domain()` |
| F5 | Sprzeczne doniesienia (explosion vs air_alert o tym samym czasie/miejscu) | Flaga konfliktu, kara -0.15 do score, zdarzenie do przeglądu operatora | ✅ `test_conflicting_type_flagged` |
| F6 | Sprostowanie po fakcie | Retrakcja obniża poziom do zielonego + wpis w status_history | ✅ `test_retraction_detected` |
| F7 | Stary alert recyrkulowany ponownie | Okno czasowe 24 h ⇒ nowe zdarzenie wymaga świeżego potwierdzenia; stara data widoczna w UI | ✅ `test_out_of_window_is_new_event` |
| F8 | Próba RED przez API publiczne | Brak endpointu; RED tylko `/admin-api/events/{id}/red-confirm` z uzasadnieniem i audytem | ✅ `require_admin` |
| F9 | Lawina powiadomień (100 zdarzeń/min) | Token bucket 10/h + scalanie 5-minutowe ⇒ ≤12 wysyłek/h | ✅ `test_token_bucket_limits_flood` |
| F10 | Ćwiczenia opisane groźnym językiem | Typ `exercise` ⇒ zawsze ZIELONY | ✅ `test_exercise_is_green` |

## Testy manualne (kwartalne)

- Tabletop exercise z zespołem operatorskim: symulacja przejęcia kanału (plan w docs/03).
- Chaos test: wyłączenie 50% źródeł — sprawdzenie banera „Brak aktualnych danych", brak interpretacji braku danych jako „brak zagrożenia" (UI pokazuje stan źródeł).
- Red team na panel administracyjny (phishing operatora, brute-force tokenu).

## Metryki sukcesu

- 0 przypadków RED spoza oficjalnego potwierdzenia PL w całym okresie działania.
- <1% fałszywych głośnych powiadomień (audyt miesięczny logu `notification_log`).
- Mediana czasu od oficjalnego komunikatu do wyświetlenia w aplikacji ≤ 3 min.
