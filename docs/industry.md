# Air freight forwarding: how the trade works, what 5U has tested, what comes next

Written Sun 22 Nov 2026, 02:00 CET, after round 93. For Sam, Mattia and Jan.
Sources: four web research runs (50 URLs, 31 of them tier 1: zoll.de, LBA, BAFA, ICAO, IATA, ADSp, DHL and
handler price lists), our mailbox backup (1115 mails in, 947 out) and the board. Speculation is marked.

## The verdict

**5U is replaying the life of a deal, stage by stage.** Rounds 1 to 85 tested the quote. Since round 86
(Sat 23:37 UTC) every new difficulty sits after the quote or beside it: a change, a cancellation, several
shipments, a charge line, a dead price source. The remaining stages of a real deal are the next waves.

**One rule limits what they can do.** 5U can only score what its key can compute. Every new number must
therefore reach us in a mail, an attachment, a sheet or an API field. The work is to find where they put it.

## 1. How a forwarder earns the quote

A forwarder owns no aircraft. It buys space from airlines and trucks, adds the lines around the flight and
sells one price. The customer sees one number. Behind it are up to six blocks.

| Block | What it is | How it is priced | In our system |
| --- | --- | --- | --- |
| Air freight | Airline rate per chargeable kg | Weight breaks, minimum, break-back rule | Built (`pricing.py`) |
| Airline surcharges | Fuel, security | Per kg of chargeable weight | Built |
| Pickup | Truck to the airport | By zone or distance | Built |
| Origin handling | Handler and forwarder fees per air waybill | Flat or per kg with a minimum | Not built, never asked |
| Value lines | Insurance, valuation charge | Percent of a value | Built since round 91 (`charges`) |
| Destination | Delivery, duties, clearance | Outlay plus a fee | Not built, never asked |

**Chargeable weight.** The higher of gross weight and volume weight. IATA: "divide the volume of the shipment
in cubic centimeters by 6000", which is 167 kg per cbm. DHL's terms say the same: "1 cubic meter has an
equivalent chargeable weight of 167 kilograms". TACT rounds each piece up to the next 0.5 kg before summing.
We do not round. No round has punished that yet.

**Break-back.** TACT's own example: 995 kg at the 500 kg rate costs more than 1000 kg at the 1000 kg rate, so
the lower charge applies. That is our "next weight break" rule. It is the trade's rule, and 5U follows it.

**Origin lines a real quote carries** (DHL Global Forwarding Germany, "Nebenkosten Luftfracht", January 2026):

| Line | Price |
| --- | --- |
| Security filing (MSEC) | EUR 15,00 per shipment, USA, Canada and Australia EUR 25,00 |
| X-ray | Minimum EUR 45,00 or EUR 0,15 per kg |
| Dangerous goods handling | Minimum EUR 55,00 or EUR 0,20 per kg |
| Storage after 24 h | Minimum EUR 25,00 per day or EUR 0,10 per kg |
| Weighing | Minimum EUR 20,00 plus EUR 5,00 per piece |
| Document correction | EUR 49,50 per correction |
| Proof of delivery | EUR 35,00 |
| Outlay fee on duties | 4 %, minimum EUR 32,50 |
| Export declaration (DHL Express) | EUR 35,00 per declaration |

Handlers add their own per air waybill. Munich Cargogate (from 1 May 2025): dangerous goods check 134,00 plus
5,10 per piece, lithium section II check 76,00, weight and volume check 47,00. Swissport Frankfurt (from
1 April 2026): hidden or undeclared dangerous goods 1500,00 per air waybill.

**The shape of all of them: a flat amount, or a rate with a minimum.** Our `charges` field takes a flat amount
or value x cover x rate. A minimum ("0,15 per kg, at least 45") is the one form it cannot hold yet.

**Insurance.** Sum insured is goods value plus freight plus 10 % (DSV). 5U used 110 % of the goods value alone.
Premium rates are not published by German forwarders. One blog gives 0,3 to 0,7 % with a minimum of 35 to 50
USD (tier 3). 5U used 0.40 % and 0.30 % and no minimum. A minimum premium is the cheap next twist.

