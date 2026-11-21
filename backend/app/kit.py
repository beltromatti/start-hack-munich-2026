"""What we know about the world: carriers, pickup zones, rate sheets, portal lanes.

Loaded from the start kit once; rate sheets can be replaced at runtime by tariff ingestion (stored as records,
which win over the kit file); portal lanes come live from the API and are refreshed.
"""
import csv
import json
import threading
import time
from dataclasses import dataclass, field

from . import store
from .config import KIT

START = KIT / "start-kit"
# Every destination in the start kit (carrier list, sheets, portal), with the names customers use for it.
DESTINATIONS = {
    "ASU": "Asuncion", "ATL": "Atlanta", "BKK": "Bangkok", "BOG": "Bogota", "BOM": "Mumbai / Bombay", "CAI": "Cairo",
    "DEL": "Delhi / New Delhi", "DFW": "Dallas", "DOH": "Doha", "DXB": "Dubai", "EZE": "Buenos Aires",
    "GRU": "Sao Paulo", "HKG": "Hong Kong", "ICN": "Seoul", "JFK": "New York", "JNB": "Johannesburg",
    "KTM": "Kathmandu", "KUL": "Kuala Lumpur", "LAX": "Los Angeles", "LIM": "Lima", "LOS": "Lagos",
    "MEL": "Melbourne", "MEX": "Mexico City", "MIA": "Miami", "MNL": "Manila", "NBO": "Nairobi",
    "NRT": "Tokyo", "ORD": "Chicago", "PEK": "Beijing / Peking", "PPT": "Papeete / Tahiti", "PVG": "Shanghai",
    "RUH": "Riyadh", "SCL": "Santiago de Chile", "SGN": "Ho Chi Minh City / Saigon", "SIN": "Singapore",
    "SYD": "Sydney", "TLV": "Tel Aviv", "TNR": "Antananarivo", "TPE": "Taipei", "ULN": "Ulaanbaatar",
    "YYZ": "Toronto",
}


def destination_code(text: str | None) -> str | None:
    """'LOS', 'Lagos', 'Lagos, Nigeria', 'Peking' -> the IATA code in our network; any other 3-letter code as is."""
    t = (text or "").strip()
    if not t:
        return None
    if t.upper() in DESTINATIONS:
        return t.upper()
    low = t.lower()
    for code, names in DESTINATIONS.items():
        if any(n.strip().lower() in low for n in names.split("/")):
            return code
    return t.upper() if len(t) == 3 and t.isalpha() else None


TRACKING = "tracking@hackloop.mail"
RATEDESK = "ratedesk@hackloop.mail"


@dataclass
class Carrier:
    name: str
    kind: str          # airline | trucker
    email: str
    serves: list[str]  # destination airports (airlines) or pickup zones (truckers)


@dataclass
class World:
    carriers: list[Carrier] = field(default_factory=list)
    zones: dict[str, dict] = field(default_factory=dict)          # "60" -> {area, airport}
    sheet_lanes: list[dict] = field(default_factory=list)          # tariffs.json lanes (+ ingested)
    portal: dict[tuple[str, str], list[dict]] = field(default_factory=dict)  # (o,d) -> [{code,name}]
    brackets: dict[str, list[int]] = field(default_factory=dict)  # airline code -> breaks
    portal_at: float = 0.0

    def carrier_by_email(self, email: str) -> Carrier | None:
        email = email.strip().lower()
        return next((c for c in self.carriers if c.email.lower() == email), None)

    def carrier_by_name(self, name: str) -> Carrier | None:
        n = name.strip().lower()
        return next((c for c in self.carriers if c.name.lower() == n), None)

    def origins(self) -> set[str]:
        return {z["airport"] for z in self.zones.values()} | {o for o, _ in self.portal}

    def sheet(self, origin: str, destination: str) -> list[dict]:
        return [l for l in self.sheet_lanes if l["origin"] == origin and l["destination"] == destination]

    def email_airlines(self, origin: str, destination: str) -> list[Carrier]:
        """Airlines not on the portal that fly to this destination: they quote by email."""
        on_portal = {a["name"].lower() for a in self.portal.get((origin, destination), [])}
        portal_names = {a["name"].lower() for lanes in self.portal.values() for a in lanes}
        return [c for c in self.carriers if c.kind == "airline" and destination in c.serves
                and c.name.lower() not in on_portal and c.name.lower() not in portal_names]

    def truckers(self, zone: str) -> list[Carrier]:
        return [c for c in self.carriers if c.kind == "trucker" and zone in c.serves]


_world = World()
_lock = threading.Lock()


def world() -> World:
    return _world


def load(api=None) -> World:
    """Start kit from disk; portal lanes from the live API when a client is given."""
    w = World()
    with open(START / "carrier-list.csv") as f:
        for row in csv.DictReader(f):
            w.carriers.append(Carrier(row["name"].strip(), row["kind"].strip(), row["email"].strip(),
                                      row["serves"].split()))
    with open(START / "pickup_zones.csv") as f:
        for row in csv.DictReader(f):
            w.zones[row["zone"].strip()] = {"area": row["area"].strip(), "airport": row["airport"].strip()}
    w.sheet_lanes = json.load(open(KIT / "tariffs.json"))["lanes"]
    _apply_ingested(w)
    if api is not None:
        refresh_portal(api, w)
    global _world
    with _lock:
        _world = w
    return w


def refresh_portal(api, w: World | None = None) -> None:
    w = w or _world
    lanes = api.ports()
    w.portal = {(l["origin"], l["destination"]): l["airlines"] for l in lanes}
    for code in {a["code"] for l in lanes for a in l["airlines"]}:
        b = api.brackets(code)
        if b:
            w.brackets[code] = b
    w.portal_at = time.time()
    store.log("kit", "info", f"portal: {len(w.portal)} lanes, {len(w.brackets)} airlines")


def replace_sheet(airline: str, lanes: list[dict], source: str) -> None:
    """Tariff ingestion: an airline's new sheet replaces its old lanes."""
    store.put(f"tariff-{airline.lower().replace(' ', '-')}", "tariff", "active",
              {"airline": airline, "lanes": lanes, "source": source, "at": time.time()})
    with _lock:
        _world.sheet_lanes = [l for l in _world.sheet_lanes if l["airline"] != airline] + lanes


def _apply_ingested(w: World) -> None:
    for rec in store.records("tariff", "active"):
        airline = rec["data"]["airline"]
        w.sheet_lanes = [l for l in w.sheet_lanes if l["airline"] != airline] + rec["data"]["lanes"]
