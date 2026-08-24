# Ograniczenia systemu — obowiązkowa lektura

## 1. Czego ten system NIE robi

1. **Nie przewiduje ataków.** Nie oblicza prawdopodobieństwa, tras pocisków ani celów.
   Wykrywa i klasyfikuje wyłącznie JUŻ opublikowane komunikaty i sygnały.
2. **Nie jest oficjalnym systemem alarmowania** i nie zastępuje RCB, 112,
   władz lokalnych ani służb.
3. **Nie gwarantuje kompletności** — agreguje tylko podłączone źródła; brak wpisu
   NIE oznacza braku zagrożenia.
4. **Nie gwarantuje czasu rzeczywistego** — typowe opóźnienie: od ~1 min (RSS tier-1)
   do interwału fetch danego źródła + czas normalizacji.
5. **Poziom CZERWONY** pojawia się wyłącznie po oficjalnym potwierdzeniu polskich
   władz/służb (lub ręcznym zatwierdzeniu operatora z audytem). Doniesienia
   Telegram/OSINT nigdy nie wywołają RED automatycznie.

## 2. Ograniczenia techniczne MVP

- Klasyfikacja `event_type` oparta na słownikach fraz (PL/UK/EN) — możliwe błędy
  przy nietypowych sformułowaniach; każde zdarzenie ma widoczne
  `matched_keywords` i podstawę klasyfikacji.
- Ekstrakcja lokalizacji działa na poziomie województw/powiatów PL oraz obwodów UA;
  precyzja nigdy nie sugeruje dokładnego punktu bez danych urzędowych.
- Tłumaczenie UK→PL: w MVP pomijane (`translated_text=null`); planowane przez
  usługę tłumaczeniową z oznaczeniem „tłumaczenie maszynowe".
- Deduplikacja SimHash może nie połączyć parafraz o niskim pokrewieństwie leksykalnym.
- Mapa w MVP jest schematyczna (poglądowa); produkcja: granice PRG/GUGiK.

## 3. Ograniczenia źródeł

- Telegram: TYLKO wpisy dodane ręcznie przez operatora (link do oryginału) lub
  legalne kanały udostępnione przez instytucję. Brak automatycznego pobierania.
- Air Alert (UA): brak publicznego API dla osób trzecich — integracja dopiero po
  uzyskaniu licencji/oficjalnego dostępu.
- Strony instytucji zmieniają strukturę HTML — adaptory wymagają utrzymania.

## 4. Znalezione błędy interpretacyjne, których się spodziewamy

- mylenie ćwiczeń z realnymi zdarzeniami (mitygacja: priorytet reguły `exercise`),
- duplikaty między kanałami cytującymi się nawzajem (mitygacja: niezależność
  źródeł liczona po slugach; docelowo graf własności mediów),
- opóźnienia sprostowań względem pierwotnej publikacji (mitygacja: retrakcje
  obniżają poziom natychmiast).

## 5. Komunikaty obowiązkowe

- Każdy alert kończy stopka OSINT z numerem 112.
- Gdy dane są starsze niż próg: „DANE NIEAKTUALNE".
- Gdy wszystkie źródła niedostępne: „Brak aktualnych danych — sprawdź oficjalne kanały".
