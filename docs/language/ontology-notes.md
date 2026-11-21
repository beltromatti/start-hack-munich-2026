# Logistics ontologies: the few nouns and verbs we need

Not a full ontology (overkill). We borrow names from existing standards so our JSON, CRM and pitch use the words
the industry already uses. Source notes at the bottom; items marked *(verify)* are from memory, not checked.

## Nouns (what things are)

From **IATA ONE Record** (the air-cargo data model, v3.2.0, endorsed July 2025):

| ONE Record term | Meaning | Our field / record |
| --- | --- | --- |
| Shipment | the consignment as a whole | one RFQ = one `shipment` |
| Piece | one physical unit (box, pallet), the centre of the model | `pieces[]` with weight and dims |
| Item / Product | what is inside a piece | `commodity` |
| ULD / LoadingUnit | aircraft container or pallet | only if the mail mentions it |
| TransportMovement | a flight leg (origin → destination) | `origin`, `destination`, `transit_days` |
| LogisticsEvent | anything worth recording (status update) | our event log, tracking answers |
| Waybill (MAWB / HAWB) | the transport document | `booking_reference` later |
| Location, Party *(verify)* | airports/addresses, shipper/consignee/carrier | `pickup_zone`, `customer`, `carrier` |
| Dimensions, Value *(verify)* | sizes, amounts with unit/currency | always store unit and currency |

## Verbs (what happens), in order

From **GS1 CBV** business steps *(verify exact list in CBV 2.0)* plus the 5U flow:

request → quote → accept → book → confirm → **shipping** → **loading** → **departing** → **arriving** →
**unloading** → **receiving** / deliver → track

Use exactly these as our CRM stages and event names: `requested, quoted, accepted, booked, confirmed, departed,
arrived, delivered`, plus `rejected, missed` for the scoring outcome.

## The RFQ record we fill (one cheap LLM call or the lexicon pre-sort)

```json
{
  "language": "de", "style": {"words": 38, "formal": true, "structured": false},
  "service": "cheapest | fastest",
  "origin": {"pickup_zone": "60", "airport": "FRA"}, "destination": {"airport": "JFK"},
  "door_pickup": true,
  "pieces": [{"count": 2, "type": "pallet", "length_cm": 120, "width_cm": 80, "height_cm": 110, "weight_kg": 160}],
  "gross_weight_kg": 320, "volume_cbm": 2.11, "chargeable_weight_kg": 352,
  "commodity": "machine parts", "ready_date": "2026-11-22",
  "flags": ["dangerous_goods?", "perishable?", "oversized?"],
  "missing": ["dimensions"],
  "evidence": {"gross_weight_kg": "320kg", "service": "cheapest pls"}
}
```

`missing` drives "ask the customer" instead of guessing. `evidence` keeps the exact words each value came from
(same idea as Sempli's evidence check), so nothing is invented.

## Sources

- IATA ONE Record data model: [iata-cargo.github.io/ONE-Record/stable/Data-Model](https://iata-cargo.github.io/ONE-Record/stable/Data-Model),
  [IATA data model insight (PDF)](https://www.iata.org/contentassets/a1b5532e38bf4d6284c4bf4760646d4e/data-insight-the-one-record-data-model-digital-twin-of-the-air-cargo-industry.pdf),
  [GitHub IATA-Cargo/ONE-Record](https://github.com/IATA-Cargo/ONE-Record)
- GS1 Core Business Vocabulary: [ref.gs1.org/standards/cbv](https://ref.gs1.org/standards/cbv)
- Chargeable weight rule (167 kg per cbm): 5U start kit, `docs/challenges/5u-kit/tariffs.json` → `rules`
