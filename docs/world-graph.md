# World graph: the customer looks into our backend

For Sam, from Jan (Sun 22 Nov, 03:00). A view for the pitch and the UX score (jury criteria 1 and 2).
It is one more tab in the sessions UI. It changes nothing the agent does.

## What it is

A clickable network of our freight world. **Nodes:** German pickup airports, destination airports, airlines,
truckers, customers. **Edges:** the lanes an airline flies, the zones a trucker picks up from, and the deals moving
right now. The viewer sees how supply in different countries hangs together, and where a live shipment sits in it.

**Everything shown is computed from data we already hold.** No Neo4j and no invented numbers. trend_scout does not
use Neo4j either: it runs SQLite plus a d3-force canvas (`trend_scout/docs/decisions/0002-sqlite-not-graph-database.md`).
A jury member who clicks a node and gets a real price beats a pretty graph that falls apart on the second question.

## The data (all in the repo)

| Source | What it gives | Count |
|---|---|---|
| `docs/challenges/5u-kit/tariffs.json` | lanes: airline, origin, destination, EUR/kg per weight break, transit days | 158 rows, 107 origin-destination pairs, 10 airlines, 42 airports |
| `start-kit/carrier-list.csv` | every carrier, `airline` or `trucker`, the airports it serves | 29 airlines, 22 truckers |
| `start-kit/pickup_zones.csv` | postcode zone to German airport | 32 zones, 6 origins (FRA 45 lanes, MUC 37, HAM 21, DUS 20, CGN 18, STR 17) |
| `GET /api/deals`, `/api/bookings` | live deals: lane, weight, options, booked carrier, status | as many as the mailbox brings |

Facts the graph can show at once, counted from `tariffs.json`:
- **60 of 107 lanes have one airline on our sheets.** That is concentration risk, and it is real.
- **Price spread on one lane goes up to 1.8x.** DUS to HKG at 100 kg: 2.53 EUR/kg cheapest, 4.57 dearest (rate + fuel + security). That gap is what our agent earns the customer.
- **FRA serves 32 destinations, and 29 of them are also flown from another German airport.** That is the fallback when FRA is down.

## Endpoint (backend, about 30 min, I or Mattia build it)

`GET /api/world` returns one JSON, built from the kit files once at startup plus the live deals on each call:

```json
{
  "nodes": [
    {"id": "FRA", "kind": "origin", "label": "Frankfurt", "lat": 50.03, "lon": 8.56, "lanes": 45},
    {"id": "HKG", "kind": "destination", "label": "Hong Kong", "lat": 22.31, "lon": 113.91, "airlines": 2},
    {"id": "air:Cobalt Skylift", "kind": "airline", "portal": true, "lanes": 17},
    {"id": "truck:...", "kind": "trucker", "zones": ["60", "61"]},
    {"id": "deal:123", "kind": "deal", "customer": "acme", "status": "quoted"}
  ],
  "links": [
    {"source": "FRA", "target": "HKG", "kind": "lane", "airlines": 2,
     "best_eur_kg": "2.53", "worst_eur_kg": "4.57", "transit_days": 4},
    {"source": "air:Cobalt Skylift", "target": "HKG", "kind": "serves"},
    {"source": "deal:123", "target": "FRA", "kind": "moves", "weight_kg": 300}
  ]
}
```

Prices come from `pricing.py`, never computed again in the frontend (team rule 1).

## The view (Sam)

**Layout.** Two modes on one set of nodes, one toggle:
1. **Force** (default, the trend_scout look): d3-force pulls airports, airlines and deals into clusters. Airlines
   sit between the airports they serve, so hubs show by themselves.
2. **Map:** the same nodes pinned to lat/lon (`fx`/`fy` in d3-force), lanes drawn as arcs from Germany outward.
   The switch animates between the two. This is the moment that looks good on the projector.

**Encoding.**
- Node size: number of lanes. Colour: kind (origin, destination, airline, trucker, deal), from your tokens in `styles.css`.
- Lane width: number of airlines. A single-airline lane is drawn dashed: concentration risk without a legend.
- A live deal is a small dot travelling along its lane. Quoted: still. Booked: moves. Each new mail makes it pulse.

**Click.**
- Airport: its lanes, airlines and the cheapest EUR/kg per break, plus the deals going through it now.
- Lane: every airline's price at 100 / 300 / 500 kg side by side, the spread in one number.
- Deal: opens the existing DealView. The graph is a second door into the same CRM.

**Library.** `d3-force` only (one small package, about 15 kB), drawn into SVG or canvas by React. No sigma, cytoscape
or graph framework. trend_scout's `drawGraph` in `src/trendscout/app/static/app.js` (lines 679 to 740) is a working
reference: forces, zoom, collide radius by node size.

## Intelligence layer (the trend_scout logic, kept simple)

Ranked by value for the pitch against build time. Only 1 is a must.

1. **Live overlay** (must, comes free with the endpoint): the world graph with today's deals on it. Story: "every
   mail you send us lands somewhere on this map, and you watch our agent work it."
2. **What-if shock** (proposal, about 1 h, the trend_scout `propagate` idea): click an airport or airline and mark it
   down. The graph greys out what is lost and shows what reroutes: "FRA closed: 3 destinations lose their only route,
   29 move to MUC or DUS at a different price." Computed by re-running `pricing.py` without that node. It sells
   "supplier intelligence" with real numbers.
3. **Margin heat** (later): colour each lane by what we earned on booked deals. Needs bookings, so only after the
   board has run a while.

## Where it sits

- One tab "World" next to deals and board in `frontend/src/App.tsx`. No new route in the agent.
- Mattia's five questions: **judgement or guarantee:** neither, a view. **This mail or the kind:** the kind,
  every deal shows. **One place:** `/api/world` in `main.py` plus one frontend component. **Does the agent use it:**
  no. **What shows it worked:** in the pitch rehearsal a jury-style click on any node gives a real price within one second.
