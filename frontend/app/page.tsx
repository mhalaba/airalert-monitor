"use client";

import { useEffect, useMemo, useState } from "react";
import AlertCard from "@/components/AlertCard";
import VoivodeshipMap from "@/components/VoivodeshipMap";
import { DEMO_MODE, DISCLAIMER_SHORT, EventItem, fetchEvents, fetchStatus, StatusResponse } from "@/lib/api";

const EVENT_TYPES = [
  ["", "wszystkie"],
  ["air_alert", "alert lotniczy"],
  ["missile_activity", "aktywność rakietowa"],
  ["airspace_incident", "incydent w przestrzeni powietrznej"],
  ["explosion", "eksplozja"],
  ["exercise", "ćwiczenia"],
  ["weather", "pogoda"],
] as const;

export default function Home() {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [events, setEvents] = useState<EventItem[]>([]);
  const [level, setLevel] = useState("");
  const [eventType, setEventType] = useState("");
  const [minConfidence, setMinConfidence] = useState(0);
  const [sourceTypeFilter, setSourceTypeFilter] = useState("");
  const [selectedVoivodeships, setSelectedVoivodeships] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        setStatus(await fetchStatus());
      } catch {
        setError("Brak połączenia z API — sprawdź oficjalne kanały.");
      }
    })();
  }, []);

  useEffect(() => {
    const params: Record<string, string> = {};
    if (level) params.level = level;
    if (eventType) params.event_type = eventType;
    if (sourceTypeFilter) params.source_type = sourceTypeFilter;
    if (minConfidence > 0) params.min_confidence = String(minConfidence);
    fetchEvents(params)
      .then((r) => setEvents(r.items))
      .catch(() => setError("Nie udało się pobrać zdarzeń."));
  }, [level, eventType, minConfidence, sourceTypeFilter]);

  // Poziom wojewodztwa = maksimum poziomow aktywnych zdarzen w tym wojewodztwie
  const levelByVoivodeship = useMemo(() => {
    const order: Record<string, number> = { green: 0, yellow: 1, orange: 2, red: 3 };
    const out: Record<string, string> = {};
    for (const ev of events) {
      for (const loc of ev.locations) {
        if (!loc.voivodeship) continue;
        const key = loc.voivodeship.toLowerCase();
        if ((order[out[key]] ?? -1) < order[ev.alert_level]) out[key] = ev.alert_level;
      }
    }
    return out;
  }, [events]);

  const visible = useMemo(
    () =>
      events.filter((ev) => {
        if (selectedVoivodeships.size === 0) return true;
        return ev.locations.some((l) => l.voivodeship && selectedVoivodeships.has(l.voivodeship.toLowerCase()));
      }),
    [events, selectedVoivodeships]
  );

  return (
    <main className="container">
      <h1>AirAlert Monitor</h1>
      {DEMO_MODE && (
        <div className="banner-demo">
          🎬 TRYB DEMO — wszystkie dane są <b>symulowane</b> wyłącznie na potrzeby
          prezentacji interfejsu. Żadne źródło nie zostało odpytane.
        </div>
      )}
      <p className="disclaimer">{DISCLAIMER_SHORT}</p>

      {status?.no_fresh_data && (
        <div className="banner-warn">Brak aktualnych danych — sprawdź oficjalne kanały.</div>
      )}
      {error && <div className="banner-warn">{error}</div>}

      <section className="status-panel">
        <span className={`global-level level-${status?.global_level ?? "green"}`}>
          Status globalny: {(status?.global_level ?? "green").toUpperCase()}
        </span>
        <span>
          Wiek danych:{" "}
          {status?.data_age_minutes != null ? `${status.data_age_minutes} min` : "brak danych"}
        </span>
        <details>
          <summary>Źródła ({status?.sources_health.length ?? 0})</summary>
          <ul>
            {status?.sources_health.map((s) => (
              <li key={s.slug}>
                {s.name}: <b>{s.status}</b>
              </li>
            ))}
          </ul>
        </details>
      </section>

      <section className="filters">
        <label>
          Poziom:
          <select value={level} onChange={(e) => setLevel(e.target.value)}>
            <option value="">dowolny</option>
            <option value="green">zielony</option>
            <option value="yellow">żółty</option>
            <option value="orange">pomarańczowy</option>
            <option value="red">czerwony</option>
          </select>
        </label>
        <label>
          Typ zdarzenia:
          <select value={eventType} onChange={(e) => setEventType(e.target.value)}>
            {EVENT_TYPES.map(([v, l]) => (
              <option key={v} value={v}>{l}</option>
            ))}
          </select>
        </label>
        <label>
          Min. pewność:
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={minConfidence}
            onChange={(e) => setMinConfidence(Number(e.target.value))}
          />
          {Math.round(minConfidence * 100)}%
        </label>
        <label>
          Typ źródła:
          <select value={sourceTypeFilter} onChange={(e) => setSourceTypeFilter(e.target.value)}>
            <option value="">wszystkie</option>
            <option value="official_government">oficjalne rządowe</option>
            <option value="official_military">oficjalne wojskowe</option>
            <option value="telegram">telegram</option>
            <option value="osint_channel">OSINT</option>
          </select>
        </label>
      </section>

      <section className="map-and-timeline">
        <VoivodeshipMap
          levelByVoivodeship={levelByVoivodeship}
          selected={selectedVoivodeships}
          onToggle={(id) => {
            const next = new Set(selectedVoivodeships);
            if (next.has(id)) {
              next.delete(id);
            } else {
              next.add(id);
            }
            setSelectedVoivodeships(next);
          }}
        />
        <div className="timeline">
          <h2>Oś zdarzeń (chronologicznie)</h2>
          {visible.length === 0 && <p>Brak zdarzeń spełniających filtry.</p>}
          {[...visible]
            .sort((a, b) => +new Date(b.published_at) - +new Date(a.published_at))
            .map((ev) => (
              <AlertCard key={ev.id} ev={ev} />
            ))}
        </div>
      </section>
    </main>
  );
}
