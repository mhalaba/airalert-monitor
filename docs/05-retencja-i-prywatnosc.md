# Polityka retencji, prywatności i minimalizacji danych

## Retencja danych systemowych

| Dane | Retencja | Uzasadnienie |
|---|---|---|
| `raw_messages` (surowe kopie) | 180 dni, potem anonimizacja do samego hasha + URL | audyt integralności; po okresie treść publiczna i tak dostępna u źródła |
| `events` (zdarzenia) | bezterminowo (wartość historyczna/statystyczna), treść = streszczenie + link | analiza trendów; brak PII |
| `status_history` / `audit_log` | 3 lata | odpowiedzialność operatorska, replay stanu |
| `user_reports` | 90 dni | obsługa korekt; brak identyfikatorów użytkownika |
| `push_subscriptions` | usunięcie po 90 dniach bez kontaktu urządzenia (`last_seen_at`) | minimalizacja |
| `notification_log` | 30 dni | kontrola limitów i audyt fałszywych alarmów |
| logi aplikacji | 30 dni (bez treści komunikatów) | operacje |

Proces czyszczenia: zadanie cykliczne (cron/worker) usuwa wg tabeli powyżej;
usunięcia są zliczane w metrykach, ale nie tworzą wpisów z treścią.

## Prywatność użytkownika — zasady

1. **Brak wymaganego konta.** Aplikacja działa bez logowania.
2. **Nie zbieramy**: numeru telefonu, e-maila, dokładnej lokalizacji GPS, identyfikatorów reklamowych.
3. **Lokalizacja** = wyłącznie ręczny wybór województw przechowywany lokalnie na urządzeniu; na serwer trafia tylko lista województw w subskrypcji push.
4. **Token push** (FCM/APNs): jedyny identyfikator; szyfrowany AES-GCM kluczem serwera, usunięty natychmiast na żądanie (`DELETE /api/v1/push/{id}`) oraz automatycznie po 90 dniach nieaktywności.
5. **Zgłoszenia błędów** są anonimowe — prosimy nie wpisywać danych osobowych w polu opisu (informacja w UI).
6. **Prawa RODO**: dostęp/usunięcie realizowane przez podanie `subscription_id` (jedyny powiązany identyfikator); brak profilowania, brak sprzedaży danych, brak trackerów analitycznych stron trzecich.
7. **Minimalizacja w UI**: żadnych pikseli śledzących; metryki agregowane po stronie serwera bez identyfikatorów.

## Minimalizacja danych źródłowych

- Prezentujemy streszczenie + link; pełna kopia tekstowa tylko w warstwie audytowej.
- Nie publikujemy: danych osobowych występujących w komunikatach (maskowanie imion/nazwisk w podglądzie), zdjęć satelitarnych, pozycji wojskowych.
- Geokodowanie ograniczone do jednostek administracyjnych (województwo/powiat).
