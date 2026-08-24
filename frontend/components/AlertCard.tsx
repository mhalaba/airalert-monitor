"use client";

import { reportError } from "@/lib/api";
import { DISCLAIMER_FOOTER, EventItem } from "@/lib/api";

const LEVEL_LABEL: Record<string, string> = {
  red: "CZERWONY",
  orange: "POMARAŃCZOWY",
  yellow: "ŻÓŁTY",
  green: "ZIELONY",
};

const VERIFICATION_LABEL: Record<string, string> = {
  officially_confirmed: "oficjalnie potwierdzone",
  corroborated: "potwierdzone przez wiele źródeł",
  single_source: "pojedyncze źródło",
  unverified: "niezweryfikowane",
};

function fmt(iso: string): string {
  return new Date(iso).toLocaleString("pl-PL");
}

function ageMinutes(updatedAt: string): number {
  return Math.floor((Date.now() - new Date(updatedAt).getTime()) / 60000);
}

export default function AlertCard({ ev }: { ev: EventItem }) {
  const primary = ev.sources.find((s) => s.role === "primary") ?? ev.sources[0];
  const confirmedWhat = ev.alert_level_basis.filter((b) => !b.startsWith("Brak"));
  const notConfirmed = [
    !ev.locations.length ? "lokalizacja" : null,
    ev.verification_status === "unverified" ? "autentyczność zdarzenia (brak potwierdzenia instytucji)" : null,
    ev.verification_status !== "officially_confirmed" ? "oficjalne potwierdzenie władz" : null,
  ].filter(Boolean) as string[];

  return (
    <article className={`alert-card level-${ev.alert_level}`} aria-label={ev.title}>
      <header>
        <span className="level-badge">[{LEVEL_LABEL[ev.alert_level] ?? ev.alert_level}]</span>
        <h2>{ev.title}</h2>
      </header>

      <dl>
        <dt>Obszar:</dt>
        <dd>{ev.locations.map((l) => l.name).join(", ") || "nie określono"}</dd>

        <dt>Czas publikacji:</dt>
        <dd>{fmt(ev.published_at)}</dd>

        <dt>Źródło:</dt>
        <dd>{primary?.source_name ?? "—"}</dd>

        <dt>Status weryfikacji:</dt>
        <dd>{VERIFICATION_LABEL[ev.verification_status] ?? ev.verification_status}</dd>

        <dt>Poziom pewności:</dt>
        <dd>{Math.round(ev.confidence * 100)}%</dd>

        <dt>Co wiadomo:</dt>
        <dd>
          {confirmedWhat.length
            ? confirmedWhat.join(" ")
            : "Tylko treść komunikatu źródłowego — brak dodatkowych ustaleń."}
        </dd>

        <dt>Czego nie potwierdzono:</dt>
        <dd>{notConfirmed.length ? notConfirmed.join("; ") : "—"}</dd>

        <dt>Ostatnia aktualizacja:</dt>
        <dd>
          {fmt(ev.updated_at)}{" "}
          <em className="age">
            ({ageMinutes(ev.updated_at)} min temu{ev.is_stale ? " — DANE NIEAKTUALNE" : ""})
          </em>
        </dd>
      </dl>

      {ev.is_stale && <p className="stale-warning">⚠️ Dane starsze niż próg świeżości.</p>}

      <div className="actions">
        {primary?.source_url && primary.source_url.startsWith("http") && (
          <a href={primary.source_url} target="_blank" rel="noopener noreferrer nofollow">
            Otwórz źródło oryginalne
          </a>
        )}
        <button onClick={() => void reportError(ev.id, "wrong_classification", "")}>
          Zgłoś błąd w klasyfikacji
        </button>
      </div>

      <footer className="disclaimer">{DISCLAIMER_FOOTER}</footer>
    </article>
  );
}
