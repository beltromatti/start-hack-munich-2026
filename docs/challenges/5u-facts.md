# 5U facts: what the live API and the start kit say

Pulled by Jan's Claude on Sat 21 Nov, 14:04 (13:04 UTC), from `/v1/portal/*`, `/v1/board`, `/v1/mailbox` and the
CSVs in `5u-kit/start-kit/`. Every number below was counted in code, not estimated. 5U changes the setup during the
night, so re-check before you build on a number.

## Decisions these facts settle

| Question | Fact | What follows |
| --- | --- | --- |
| Do we need a knowledge graph? | 51 carriers, 6 origins, 41 destinations, 32 pickup zones | No. Three SQLite tables hold it: carriers, lanes, zones |
| Can we ask the portal for every airline on a lane? | **10 rate calls per minute**, at most 4 airlines per lane | Yes. One RFQ needs 1 to 4 calls. Cache per lane and weight, never loop blindly |
| How long does a portal rate hold? | `valid_until` is 15 min after the call | Book within 15 min or fetch again (410 means expired) |
| Which airlines need email instead of the portal? | 14 of 29 airlines are not on the portal | 10 have a rate sheet in the kit, 4 only answer by mail |
| Which destinations only email airlines reach? | ASU, KTM, PPT, TNR, ULN | An RFQ there cannot be priced from the portal at all |
| Is a trucker always available for the pickup leg? | Every one of the 32 zones has 2 to 5 truckers | Always ask at least 2. Zones 63, 35, 71, 72 have only 2 |

## Carriers (`carrier-list.csv`)

- **51 carriers: 29 airlines, 22 truckers.** Columns `name, kind, email, serves`.
- Airlines: `serves` lists destination airports. Truckers: `serves` lists **pickup zones** (postcode prefixes), not
  airports.

## Portal (`/v1/portal/ports`, `/v1/portal/brackets`)

- **114 lanes** from 6 origins to 36 destinations.
- Lanes per origin: FRA 34, MUC 24, DUS 17, HAM 14, STR 13, CGN 12.
- Airlines per lane: 1 on 46 lanes, 2 on 49, 3 on 14, 4 on 5. A single-airline lane has no portal competition, so
  email airlines matter most there.
- **15 airlines on the portal**: AU Aurelia, BX Borealis, FQ Fjordline, GN Gannet, IB Ibisair, JP Juniper, LM Lumen,
  MD Meridian, NV Nova Atlas, PL Polaris, RV Riverbend, SL Solace, TM Tamarind, UV Ultraviolet, XC Xenon.
- **14 airlines only by email**: Cobalt Skylift, Danube Wings Cargo, Elbflug Air Freight, Helix Air Freight, Kestrel
  Airways, Orion Cargo Air, Quetzal Air Freight, Vega Skyfreight, Wayzata Air Cargo, Yellowtail Air Freight, Zephyr
  Steppe Cargo, Himalaya Bridge Air, Lagoon Isles Airways, Pampero Air Cargo. The first 10 have a rate sheet in the
  kit (11 files, Danube comes as two jpg pages). The last 4 (Zephyr, Himalaya, Lagoon, Pampero) have none: ask them by
  mail.
- `brackets` for an email airline returns 404 with the address to mail, for example
  `cobalt-skylift@hackloop.mail`.
- Weight breaks come in two shapes. 8 airlines (AU, BX, FQ, IB, NV, RV, SL, XC) end at 2000 kg:
  breaks `0, 45, 100, 250 or 300, 500, 1000, 2000`. 7 (GN, JP, LM, MD, PL, TM, UV) stop at 1000 kg.
- The third break differs: **250 kg** for AU, FQ, IB, NV, **300 kg** for the other 11. A 280 kg shipment falls in
  different brackets per airline, so code must read the breaks per airline.

## One sample rate (`/v1/portal/rates`)

CGN to DEL, Juniper (JP), 250 kg, 1.2 cbm: **EUR 927.50**, chargeable 250 kg, 5 days transit, `dataset_version` v1.
Headers: `X-RateLimit-Limit: 10`, `X-RateLimit-Remaining: 9`. Totals are strings in EUR: parse them as `Decimal`.

## Pickup zones (`pickup_zones.csv`)

32 zones: FRA 8, MUC 6, DUS 6, HAM 5, STR 4, CGN 3. Truckers per zone range from 2 to 5. Every trucker zone exists
in the zone file.

## Board and mailbox at 14:04

- `/v1/board`: **14 teams**, 0 rounds sent, 0 accepted, 0 bookings. Rules as in the brief: accuracy 45, cost 40,
  time 15, plus humanity 10 and tracking 10.
- `/v1/board/me`: start-milan, total 0, no requests yet.
- Mailbox empty. Gateway: `"set": false`, so no model call works until our OpenAI key is posted.
