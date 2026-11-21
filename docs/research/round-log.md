# Round log: what 5U scored and what it teaches

Read-only (`backend/research/rounds.py`: GET on board and mailbox). Times in CET. Newest finding on top.

## What the rounds have settled so far

| Question | Answer | Evidence |
| --- | --- | --- |
| Which trucker is in 5U's best price? | **The 50/50 one: price and pickup time, each relative to the best on offer** (`BALANCE_RULE=ratio`). Not the fastest, not the cheapest | Round 1: Westfalenroute, full accuracy. Round 2: Bodenseefracht, we took the fastest and lost 10.86 points |
| Does the customer's "fastest" change the trucker? | No. Both rounds asked for fastest; round 2's best price has the slowest, cheapest trucker | Round 2 |
| How are accuracy points computed? | 45 x (1 - excess / 10 %): 4.5 points per 1 % above the best price | Round 2: 2.41 % above gives 34.14, to the cent |
| Is the next break part of the best price? | Yes | Round 1: 966.93 kg booked at 1000 kg. Round 2: 1800.26 kg booked at 2000 kg |
| "Cheapest" with pickup: the same 50/50 trucker? | open, expected yes (one rule for the trucker) | no such round yet |

**Action: `PICKUP_RULE=balanced` (now the default on this branch).** Main today takes the fastest trucker for a
"fastest" request. That was right in round 1 by coincidence and cost 10.86 of 60 points in round 2.

## Round 2, Sat 16:07: accepted, 49.14 of 60, booked

Request (sonnberg-roesterei@): fastest to JFK, trucking from 61018 Bad Homburg (zone 61, FRA), 6 pieces, 1233 kg,
10.78 cbm (1800.26 kg chargeable), ready 25 Nov.

| Trucker | EUR | Pickup | price / lowest + hours / fewest |
| --- | --- | --- | --- |
| Bodenseefracht | 119.01 | 30 h | 1.00 + 1.30 = **2.30** |
| Nordlicht Haulage | 152.01 | 30 h | 1.28 + 1.30 = 2.58 |
| Hansekogge Trucking | 245.02 | 23 h | 2.06 + 1.00 = 3.06 |
| Westfalenroute | 266.03 | 23 h | 2.24 + 1.00 = 3.24 |
| Spessart Spedition | 299.03 | 25 h | 2.51 + 1.09 = 3.60 |

Our quote, 39 s after the request: Solace Air Cargo (portal, 2 days, billed at 2000 kg) 5100.00 + Hansekogge
(the fastest trucker) 245.02 = **5345.02 EUR**. Accepted, 49.14 points = time 15 + accuracy 34.14.

With Bodenseefracht the total is 5219.01. Ours is 2.4144 % above that, and 45 x (1 - 0.24144) = 34.14: the
score fits a best price with Bodenseefracht to the cent. No other trucker fits (Nordlicht would give 37.0,
Hansekogge 45). Round 1 by the same formula: Westfalenroute 1.63 + 1.00 = 2.63 is the lowest, the cheapest
(Elbkante, 1.00 + 2.64) is not. `pricing.balanced(offers, "ratio")` picks both; the fastest, the cheapest and
`minmax` each miss one round. Test: `test_the_trucker_in_5us_best_price_is_the_ratio_balanced_one`.

Field after round 2: MAKEANOTHERMD 120.0, START Milan 109.14, Google 92.52, PIXEL 83.61.

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
and could not have had full accuracy. Westfalenroute is the fastest trucker and also the 50/50 pick, so round 1
alone could not tell these two apart. Round 2 did.

Field: 14 teams, 5 answered, 3 accepted (MAKEANOTHERMD 60.0, START Milan 60.0, Mythos 48.11).
Carriers answered 34 s after the request, all in EUR. Five sheet airlines were asked for CGN-ORD and all said
"we do not serve this lane" (their sheets have no such lane): no price lost, five mails and five reads spent.

How 5U's customers write (first real mail): one paragraph, "Hi,", IATA code plus city ("ORD (Chicago, US)"),
"all-in price in EUR", trucking asked for in words ("Please arrange trucking from our site in 51447 ..."),
signed with first name and company on two lines.
