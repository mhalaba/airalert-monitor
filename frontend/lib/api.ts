export const DISCLAIMER_SHORT =
  "To nie jest oficjalny system alarmowania. W sytuacji zagrożenia stosuj się do komunikatów RCB, władz lokalnych i służb państwowych.";

export const DISCLAIMER_FOOTER =
  "Informacja OSINT. Nie zastępuje komunikatów RCB, władz lokalnych ani służb. W przypadku bezpośredniego zagrożenia dzwoń pod 112 i stosuj się do oficjalnych poleceń.";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

// Tryb demo (GitHub Pages): dane symulowane zamiast zapytan do API.
export const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === "1";

export interface Location {
  name: string;
  country: string;
  voivodeship?: string | null;
  powiat?: string | null;
  precision: string;
}

export interface SourceRef {
  source_name: string;
  source_type: string;
  source_url?: string | null;
  published_at?: string | null;
  role: string;
  trust_tier: number;
}

export interface EventItem {
  id: string;
  event_type: string;
  severity: string;
  urgency: string;
  confidence: number;
  verification_status: string;
  language: string;
  title: string;
  original_text: string;
  published_at: string;
  updated_at: string;
  alert_level: "green" | "yellow" | "orange" | "red";
  alert_level_basis: string[];
  status: string;
  locations: Location[];
  sources: SourceRef[];
  is_stale: boolean;
  disclaimer: string;
}

export interface StatusResponse {
  global_level: string;
  level_basis: string[];
  updated_at: string;
  data_age_minutes?: number | null;
  no_fresh_data: boolean;
  sources_health: { slug: string; name: string; status: string }[];
  disclaimer: string;
}

export async function fetchStatus(): Promise<StatusResponse> {
  if (DEMO_MODE) {
    const { DEMO_STATUS } = await import("./demo");
    return { ...DEMO_STATUS, updated_at: T(2), data_age_minutes: 2 };
  }
  const r = await fetch(`${API}/status`, { cache: "no-store" });
  if (!r.ok) throw new Error("status unavailable");
  return r.json();
}

export async function fetchEvents(params: Record<string, string>): Promise<{ items: EventItem[]; total: number }> {
  if (DEMO_MODE) {
    const { DEMO_EVENTS } = await import("./demo");
    let items = DEMO_EVENTS;
    if (params.level) items = items.filter((e) => e.alert_level === params.level);
    if (params.event_type) items = items.filter((e) => e.event_type === params.event_type);
    if (params.min_confidence)
      items = items.filter((e) => e.confidence >= Number(params.min_confidence));
    if (params.source_type)
      items = items.filter((e) => e.sources.some((s) => s.source_type === params.source_type));
    return { items, total: items.length };
  }
  const qs = new URLSearchParams(params).toString();
  const r = await fetch(`${API}/events?${qs}`, { cache: "no-store" });
  if (!r.ok) throw new Error("events unavailable");
  return r.json();
}

const T = (minutesAgo: number) =>
  new Date(Date.now() - minutesAgo * 60_000).toISOString();

export async function reportError(eventId: string | null, category: string, message: string) {
  if (DEMO_MODE) return; // w demo nie zapisujemy zgloszen
  await fetch(`${API}/reports`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ event_id: eventId, category, message }),
  });
}