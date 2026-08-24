"use client";

/**
 * Mapa SCHEMATYCZNA wojewodztw (MVP offline).
 * PRODUKCJA: podmienic na granice urzedowe z PRG/GUGiK (dane otwarte, CC-BY 4.0)
 * renderowane np. przez react-simple-maps / deck.gl.
 * Zasada: poziom wojewodztwa/powiatu, bez falszywej precyzji - brak punktow dla
 * obiektow wojskowych i infrastruktury krytycznej.
 */

const LEVEL_COLORS: Record<string, string> = {
  red: "#c62828",
  orange: "#ef6c00",
  yellow: "#f9a825",
  green: "#2e7d32",
};

// Uproszczone prostokatne uklady - wylacznie schemat pogladowy.
const VOIVODESHIPS: { id: string; label: string; x: number; y: number; w: number; h: number }[] = [
  { id: "pomorskie", label: "pomorskie", x: 150, y: 20, w: 90, h: 55 },
  { id: "zachodniopomorskie", label: "zach.-pom.", x: 45, y: 15, w: 95, h: 60 },
  { id: "warminsko-mazurskie", label: "warmińsko-maz.", x: 255, y: 25, w: 110, h: 55 },
  { id: "kujawsko-pomorskie", label: "kujawsko-pom.", x: 160, y: 85, w: 100, h: 50 },
  { id: "podlaskie", label: "podlaskie", x: 275, y: 90, w: 90, h: 60 },
  { id: "lubuskie", label: "lubuskie", x: 40, y: 85, w: 80, h: 50 },
  { id: "wielkopolskie", label: "wielkopolskie", x: 130, y: 145, w: 105, h: 65 },
  { id: "lodzkie", label: "łódzkie", x: 245, y: 155, w: 75, h: 60 },
  { id: "mazowieckie", label: "mazowieckie", x: 235, y: 225, w: 115, h: 70 },
  { id: "dolnoslaskie", label: "dolnośląskie", x: 60, y: 200, w: 95, h: 70 },
  { id: "opolskie", label: "opolskie", x: 120, y: 280, w: 60, h: 40 },
  { id: "slaskie", label: "śląskie", x: 190, y: 290, w: 65, h: 55 },
  { id: "swietokrzyskie", label: "świętokrz.", x: 265, y: 300, w: 75, h: 45 },
  { id: "podkarpackie", label: "podkarpackie", x: 350, y: 295, w: 95, h: 65 },
  { id: "malopolskie", label: "małopolskie", x: 260, y: 355, w: 90, h: 50 },
  { id: "lubelskie", label: "lubelskie", x: 360, y: 370, w: 90, h: 60 },
];

export default function VoivodeshipMap({
  levelByVoivodeship,
  selected,
  onToggle,
}: {
  levelByVoivodeship: Record<string, string>;
  selected: Set<string>;
  onToggle?: (id: string) => void;
}) {
  return (
    <div>
      <svg viewBox="0 0 480 440" role="img" aria-label="Mapa schematyczna województw">
        <rect width="480" height="440" fill="transparent" />
        {VOIVODESHIPS.map((v) => {
          const level = levelByVoivodeship[v.id] ?? "green";
          const isSel = selected.has(v.id);
          return (
            <g key={v.id} onClick={() => onToggle?.(v.id)} style={{ cursor: "pointer" }}>
              <rect
                x={v.x}
                y={v.y}
                width={v.w}
                height={v.h}
                rx={10}
                fill={LEVEL_COLORS[level]}
                opacity={selected.size === 0 || isSel ? 1 : 0.35}
                stroke={isSel ? "#000" : "#fff"}
                strokeWidth={isSel ? 3 : 1}
              />
              <text
                x={v.x + v.w / 2}
                y={v.y + v.h / 2}
                textAnchor="middle"
                fontSize={11}
                fill="#fff"
                style={{ pointerEvents: "none" }}
              >
                {v.label}
              </text>
            </g>
          );
        })}
      </svg>
      <p className="hint">Mapa schematyczna (poglądowa). Produkcja: granice PRG/GUGiK.</p>
      <div className="legend">
        {Object.entries(LEVEL_COLORS).map(([lvl, color]) => (
          <span key={lvl}>
            <i style={{ background: color }} /> {lvl}
          </span>
        ))}
      </div>
    </div>
  );
}
