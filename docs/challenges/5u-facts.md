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
| Which airlines need email instead of the portal? | 14 of 29 airlines are not on the portal | 10 have a rate sheet, now in `5u-kit/tariffs.json`. 4 only answer by mail |
| Is the portal total the best price? | 299 kg costs EUR 1109.29, 300 kg EUR 1026.00 (same lane) | Always also price the next break up and take the cheaper |
| Which destinations only email airlines reach? | ASU, KTM, PPT, TNR, ULN | An RFQ there cannot be priced from the portal at all |
| Is a trucker always available for the pickup leg? | Every one of the 32 zones has 2 to 5 truckers | Always ask at least 2. Zones 63, 35, 71, 72 have only 2 |

## Pricing rule: bill at the next break when it is cheaper

Portal, CGN to DEL, Juniper, probed Sat 14:2x:

| Weight | Total EUR | Per kg |
| --- | --- | --- |
| 280 kg | 1038.80 | 3.71 |
| 299 kg | 1109.29 | 3.71 |
| 300 kg | 1026.00 | 3.42 |
| 320 kg | 1094.40 | 3.42 |

The portal does not apply the break point itself: 299 kg costs 83.29 more than 300 kg. **Our price must be the minimum
over the actual chargeable weight and each higher break**, so 299 kg is billed as 300 kg. The gap here is 7.5 %, more
than the 5 % tolerance. This is likely what 5U means by "the best price is not always the obvious one".

## Rate sheets as data (`5u-kit/tariffs.json`)

All 10 sheets normalised into one table: **158 lanes**, per lane the weight breaks, EUR per kg, minimum charge,
transit days, fuel and security per kg. Prices are strings with two decimals (parse as `Decimal`). Rules in the
file's `rules` block, the same on all 10 sheets: chargeable weight = max(actual kg, cbm x 167), minimum applies to
freight before surcharges, surcharges per kg of billed weight, valid 1 to 30 Nov 2026.

- Checked: every lane's destination is in that airline's `serves` list, every `serves` destination has a lane, every
  lane has surcharges, no rate rises with weight, lane counts equal the source files.
- The sheets cover 107 origin-destination pairs. 101 are portal lanes too. **All 46 portal lanes with a single
  airline get at least one sheet competitor.** 6 pairs exist only on sheets: CGN-LOS, FRA-BOM, FRA-DXB, HAM-PEK,
  MUC-HKG, MUC-MEL.
- Breaks differ: Yellowtail, Kestrel and Helix break at 250 kg, the other 7 at 300 kg. Orion and Danube stop at
  1000 kg.
- Danube Wings came as two scanned jpg pages, transcribed by reading the images. Re-check those 9 lanes before money
  depends on them.

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

## Live mail formats (probed Sat 14:50–15:10 by Mattia's Claude, real 5U carriers)

- **Carriers answer bid requests by mail in 15–35 s**, the rate desk in ~47 s, all in prose (an LLM parses them).
- **Write the weight as `Total weight: 320 kg`.** "320 kg chargeable" got "To quote we need: the total weight in kg"
  from every airline. Labelled lines work: `Route: FRA to ORD` / `Total weight:` / `Volume:` / `Pieces:`.
- **Sheet airlines quote by mail exactly their sheet price** (Yellowtail FRA-ORD 320 kg 1.5 cbm: 828.80 EUR = sheet),
  with a portal-style `R-...` reference "to quote when booking", valid 15 min.
- **Email-only airlines** (Zephyr etc.) answer the same way. **Portal airlines** asked by mail say which lanes they fly.
- **Truckers**: "Our total for the pickup ... is 177.40 EUR. Pickup time: 3 hours. ... offer reference TRK-49. No
  booking is required." Zone 60 (Frankfurt): 5 truckers, 88.60 EUR / 26 h up to 177.40 EUR / 3 h.
- **Rate desk** (`ratedesk@`): answers in a new thread (`in_reply_to` null), subject `Portal rates FRA-ORD 320.0 kg`,
  one line per airline on the lane with total, transit, rate_id; non-portal airlines listed as "email ...".
- **Gateway**: `gpt-6-luna` (reasoning `none`) ~1.5–2.5 s per call, `gpt-5-nano` (`minimal`) ~0.8 s. A whole RFQ
  (read, ~6 bid parses, write) costs about **$0.0008**, i.e. ~39.7 of 40 cost points.
- **Production runs on Mattia's Mac (`make live`) from Sat 15:10.** Nobody else runs `make live`: two pollers on
  one mailbox would answer twice.

## First live round (Sat 16:00, Mattia's Claude)

- **Customers write from `@hackloop.mail` addresses** too (e.g. `lindqvist-medtech@hackloop.mail`): never route by
  domain; unknown senders are customers.
- Round 1: CGN-ORD door-to-port (51447), 676 kg / 5.79 cbm (chargeable 966.93 kg, billed at the 1000 kg break),
  fastest. We quoted Meridian (1 day) + pickup, **3230.03 EUR in 39 s: accepted, 60 points** (45 accuracy + 15 time;
  cost points come hourly). The customer accepted 24 s later; booked on the portal (`BK-3ZY8SE7F`), confirmed,
  the customer's thank-you got no reply. Whole deal: $0.0016 of model cost. Field: 4 teams answered, 3 accepted.
- `/v1/board/me` request fields: `round_no, sent_at, answered_at, verdict, reason, booked`; plus `scores_revealed`
  and our `bookings` with `booking_reference`. Public `rounds`: `round_no, sent_at, expires_at, voided, status,
  answered, accepted`.
