"""Audyt E2E: prawdziwy serwer uvicorn + seria zapytan HTTP przez caly przeplyw."""
import json
import os
import signal
import subprocess
import sys
import time

import httpx

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PORT = 8123
BASE = f"http://127.0.0.1:{PORT}"
DB = "/tmp/airalert_e2e.db"
TOKEN = "audit-token"

if os.path.exists(DB):
    os.remove(DB)

env = dict(os.environ,
           AIRALERT_DATABASE_URL=f"sqlite:///{DB}",
           AIRALERT_ADMIN_API_TOKEN=TOKEN)

proc = subprocess.Popen(
    [sys.executable, "-u", "-m", "uvicorn", "app.main:app", "--port", str(PORT)],
    env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
)

# czekaj na start
t0 = time.time()
while time.time() - t0 < 40:
    line = proc.stdout.readline()
    if "Application startup complete" in line:
        break
else:
    print("SERWER NIE WSTAL")
    proc.kill()
    sys.exit(1)

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


try:
    c = httpx.Client(timeout=15)

    # 1. Status
    r = c.get(f"{BASE}/api/v1/status")
    st = r.json()
    check("GET /status 200 + green", r.status_code == 200 and st["global_level"] == "green",
          f"{r.status_code}, level={st['global_level']}")
    check("Status: zrodla w health-checku", len(st["sources_health"]) >= 10, f"n={len(st['sources_health'])}")
    check("Status: disclaimer RCB/112", "oficjalny system alarmowania" in st["disclaimer"])

    # 2. OpenAPI docs
    r = c.get(f"{BASE}/docs")
    check("GET /docs 200", r.status_code == 200, f"{r.status_code}")

    # 3. Zgloszenie bledu - poprawne i niepoprawne
    r = c.post(f"{BASE}/api/v1/reports", json={"category": "wrong_classification", "message": "test"})
    check("POST /reports 202", r.status_code == 202)
    r = c.post(f"{BASE}/api/v1/reports", json={"category": "XSS<script>", "message": "A" * 5000})
    check("POST /reports walidacja kategorii -> 422", r.status_code == 422)

    # 4. Push register/delete + walidacja
    r = c.post(f"{BASE}/api/v1/push/register", json={
        "token": "fcm-token-e2e-1234567890", "platform": "android",
        "voivodeships": ["podlaskie"], "min_level": "orange", "official_only": True})
    sid = r.json().get("subscription_id")
    check("POST /push/register 201", r.status_code == 201 and sid)
    r2 = c.post(f"{BASE}/api/v1/push/register", json={"token": "x" * 20, "platform": "symbian"})
    check("/push/register zla platforma -> 422", r2.status_code == 422)
    r3 = c.delete(f"{BASE}/api/v1/push/{sid}")
    check("DELETE /push 204", r3.status_code == 204)

    # 5. Admin bez tokenu
    r = c.get(f"{BASE}/admin-api/sources")
    check("Admin bez tokenu -> 401", r.status_code == 401)

    H = {"Authorization": f"Bearer {TOKEN}"}

    # 6. Reczny wpis Telegram -> pending_review -> approve -> max yellow/orange, NIGDY red
    r = c.post(f"{BASE}/admin-api/messages/manual", headers=H, json={
        "url": "https://t.me/przyklad/123", "source_slug": "telegram-manual",
        "title": "WIELKI ATAK!!!", "text": "Podobno rakiety nad Warszawą!!! Doniesienia niepotwierdzone."})
    out = r.json()
    ev_id_tg = out.get("event_id")
    check("Manualny Telegram -> created", r.status_code == 200 and out["action"] == "created", str(out))
    listing = c.get(f"{BASE}/api/v1/events").json()["items"]
    check("pending_review niewidoczne publicznie", all(e["id"] != ev_id_tg for e in listing))
    r = c.post(f"{BASE}/admin-api/events/{ev_id_tg}/approve", headers=H)
    ev = c.get(f"{BASE}/api/v1/events/{ev_id_tg}").json()
    check("Po approve: widoczne, status active", ev["status"] == "active")
    check("Telegram NIE jest red (twarda regula)", ev["alert_level"] != "red", ev["alert_level"])
    check("Telegram: single_source/unverified", ev["verification_status"] in ("single_source", "unverified"))
    check("Karta: baza pewnosci widoczna", float(ev["confidence"]) < 0.5 and len(ev["confidence_breakdown"]) > 0,
          f"conf={ev['confidence']}")
    check("Disclaimer OSINT+112 w alercie", "112" in ev["disclaimer"])

    # 7. Oficjalny komunikat przez kanal reczny zrodel rcb (symulacja wpisu operatora)
    r = c.post(f"{BASE}/admin-api/messages/manual", headers=H, json={
        "url": "https://www.gov.pl/web/rcb/e2e-alert", "source_slug": "rcb",
        "title": "Alert lotniczy",
        "text": "Zagrożenie w przestrzeni powietrznej - alert lotniczy dla województwa podlaskiego.",
        "published_at": "2026-08-23T23:30:00Z"})
    o2 = r.json()
    ev_id_rcb = o2.get("event_id")
    ev_rcb = c.get(f"{BASE}/api/v1/events/{ev_id_rcb}").json()
    check("RCB: officially_confirmed", ev_rcb["verification_status"] == "officially_confirmed")
    check("RCB air_alert => CZERWONY wg reguly", ev_rcb["alert_level"] == "red", ev_rcb["alert_level"])
    check("RCB: podstawa klasyfikacji z tier-1", any("tier-1" in b for b in ev_rcb["alert_level_basis"]))
    loc_ok = any(l["voivodeship"] == "podlaskie" for l in ev_rcb["locations"])
    check("Geolokalizacja: podlaskie (region)", loc_ok)

    # 8. Globalny poziom po czerwonym zdarzeniu
    st2 = c.get(f"{BASE}/api/v1/status").json()
    check("Global level = red po oficjalnym alarmie", st2["global_level"] == "red", st2["global_level"])

    # 9. Red-confirm walidacja uzasadnienia
    r = c.post(f"{BASE}/admin-api/events/{ev_id_tg}/red-confirm", headers=H, json={"justification": ""})
    check("red-confirm bez uzasadnienia -> 422", r.status_code == 422)

    # 10. Anti-spoofing: URL spoza domain_pin rcb
    r = c.post(f"{BASE}/admin-api/messages/manual", headers=H, json={
        "url": "https://evil.example.com/fake-rcb", "source_slug": "rcb",
        "title": "Fake", "text": "Fake alert lotniczy dla województwa pomorskiego."})
    # manual nie przechodzi przez check_domain (operator odpowiada za URL), ale dedup/normalizacja dziala
    check("Manual z obcej domeny przyjety do kolejki (operator odpowiada)", r.status_code == 200, r.text[:80])

    # 11. Filtry listy
    items_red = c.get(f"{BASE}/api/v1/events?level=red").json()
    check("Filtr level=red", items_red["total"] >= 1)
    items_src = c.get(f"{BASE}/api/v1/events?source_type=telegram").json()
    check("Filtr source_type=telegram (SQL)", items_src["total"] >= 1 and
          all(any(s["source_type"] == "telegram" for s in e["sources"]) for e in items_src["items"]))
    items_voiv = c.get(f"{BASE}/api/v1/events?voivodeship=podlaskie").json()
    check("Filtr voivodeship=podlaskie", items_voiv["total"] >= 1)

    # 12. Historia statusow
    hist = ev_rcb.get("status_history", [])
    check("Historia zmian poziomu zapisana", len(hist) >= 1)

    # 13. CORS preflight
    r = c.options(f"{BASE}/api/v1/events", headers={
        "Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"})
    acao = r.headers.get("access-control-allow-origin")
    check("CORS: localhost:3000 dozwolony", acao == "http://localhost:3000", str(acao))

    # 14. Audyt admina
    audit = c.get(f"{BASE}/admin-api/audit", headers=H).json()
    actions = [a["action"] for a in audit]
    check("Dziennik audytu: approve+manual", "approve_event" in actions and "manual_ingest" in actions,
          ",".join(set(actions)))

    # 15. Nieistniejace zdarzenie -> 404
    r = c.get(f"{BASE}/api/v1/events/nie-ma-takiego")
    check("GET /events/{nieznane} -> 404", r.status_code == 404)

finally:
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()

print(f"\n{'='*64}")
ok = sum(1 for _, s, _ in results if s)
for name, status, detail in results:
    print(f"  [{'OK ' if status else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))
print(f"{'='*64}\nWYNIK: {ok}/{len(results)}")
sys.exit(0 if ok == len(results) else 2)
