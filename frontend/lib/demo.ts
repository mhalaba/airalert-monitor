/**
 * TRYB DEMO - dane w pelni SYMULOWANE.
 * Sluzy wyłącznie prezentacji interfejsu na statycznym hostingu (GitHub Pages).
 * Zadne z tych zdarzen nie jest prawdziwe i zadne zrodlo nie zostalo odpytane.
 */
import type { EventItem, StatusResponse } from "./api";

const T = (minutesAgo: number) =>
  new Date(Date.now() - minutesAgo * 60_000).toISOString();

export const DEMO_STATUS: StatusResponse = {
  global_level: "orange",
  level_basis: [
    "DEMO: poziom wynika z symulowanego zdarzenia 'aktywność rakietowa' (UA, potwierdzone przez 2 niezależne źródła).",
  ],
  updated_at: T(2),
  data_age_minutes: 2,
  no_fresh_data: false,
  sources_health: [
    { slug: "rcb", name: "Rządowe Centrum Bezpieczeństwa", status: "ok" },
    { slug: "mon", name: "Ministerstwo Obrony Narodowej", status: "ok" },
    { slug: "dorsz", name: "Dowództwo Operacyjne RSZ", status: "degraded" },
    { slug: "psp", name: "Państwowa Straż Pożarna", status: "ok" },
    { slug: "policja", name: "Policja", status: "ok" },
    { slug: "ua-mod", name: "Міністерство оборони України", status: "ok" },
    { slug: "nato", name: "NATO Newsroom", status: "stale" },
    { slug: "telegram-manual", name: "Telegram (wpisy zatwierdzane ręcznie)", status: "disabled" },
  ],
  disclaimer:
    "[TRYB DEMO — DANE SYMULOWANE] To nie jest oficjalny system alarmowania. W sytuacji zagrożenia stosuj się do komunikatów RCB, władz lokalnych i służb państwowych.",
};

export const DEMO_EVENTS: EventItem[] = [
  {
    id: "demo-ua-1",
    event_type: "missile_activity",
    severity: "high",
    urgency: "elevated",
    confidence: 0.85,
    verification_status: "corroborated",
    language: "uk",
    title: "[SYMULACJA] Aktywność rakietowa nad obwodem lwowskim",
    original_text:
      "Повітряні сили повідомляють про роботу ворожої авіації та пуск ракет по західних областях. Слідкуйте за офіційними каналами. (treść symulowana)",
    published_at: T(18),
    updated_at: T(4),
    alert_level: "orange",
    alert_level_basis: [
      "Zdarzenie w pobliżu Polski (kontekst UA), potwierdzone przez ≥2 niezależne źródła lub instytucję (verification_status=corroborated).",
      "[DEMO] Dane wygenerowane na potrzeby prezentacji interfejsu.",
    ],
    confidence_breakdown: {
      confidence: 0.85, base: 0.65, corroboration_bonus: 0.2,
      official_confirmation_bonus: 0, conflict_penalty: 0, vagueness_penalty: 0,
      notes: ["[DEMO] Przykład działania przejrzystego scoringu."],
    },
    status: "active",
    locations: [
      { name: "Lwowski", country: "UA", voivodeship: null, powiat: null, precision: "region" },
    ],
    sources: [
      { source_name: "ua-mod", source_type: "official_military", source_url: null,
        published_at: T(18), role: "primary", trust_tier: 2 },
      { source_name: "ua-dsns", source_type: "official_government", source_url: null,
        published_at: T(15), role: "corroborating", trust_tier: 2 },
    ],
    is_stale: false,
    disclaimer:
      "Informacja OSINT. Nie zastępuje komunikatów RCB, władz lokalnych ani służb. W przypadku bezpośredniego zagrożenia dzwoń pod 112 i stosuj się do oficjalnych poleceń.",
  },
  {
    id: "demo-tg-1",
    event_type: "airspace_incident",
    severity: "moderate",
    urgency: "routine",
    confidence: 0.38,
    verification_status: "single_source",
    language: "pl",
    title: "[SYMULACJA] Doniesienie o obiekcie w przestrzeni powietrznej (niezweryfikowane)",
    original_text:
      "Anonimowy kanał donosi o rzekomym obiekcie nad Podlasiem. Brak potwierdzenia instytucji. (treść symulowana)",
    published_at: T(41),
    updated_at: T(41),
    alert_level: "yellow",
    alert_level_basis: [
      "typ zdarzenia: airspace_incident; informacja z pojedynczego źródła.",
      "[DEMO] Przykład wpisu niskiej wiarygodności — nigdy nie podnosi poziomu do czerwonego.",
    ],
    confidence_breakdown: {
      confidence: 0.38, base: 0.4, corroboration_bonus: 0,
      official_confirmation_bonus: 0, conflict_penalty: 0, vagueness_penalty: -0.02,
      notes: ["Brak linku do oryginału: -0.02"],
    },
    status: "active",
    locations: [
      { name: "Podlaskie", country: "PL", voivodeship: "podlaskie", powiat: null, precision: "region" },
    ],
    sources: [
      { source_name: "telegram-manual", source_type: "telegram", source_url: null,
        published_at: T(41), role: "primary", trust_tier: 4 },
    ],
    is_stale: false,
    disclaimer:
      "Informacja OSINT. Nie zastępuje komunikatów RCB, władz lokalnych ani służb. W przypadku bezpośredniego zagrożenia dzwoń pod 112 i stosuj się do oficjalnych poleceń.",
  },
  {
    id: "demo-ex-1",
    event_type: "exercise",
    severity: "informational",
    urgency: "routine",
    confidence: 0.95,
    verification_status: "officially_confirmed",
    language: "pl",
    title: "[SYMULACJA] Zaplanowane ćwiczenia systemu ostrzegania",
    original_text:
      "W dniu jutrzejszym zaplanowano test ćwiczebnych komunikatów systemu wykrywania i alarmowania. (treść symulowana)",
    published_at: T(120),
    updated_at: T(90),
    alert_level: "green",
    alert_level_basis: [
      "Typ zdarzenia: ćwiczenie/zaplanowane działanie.",
      "[DEMO]",
    ],
    confidence_breakdown: {
      confidence: 0.95, base: 0.95, corroboration_bonus: 0,
      official_confirmation_bonus: 0, conflict_penalty: 0, vagueness_penalty: 0,
      notes: [],
    },
    status: "active",
    locations: [
      { name: "Pomorskie", country: "PL", voivodeship: "pomorskie", powiat: null, precision: "region" },
    ],
    sources: [
      { source_name: "rcb", source_type: "official_government", source_url: null,
        published_at: T(120), role: "primary", trust_tier: 1 },
    ],
    is_stale: false,
    disclaimer:
      "Informacja OSINT. Nie zastępuje komunikatów RCB, władz lokalnych ani służb. W przypadku bezpośredniego zagrożenia dzwoń pod 112 i stosuj się do oficjalnych poleceń.",
  },
];
