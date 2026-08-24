# Analiza ryzyk przed rozpoczęciem implementacji

> Projekt: monitoring publicznych komunikatów i wskaźników ryzyka (OSINT) dla terytorium Polski.
> Aplikacja NIE jest systemem alarmowym i nie zastępuje RCB, numeru 112 ani służb państwowych.

## 1. Ryzyka prawne

| # | Ryzyko | Opis | Mitygacja w projekcie |
|---|--------|------|-----------------------|
| P1 | Naruszenie regulaminu Telegram/X/Meta | Automatyczne pobieranie z kanałów Telegram przez klienta użytkownika (MTProto „user API") może naruszać ToS platformy. | Ingest wyłącznie przez: oficjalne RSS/API instytucji, webhooki, oraz **ręczne zatwierdzanie przez operatora** (operator wkleja link + treść; system przechowuje oryginał do audytu). Brak automatycznego scrapingu kanałów społecznościowych. |
| P2 | Brak licencjonowanego dostępu do danych Air Alert (UA) | Oficjalna aplikacja ukraińska nie udostępnia publicznego, udokumentowanego API dla osób trzecich. | Integracja tylko, jeśli pojawi się legalny interfejs lub umowa licencyjna. Do tego czasu źródła UA = oficjalne komunikaty prasowe/RSS ministerstw i administracji obwodowych. |
| P3 | Odpowiedzialność za błędną informację | Fałszywy lub opóźniony alert może prowadzić do szkód. | Obowiązkowy disclaimer na każdym alercie i ekranie; poziom CZERWONY wyłącznie po potwierdzeniu przez polskie władze; jawne rozdzielenie faktów / niepotwierdzonych doniesień; brak prognoz tras pocisków. |
| P4 | RODO | Przechowywanie tokenów push, ewentualnie lokalizacji. | Minimalizacja: bez konta, bez telefonu, lokalizacja tylko jako wybór województw po stronie urządzenia; tokeny push zaszyfrowane, z mechanizmem usunięcia; retencja ograniczona. |
| P5 | Prawa autorskie do treści źródłowych | Kopiowanie pełnych tekstów artykułów. | Przechowujemy pełny tekst wyłącznie jako surową kopię audytową (uzasadniony interes: weryfikacja integralności), a publicznie prezentujemy streszczenie + link do oryginału. |
| P6 | Ujawnienie informacji wrażliwych | Ryzyko opublikowania położenia wojsk/OPL. | Filtr wrażliwości na etapie publikacji (lista słów + reguły redakcyjne); geolokalizacja maksymalnie województwo/powiat; brak mapowania obiektów wojskowych. |
| P7 | Status prawny podmiotu | Kto odpowiada za serwis publiczny? | Wymagany podmiot operatora, regulamin, kontakt, procedury RODO; rekomendowany kontakt z RCB w sprawie wzajemnej informacyjnej kooperacji (linkowanie). |

## 2. Ryzyka techniczne

| # | Ryzyko | Opis | Mitygacja |
|---|--------|------|-----------|
| T1 | Awaria źródła / zmiana formatu | RSS/API przestanie działać lub zmieni schemat. | Health-check per źródło, `consecutive_failures`, alert operatorski, oznaczenie „źródło niedostępne" w UI. |
| T2 | Nieaktualne dane traktowane jak aktualne | Stare wpisy wyglądają jak bieżące. | Wiek danych widoczny w UI; próg świeżości; komunikat „Brak aktualnych danych — sprawdź oficjalne kanały". |
| T3 | Spoofing źródła | Podszycie się pod oficjalną instytucję. | Rejestr źródeł (whitelist) z pinowaniem domeny/klucza; podpisywanie webhooków; TLS + walidacja certyfikatu; brak możliwości dodania źródła przez publiczne API. |
| T4 | Lawina duplikatów | Jeden incydent = dziesiątki wpisów. | Deduplikacja (hash dokładny + SimHash + okno czasowe + nakładanie lokalizacji), scalanie do jednego zdarzenia z listą źródeł. |
| T5 | Fałszywe alarmy masowe (koordynowane) | Atak na percepcję: wiele anonimowych kanałów publikuje to samo. | Anonimowe kanały mają niski tier zaufania i nie podnoszą poziomu powyżej ŻÓŁTY; korelacja wymaga niezależności źródeł (różne domeny/właściciele); limity powiadomień. |
| T6 | LLM generujący treść alarmową | Model językowy mógłby „dopowiedzieć" fakty. | LLM (jeśli użyty) działa wyłącznie jako klasyfikator/tłumacz z zakazem generowania twierdzeń; jego wyjście trafia do kolejki oceny regułowej; żaden alert nie jest publikowany samodzielnie przez model. |
| T7 | Skalowanie powiadomień | Push do milionów urządzeń w sekundach. | Kolejka zdarzeń, wsadowa wysyłka FCM/APNs, okno scalające 5 min, token bucket per subskrypcja. |

## 3. Ryzyka operacyjne

| # | Ryzyko | Opis | Mitygacja |
|---|--------|------|-----------|
| O1 | Koszt dyżuru 24/7 | System o charakterze bezpieczeństwa wymaga nadzoru. | MVP: tryb „best effort" z jawną etykietą; panel administracyjny z kolejką zdarzeń oczekujących; eskalacja e-mail/SMS operatorom. |
| O2 | Przejęcie konta źródłowego | Haker przejmuje kanał instytucji i publikuje fałszywy komunikat. | Plan reakcji (docs/04): natychmiastowe zamrożenie źródła, wycofanie zdarzeń pochodnych, komunikat użytkownikowi, weryfikacja krzyżowa z drugim kanałem tej samej instytucji. |
| O3 | Nadmierne zaufanie użytkownika | Użytkownik traktuje aplikację jak oficjalną. | Stała, nietykalna stopka w każdym alercie i powiadomieniu; nazwa produktu nie zawiera słów sugerujących status urzędowy. |
| O4 | Operator wprowadza błąd ręcznie | Korekta klasyfikacji bez śladu. | Każda zmiana operatora w dzienniku audytu (before/after), możliwość odtworzenia stanu z dowolnego momentu. |

## 4. Decyzje projektowe wynikające z ryzyk

1. **MVP = agregacja oficjalnych źródeł PL** (RSS/HTML→parser z linkiem do oryginału) + ręczna kolejka zatwierdzania dla reszty.
2. **Telegram**: wyłącznie jako typ źródła `telegram` dodawany ręcznie przez operatora z linkiem do oryginalnego posta; brak automatycznego pobierania.
3. **Poziomy**: ZIELONY/ŻÓŁTY/POMARAŃCZOWY mogą być wyliczane automatycznie wg reguł; **CZERWONY tylko z tier-1 PL official + flaga `officially_confirmed`**; każda zmiana poziomu zapisuje podstawę klasyfikacji.
4. **Brak predykcji**: system klasyfikuje istniejące komunikaty; nie oblicza tras, celów ani prawdopodobieństwa ataku.