**Quote terms.** DHL: "DGF is bound to offers for 7 calendar days". Its quotes exclude "issue of export
declaration", "insurance fees", "storage", "separately processed x-ray checks". So a real quote is the freight
plus a list of things that are not in it. A customer who says "all-in" is asking to pull those inside.

## 2. Who carries what: Incoterms

The Incoterm decides which lines belong in the seller's quote. Seven of the eleven rules fit air freight. FOB
and CIF are sea rules, and a mail that says "FOB Frankfurt" by air is a mismatch a forwarder reads as FCA.

| Term | Seller pays main carriage | Seller insures | Seller pays destination |
| --- | --- | --- | --- |
| EXW, FCA | No | No | No |
| CPT | Yes | No | No |
| CIP | Yes | Yes, Institute Cargo Clauses A | No |
| DAP, DPU | Yes | No duty | Delivery, no import duties |
| DDP | Yes | No duty | Delivery and import duties |

Sourced: CIP (ICC Academy: "The seller must obtain insurance that complies with coverage provided by Clauses
'A'"). The other rows are trade knowledge, not read at an ICC source in this run.

**What this means for us.** Round 91 was CIP written out in plain words. DAP written out is "deliver to the
consignee's door in Mexico City". DDP written out is "include duties". We have no price source for either, so
when it comes the number will be in the mail or in a new sheet.

## 3. Liability and paper

- **Airline liability is capped at 26 SDR per kg** of gross weight (Montreal Convention, limit since
  28 Dec 2024). On 100 kg of electronics worth 22000 EUR that covers a fraction. Hence insurance.
- **A stated goods value creates a duty.** ADSp 2017, clause 21.2.2: when the order names a "Warenwert für eine
  Versicherung des Gutes", the forwarder is presumed to have to insure. A customer who only mentions a value
  may expect cover. Speculation: 5U could score a quote that ignores a stated value as too low.
- **Claims have deadlines.** Damage 14 days, delay 21 days, court action 2 years (Montreal, articles 31 and 35).
- **Export declaration** is needed above EUR 1.000 value or 1.000 kg (zoll.de). Splitting a shipment to stay
  under the limit is not allowed. Almost every shipment we quoted needs one. No customer has asked who files it.
- **Unknown shipper.** Cargo from a company that is not a known consignor is "unsicher" and must be screened
  before loading (LBA). It costs time and money. That is the X-ray line above.
- **Sanctions.** BAFA: "Derzeit existiert kein Totalembargo". The hard no is a listed person, a listed good, or
  a destination rule such as dual-use goods to Russia. Everything else is hold and ask.
- **Lithium batteries.** UN3480 (batteries alone) is "forbidden for transport as cargo on passenger aircraft"
  (IATA 2026 guidance). From 1 January 2026 batteries packed with equipment fly at 30 % charge at most.

## 4. What happens after the booking

The Cargo iQ route map is the airline industry's own list of stages: booked (BKD), accepted (RCS), departed
(DEP), arrived (ARR), broken down (RCF), customer notified (NFD), delivered (DLV), proof of delivery (POD).
Each stage has a way to fail:

| Event | Code | What the forwarder does |
| --- | --- | --- |
| Re-weigh at acceptance, weight differs | CCA (charges correction advice) | New chargeable weight, new price, tell the customer |
| Offloaded from the booked flight | OFF | Re-plan, new arrival date, tell the customer before they ask |
| Pieces missing or damaged | DIS | Report, start the claim inside 14 days |
| Cancelled by the airline | CNL | Rebook on the next best option |
| Booking changed late | Handler fee | Munich: "Surcharge confirmation less than 2 days: 25%" |

We have seen none of these from 5U. Our tracking scored 5 instead of 10 on rounds 7, 32 and 59 with no reason
given. Speculation: the key holds a status we did not have.

## 5. What 5U actually tested, in order

| When (CET) | Rounds | What changed | What it costs to miss |
| --- | --- | --- | --- |
| Sat 16:00 | 1 to 9 | Plain quote, pickup, weight breaks, three languages | Baseline |
| Sat ~17:00 | 10, 11 | Dangerous goods in the attachment, mail says none | R11 lost |
| Sat ~17:30 | 15, 20 | Pickup town in the signature, no postcode | R20 lost |
| Sat 18:38 | 27 | Rate API down | Survived, airlines answered by mail |
| Sat ~19:30 | 33 | Packing list contradicts the mail | R33 lost |
| Sat ~20:15 | 42 | "Do not offer Zephyr, now or in future" | R42 lost, corrected by 5U |
| Sat 20:29 | 45 to 50 | Booking API down, airline books 10 % higher | Adjustments of -10 to -32.5 |
| Sat 22:17 | 63, 65 | Offers as PDF, Word, voice message | R63 lost |
| Sun ~00:00 | 76 | A formal offer document demanded | R76 lost |
| Sun ~00:37 | 86, 87 | Customer changes the shipment after the quote | No round lost |
| Sun ~00:45 | 88 | Cancellation | No round lost |
| Sun ~00:50 | 89, 90 | Several shipments in one mail | No round lost |
| Sun ~01:00 | 91, 92 | Insurance inside the all-in price | R91 lost, 10 of 11 teams lost |
| Sun 01:19 | 93 | Rate API down and its airlines silent | R93 lost, 13 of 13 teams lost |

Eight rounds lost of 93, and each was the first or second round of a new kind. We lose the first one and hold
the next. That is the cost of learning from the verdict. Times with ~ are approximate.

## 6. Our predictions against what came

`docs/likely-changes.md` listed 14 changes on Saturday afternoon, read from the API spec.

| Predicted | Came | Note |
| --- | --- | --- |
| Portal down (3) | Yes, R27 and R93 | R93 added the twist we did not predict: the mail fallback was dead too |
| Booking API down (4) | Yes, R45 | Built before it came |
| Carriers need more facts (9) | Yes | |
| Per kg instead of a total (10) | Yes | |
| Customers write differently (12) | Yes, far beyond the guess | Attachments, voice, contradictions |
| Mail that tries to steer us (14) | Yes, mildly | |
| New tariff, tariff not valid yet (1, 2) | Not yet | `dataset_version` still `v1` |
| Other currency (7) | Not yet | `fx_eur_per_usd` unused for 10 hours |
| Lower limit, shorter validity (5, 6) | No | |
| Insurance, change after quote, cancellation, multi-shipment, offer document | Came, not predicted | |

**Why we missed five.** We read the API for levers. The API only describes the price sources. Everything that
came unpredicted lives in the customer's mail, and comes from the trade, where a deal has a life after the
quote. The API tells us how 5U breaks a source. The trade tells us what the customer asks next.

## 7. The extended pattern

5U sells four workers: "Repetitive Quoting", "Status Chasing", "Financial Reconciliation", "After-Hours
Messaging". Its CEO named three test cases in July (CargoForwarder, 28 Jul 2026): "an expired surcharge, a
customs broker joining a thread halfway, a rush request at midnight."

**Used so far:** repetitive quoting (all of Saturday), status chasing (tracking), the rush request at midnight
(round 93 asked for the fastest at 01:19 with half the lane dark).

**Not used yet:** the expired surcharge, the broker joining a thread, financial reconciliation.

Three moves repeat, and each new wave is one of them applied to the next stage of the deal:

1. **Move the fact.** The number that decides the price moves out of the mail body: into an attachment (R11,
   R33), a voice message (R65), an earlier thread (R42), a later mail (R86).
2. **Break a source.** A system we rely on stops, and the fallback is the test (R27, R45, R93). Each outage is
   harder than the last: first the API, then the booking, then the API plus the mail fallback.
3. **Widen the deal.** One more thing a real customer expects inside the answer (pickup, an offer document,
   insurance, several shipments).

**Why it gets harder.** The moves now combine. Round 93 was a source outage on a "fastest" request, where the
missing airlines are the ones that win. A combined wave has no second round to learn from, because the field
verdict (0 of 13) says only that everyone failed.

## 8. What comes next, ranked

Likelihood is our estimate. Each row names the earliest signal and what holds it.

| # | Wave | Why we expect it | Earliest signal | What holds it |
| --- | --- | --- | --- | --- |
| 1 | More lines inside "all-in": export declaration, X-ray, dangerous goods fee, delivery at destination | Insurance opened the door one hour ago. The trade has 20 such lines | "all-in including", "DAP", "door", a fee with an amount | `charges` takes any line with stated terms. Add a minimum to its form |
| 2 | The expired surcharge, tariff v2 | Named by 5U's CEO. `dataset_version` and sheet validity dates exist | A carrier mail with a file and no thread, `dataset_version` not `v1` | Sheets keep validity dates (built). Test it once on the fake 5U |
| 3 | Zephyr's return | Round 42: "for any of our future inquiries". A planted line with no payoff yet | A mail from Meyer Industrietechnik on a lane where Zephyr is cheapest | The note in the CRM (built). Check that it reaches a new thread |
| 4 | A third party joins the thread | Named by 5U's CEO | A new sender in a customer thread | Tools mail only people in the thread. Decide who counts |
| 5 | Events after booking: re-weigh, offload, cancel | Cargo iQ stages. Tracking scored 5 of 10 three times | An airline mail in a booked thread that is no confirmation | Carrier replies wake the agent only for a confirmation today |
| 6 | Reconciliation: the airline's invoice differs from the booked rate | A 5U product line. Booking at +10 % was the first step | A mail with "invoice" from a carrier | Nothing built |
| 7 | Another currency | Fields in the API for 10 hours | `currency` not EUR | `pricing.to_eur` (built) |
| 8 | The right answer is no | Verdict `voided` exists. Lithium alone on a passenger flight, a listed consignee | UN3480, a sanctioned destination | The agent may decline with a reason. No rule built |
| 9 | Haggling | 5U said at 15:15 a counter-offer "can happen at some point" | "Your competitor offers" | Prompt: we do not negotiate, the price stands |

**Our one bet.** Wave 1 comes first and combined with a source outage, because both were introduced in the
last hour and 5U combines its newest moves.

## 9. How to change the system

Per `vision.md`: a new capability is a tool or a field a tool returns. Three changes, smallest first.

1. **`charges` with a minimum** (one more field: `minimum_amount`). Covers "0,15 per kg, at least 45".
   Kind: every line of the trade's fee lists. Place: `pricing.charge`.
2. **A carrier mail in a booked thread wakes the agent.** Today only a confirmation does. Kind: every event
   after booking. Place: the router in `forwarder.py`. The agent judges what the customer must hear.
3. **`no_price_from` for every source, not only the portal.** Built for the portal in pull request 8. The same
   field should name a trucker that has not answered. Kind: any quote built on half the market.

What we should not build: a rule per Incoterm, a sanctions list, a fee table from DHL's price list. 5U's key
cannot contain numbers it did not give us.

## 10. For the pitch

**How an air export quote gets made today, and where the hours go.** A request arrives by mail, often with
the facts in an attachment. A person reads it, works out the chargeable weight, opens two or three airline
portals, mails the airlines that have none, waits, opens the rate sheets, adds the pickup and the fee lines,
and writes the reply. 5U's own figures (CargoForwarder, 28 Jul 2026, company claim): a forwarder receives 200 to
300 quote requests a day, "three or four people do nothing but answer them", and a quote takes about 15 minutes
by hand against about 2 with the agent. At 250 requests and 15 minutes that is 62 hours of work a day.

**Market size, honestly.** This research found no sourced figure for the number of forwarders or the spend on
quoting. Any number on a slide would be a guess. The defensible claim is per desk: three to four people per
250 daily requests, from the source above.

**Why now.** Two facts from this weekend, both ours. A model reads a packing list, a Word letter and a voice
message well enough to price from them (rounds 33, 63, 65). And prices computed by code survive it: in 93
rounds no lost round was an arithmetic error. Every lost round was a fact we did not have or did not look for.

**The belief that would kill the pitch.** A 5U judge believes an agent that quotes on its own will one day
send a wrong price and nobody will know why. The fact that breaks it: in our system the model never produces a
number. Every total comes from `pricing.py`, every quote records the option it came from, and for each of the
eight lost rounds we can name the missing input (round 91: 96.80 EUR of insurance. Round 93: two airlines with
no price). Speculation: this is the belief. We have not asked a judge.
