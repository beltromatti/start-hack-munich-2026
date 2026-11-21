"""What we know about the world: carriers, pickup zones, rate sheets, portal lanes.

Loaded from the start kit once; rate sheets can be replaced at runtime by tariff ingestion (stored as records,
which win over the kit file); portal lanes come live from the API and are refreshed.
"""
import csv
import json
import re
import threading
import time
from dataclasses import dataclass, field

from . import store
from .config import KIT

START = KIT / "start-kit"
# Every destination in the start kit (carrier list, sheets, portal), with the names customers use for it, in the
# languages they write in.
DESTINATIONS = {
    "ASU": "Asuncion", "ATL": "Atlanta", "BKK": "Bangkok", "BOG": "Bogota", "BOM": "Mumbai / Bombay",
    "CAI": "Cairo / Kairo / Le Caire / El Cairo / Il Cairo",
    "DEL": "Delhi / New Delhi / Neu-Delhi / Neu Delhi / Nueva Delhi / Nuova Delhi", "DFW": "Dallas", "DOH": "Doha",
    "DXB": "Dubai", "EZE": "Buenos Aires", "GRU": "Sao Paulo / San Paolo", "HKG": "Hong Kong / Hongkong",
    "ICN": "Seoul / Seul", "JFK": "New York / Nueva York / Nuova York", "JNB": "Johannesburg / Johannesbourg",
    "KTM": "Kathmandu / Katmandu / Katmandou", "KUL": "Kuala Lumpur", "LAX": "Los Angeles", "LIM": "Lima",
    "LOS": "Lagos", "MEL": "Melbourne",
    "MEX": "Mexico City / Mexiko-Stadt / Mexiko Stadt / Ciudad de Mexico / Citta del Messico / Mexico DF",
    "MIA": "Miami", "MNL": "Manila / Manille", "NBO": "Nairobi", "NRT": "Tokyo / Tokio", "ORD": "Chicago",
    "PEK": "Beijing / Peking / Pekin / Pechino", "PPT": "Papeete / Tahiti", "PVG": "Shanghai / Schanghai",
    "RUH": "Riyadh / Riad / Riyad", "SCL": "Santiago de Chile / Santiago",
    "SGN": "Ho Chi Minh City / Saigon / Ho-Chi-Minh-Stadt / Ho Chi Minh", "SIN": "Singapore / Singapur / Singapour",
    "SYD": "Sydney", "TLV": "Tel Aviv", "TNR": "Antananarivo / Tananarive", "TPE": "Taipei / Taipeh",
    "ULN": "Ulaanbaatar / Ulan Bator / Ulan-Bator / Oulan-Bator", "YYZ": "Toronto",
}
# The pickup zones are named in English in the kit; the same towns as their own people write them.
TOWNS = {"munchen": "munich", "monaco di baviera": "munich", "koln": "cologne", "colonia": "cologne",
         "francoforte": "frankfurt", "francfort": "frankfurt", "amburgo": "hamburg", "hambourg": "hamburg",
         "stoccarda": "stuttgart", "magonza": "mainz", "mayence": "mainz", "ratisbona": "regensburg",
         "ratisbonne": "regensburg", "brema": "bremen", "breme": "bremen", "sud": "south", "sued": "south",
         "nord": "north"}


def fold(text: str | None) -> str:
    """A place name as a key: lower case, accents dropped, the German spellings made one ("München", "Muenchen",
    "Munchen"; "Gießen", "Giessen"; "São Paulo", "Sao Paulo"), punctuation as spaces."""
    import unicodedata
    t = (text or "").lower().replace("ß", "ss")
    t = "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))
    t = re.sub(r"(?<=[aou])e(?=[a-z])", "", t) if re.search(r"[aou]e[a-z]", t) else t
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def destination_code(text: str | None) -> str | None:
    """'LOS', 'Lagos', 'Lagos, Nigeria', 'Peking', 'São Paulo' -> the IATA code in our network; any other 3-letter
    code as is. Of several cities in the text the one named first (the others are left to the agent)."""
    t = (text or "").strip()
    if not t:
        return None
    if t.upper() in DESTINATIONS:
        return t.upper()
    low, found = f" {fold(t)} ", []
    for code, names in DESTINATIONS.items():
        at = [low.find(f" {fold(n)} ") for n in names.split("/")]
        if any(i >= 0 for i in at):
            found.append((min(i for i in at if i >= 0), code))
    if found:
        return min(found)[1]
    return t.upper() if len(t) == 3 and t.isalpha() else None


