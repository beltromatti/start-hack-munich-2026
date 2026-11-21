# Round log: what 5U scored and what it teaches

Read-only (`backend/research/rounds.py`: GET on board and mailbox). Times in CET. Newest finding on top.

## What the rounds have settled so far

| Question | Answer | Evidence |
| --- | --- | --- |
| "Fastest" with pickup: which trucker is in the best price? | **Not the cheapest.** The fastest trucker (or the 50/50 pick, both the same truck in round 1) | Round 1: quote with the fastest trucker got full accuracy |
| Is the next break part of the best price? | Yes | Round 1: 966.93 kg chargeable, booked and scored at 1000 kg |
| "Cheapest" with pickup: cheapest trucker or the 50/50 pick? | open | no such round yet |
| Fastest trucker or 50/50 pick, when they differ? | open | in round 1 both rules pick Westfalenroute |

## Round 1, Sat 16:00: accepted, 60 of 60 before cost points, booked

Request (lindqvist-medtech@): fastest to ORD, trucking from 51447 Bergisch Gladbach (zone 51, CGN), 12 pieces,
676 kg, 5.79 cbm (966.93 kg chargeable), ready 25 Nov.

| Trucker | EUR | Pickup |
| --- | --- | --- |
| Elbkante Logistik | 134.69 | 29 h |
| Westfalenroute | 220.03 | 11 h |
| Maintal Transport Logistik | 222.36 | 13 h |
| Bodenseefracht | 269.71 | 12 h |

Our quote, 39 s after the request: Meridian Freightways (portal, 1 day, billed at 1000 kg) 3010.00 + Westfalenroute
220.03 = **3230.03 EUR**. Verdict accepted, total 60.0 = accuracy 45 + time 15 (cost points come hourly).
Booked on the portal: BK-3ZY8SE7F, price 3010.00 EUR, weight 1000 kg.

What it proves: with the cheapest trucker (134.69) in 5U's best price our quote would have been 2.7 % above it
and could not have had full accuracy. So for a "fastest" request the trucker is not the cheapest.
`PICKUP_RULE=cheapest` would have quoted 85.34 EUR under the best price. **Keep `PICKUP_RULE=asked` (the default,
main's behaviour).** My estimate before the round was wrong.

Field: 14 teams, 5 answered, 3 accepted (MAKEANOTHERMD 60.0, START Milan 60.0, Mythos 48.11).
Carriers answered 34 s after the request, all in EUR. Five sheet airlines were asked for CGN-ORD and all said
"we do not serve this lane" (their sheets have no such lane): no price lost, five mails and five reads spent.

How 5U's customers write (first real mail): one paragraph, "Hi,", IATA code plus city ("ORD (Chicago, US)"),
"all-in price in EUR", trucking asked for in words ("Please arrange trucking from our site in 51447 ..."),
signed with first name and company on two lines.
