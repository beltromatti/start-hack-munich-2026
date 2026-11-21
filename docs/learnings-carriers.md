# What the carriers actually do (from our real mailbox, Sat ~15:15)

Read-only look at `start-milan@hackloop.mail` (35 mails, all replies to our own test requests). Raw dump stays
local in `backend/data/` (gitignored). Update this file as we learn more; it feeds the CRM and the watcher.

1. **Every carrier answers about 30 seconds after our request** (airlines, truckers, rate desk alike; measured
   30–31 s on all 34 replies). Waiting for all bids costs ~30 s, well inside the 2:00 for full speed points.
   Watch this: a slower reply is a sign that the setup changed.
2. **A bid request without an explicit total weight gets no price.** 9 airlines answered only:
   "To quote we need: the total weight in kg. Please reply in this thread." Always write `Total weight: 320 kg`
   (number + kg, on its own line) in every bid request. Each miss costs a full ~30 s round trip.
3. **Airlines that don't serve a lane say so and list the lanes they do fly** (e.g. Ibisair Cargo: CGN-ORD,
   DUS-HKG, FRA-ATL, …). Store these lists: free lane map, so we stop asking them.
4. **Quotes carry a reference and a validity of ~15 minutes**: airline `R-…` (book with it), trucker `TRK-…`
   ("No booking is required"). Example: Yellowtail FRA-ORD 320 kg 828.80 EUR, 4 days.
5. **The rate desk answers by email with portal rates** incl. `rate_id`, transit days and validity, and names the
   airlines that are not on the portal ("email orion-cargo-air@…").
6. **Truckers quote pickup zone → airport with a pickup time.** Zone 60 → FRA: Bodenseefracht 88.60,
   Westfalenroute 96.80, Isarwelle 129.80, Domblick 151.60, Taunusfracht 177.40 EUR.
7. `/v1/board/me` before 16:00: rank 1, total 0, no requests yet (everyone is at 0).

CRM fields worth keeping per carrier reply: carrier, lane, weight, price, currency, transit days / pickup time,
reference (R-/TRK-), valid until, seconds to reply, outcome (priced / needs info / lane not served).