def zone_of_town(text: str | None, zones: dict[str, dict]) -> str | None:
    """The pickup zone a town belongs to, as the customer wrote the town: its own spelling ("München", "Köln",
    "Düsseldorf"), and the longest name that fits ("Munich South depot" is Munich South, not Munich)."""
    key = f" {fold(text)} "
    for theirs, ours in TOWNS.items():
        key = key.replace(f" {theirs} ", f" {ours} ")
    key = key.strip()
    if not key:
        return None
    areas = sorted(((fold(v["area"]), z) for z, v in zones.items()), key=lambda x: -len(x[0]))
    return next((z for a, z in areas if a == key), None) \
        or next((z for a, z in areas if f" {a} " in f" {key} "), None) \
        or next((z for a, z in reversed(areas) if f" {key} " in f" {a} "), None)


# A real postcode in the town of each pickup zone. Truckers price a collection by zone but only answer a request
# that carries a 5-digit postcode (probe Sat 18:14: "Augsburg" -> "we need the postcode", "area 86" -> no,
# "86150 Augsburg" -> 261.43 EUR "from Augsburg"). Used only when the customer names the town, not the postcode.
ZONE_POSTCODE = {
    "60": "60311", "61": "61348", "63": "63065", "64": "64283", "65": "65183", "55": "55116", "35": "35390",
    "36": "36037", "80": "80331", "81": "81541", "84": "84028", "85": "85049", "86": "86150", "93": "93047",
    "40": "40213", "41": "41061", "42": "42103", "44": "44135", "45": "45127", "47": "47051", "20": "20095",
    "21": "21335", "22": "22297", "24": "24103", "28": "28195", "70": "70173", "71": "71032", "72": "72070",
    "73": "73728", "50": "50667", "51": "51465", "53": "53111"}

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

    def sheet(self, origin: str, destination: str, on: str | None = None) -> list[dict]:
        """Each airline's lane valid on `on` (ISO day, default today); of several valid, the newest tariff."""
        day = on or time.strftime("%Y-%m-%d")
        best: dict[str, dict] = {}
        for l in self.sheet_lanes:
            if l["origin"] != origin or l["destination"] != destination:
                continue
            if not (l.get("valid_from") or "") <= day <= (l.get("valid_to") or "9999"):
                continue
            if l["airline"] not in best or (l.get("valid_from") or "") >= (best[l["airline"]].get("valid_from") or ""):
                best[l["airline"]] = l
        return list(best.values())

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
    kit_tariffs = json.load(open(KIT / "tariffs.json"))
    rules = kit_tariffs.get("rules", {})
    w.sheet_lanes = [{**l, "valid_from": rules.get("valid_from"), "valid_to": rules.get("valid_to")}
                     for l in kit_tariffs["lanes"]]
    _apply_ingested(w)
    if api is not None:
        refresh_portal(api, w)
    global _world
    with _lock:
        _world = w
    return w


def refresh_portal(api, w: World | None = None) -> None:
    """The portal's lanes and weight breaks. The portal can be down (Sat 20:26: /ports answered 503 at a restart):
    then we keep what we knew and carry on; the next refresh tries again, and prices come by mail meanwhile."""
    w = w or _world
    try:
        lanes = api.ports()
    except Exception as e:
        w.portal_at = time.time()
        store.log("kit", "error", f"portal lanes not refreshed: {e}"[:300])
        return
    w.portal = {(l["origin"], l["destination"]): l["airlines"] for l in lanes}
    for code in {a["code"] for l in lanes for a in l["airlines"]}:
        b = api.brackets(code)
        if b:
            w.brackets[code] = b
    w.portal_at = time.time()
    store.log("kit", "info", f"portal: {len(w.portal)} lanes, {len(w.brackets)} airlines")


def add_sheet(airline: str, lanes: list[dict], source: str, valid_from: str | None, valid_to: str | None) -> None:
    """Tariff ingestion: an airline's new sheet joins with its validity. It wins from its first valid day; the old
    one keeps pricing what ships before (a December tariff mailed in November does not reprice November)."""
    valid_from = valid_from or time.strftime("%Y-%m-%d")
    lanes = [{**l, "valid_from": valid_from, "valid_to": valid_to} for l in lanes]
    store.put(f"tariff-{airline.lower().replace(' ', '-')}-{valid_from}", "tariff", "active",
              {"airline": airline, "lanes": lanes, "source": source, "at": time.time(), "valid_from": valid_from,
               "valid_to": valid_to})
    with _lock:
        _world.sheet_lanes = [l for l in _world.sheet_lanes
                              if not (l["airline"] == airline and l.get("valid_from") == valid_from)] + lanes


def _apply_ingested(w: World) -> None:
    for rec in store.records("tariff", "active"):
        d = rec["data"]
        vf = d.get("valid_from") or d["lanes"][0].get("valid_from") if d.get("lanes") else None
        w.sheet_lanes = [l for l in w.sheet_lanes if not (l["airline"] == d["airline"] and l.get("valid_from") == vf)] \
            + [{**l, "valid_from": l.get("valid_from") or vf} for l in d["lanes"]]
