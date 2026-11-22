# Likely changes: what came, where the points went, what comes next

Sun 22 Nov 2026, 02:35 CET, after round 102. This replaces the list of Saturday afternoon. Its 14 changes are scored
in section 3. The trade behind the waves is in `docs/industry.md`.
Sources: `/v1/board` and `/v1/board/me` at 02:16 (one read each), the customer and carrier mails of rounds 81 to
101, our four prediction lists. A guess is marked as one.

## 1. Where we stand

- Rank 1 with 9539.74. Leylü 8808.70 (731 behind), Mythos 8765.53, Google 8434.77, TALOS 8037.78.
- From 01:15 to 02:16 we gained 205 points. TALOS gained 1897, Leylü 955, Mythos 764.
- 87 of 102 rounds accepted. Rounds 101 and 102 were accepted by every team that answered.
- `main` is ab5d5d8 of Sat 23:19. Every fix written since then sits on a branch (section 5).
- Board rule since round 92: a round that only 1, 2 or 3 teams get accepted counts 10, 5 or 3 times for them. One
  such round is worth up to about 1000 points. Our lead is smaller than that.
- A request comes every 6 minutes. If that runs until noon (not confirmed), about 95 rounds are left: as many as
  we have played.

## 2. Where the points went

An accepted round brings 106 points on average, without the jury's 10. About 1730 points are gone:

| Kind | Rounds | Points | What happened |
| --- | --- | --- | --- |
| A price source was dead or half dead | 93 to 100 | 8 rounds, about 850 | All eight asked for the fastest option. 93: rate API 503 and the lane's two portal airlines silent by mail. 94: answered after 499 s (`out_of_time`). 95 to 99: the lane's portal airline was missing from our options, we offered the next fastest mail airline, and it was cheaper (`too_low`). 100: no price at all, and we wrote to the customer anyway (`declined_in_scope`) |
| A fact was not in the mail body | 11, 20, 33, 63 | 4 rounds, about 425 | Dangerous goods in the attachment, the pickup town in the signature, the packing list against the mail, offers as PDF, Word and voice |
| A wish of the customer was not carried out | 76, 91 (5U corrected 42) | 2 rounds, about 210 | The offer as a PDF. Insurance inside the all-in price (96.80 EUR) |
| LLM cost | all | 96 | 38.87 of 40 on average |
| Accuracy under 45 on an accepted quote | 2, 9, 27, 28, 62, 67, 69 | 52 | The wrong trucker (2: -10.86. 67: -21.73, "28 hours". 69: -7.33, "seven hours"), the portal asked with the wrong weight (27: -5.68), 117 for 116.9 kg (28). Round 9 (-5.93): cause not known |
| Adjustments by 5U | 48, 49, 88 | 52.5 | A booking at +10 % that the confirmation did not say (-10, -22.5). The cancellation in round 88 (-20) |
| Tracking | 7, 32, 59, 65 (5 of 10), 62, 88 (0 of 10) | 40 | Round 88 was the cancelled booking. The others: not visible from our side |
| Time | none | 0 | Every accepted quote had the full 15, also at 100 s |

**Half of everything we lost went in 48 minutes, to one kind** (01:19 to 02:02). The teams that got rounds 95 to
100 accepted (TALOS five of six, Mythos four, Leylü three, Google three, read from the public bookings) booked the
lane's portal airline 83 to 358 s after the request. They waited for it. We answered in about 60 s with what we had.

## 3. What we predicted and what came

| List | Predicted | What came | Was a fix live in `main`? | Cost |
| --- | --- | --- | --- | --- |
| Sat afternoon, 14 changes read from the API | Rate API down | R27, R93, R95 to R100 | Yes for the plain case (R27). No for "the mail fallback is dead too" and "one airline is missing" | 8 rounds |
| | Booking API down | R45, R51, R52 | Yes | 0 |
| | Carriers ask back, or quote per kg | Yes | Yes | 0 |
| | Customers write differently | Far beyond the guess: attachments, voice, contradictions, lb and cubic feet (R82), a deadline (R83 to R85) | Partly | R11, R20, R33, R63 |
| | Scoring detail changes | Points at round end (18:36), cost window 18 min (21:00), the factor for few winners (R84, raised at R92) | No alarm | none directly |
| | New tariff, other currency, lower portal limit, shorter validity, closed lanes | Not yet | | |
| Sat 21:40, 14 kinds and a clock | "A new kind starts in a round divisible by 3" | No. R76, R88 and R91 started one round later | | Dropped |
| | Scans and pictures | R63, 37 minutes later | No | R63 |
| | A date in words | R65 | No | none |
| | The customer changes or cancels | R86 to R88, three hours later | No | -30 on R88 |
| | 11 more (a carrier in USD, slow carriers, two services, a send limit ...) | Not yet | | |
| Sun 00:30, after 5U's "new cases" | A booking changed or cancelled | R86, seven minutes later. R88 | On `sam/new-cases-prep`, not in main | -30 on R88 |
| | Two shipments in one mail | R89, R90 | No | none |
| | Incoterms and jargon, `.xls`, a carrier mail with no deal, a request out of scope | Not yet | | |
| | 7 ways the scoring could change | None of the 7. The factor for few winners came | | |
| Sun 02:00, `industry.md` | 9 waves. The bet: more lines inside "all-in", together with an outage | The outage came (R94 to R100), no new line did. Wave 9, a competitor's price, came first (R101) | The price stood | none |
| Sun 01:20 and 01:55, causes guessed without the round's mails | R91 is a withdrawn carrier bid. R95 to R98 are charges again | Both wrong. It was the insurance, then a missing portal airline | A guard was built for the wrong cause | 40 minutes |
| On no list | The offer as a PDF, insurance in the price, a deadline | R76, R91, R83 | No | R76, R91 |

**What this says.**

- The kind is often on a list hours before it comes (outage, scans, cancellation, two shipments, a competitor's
  price). The round never is.
- A list saved rounds only where the fix was live in `main` before the wave. The booking API down was: 0 rounds
  lost. A kind that was listed but not live cost the same as one nobody listed.
- Both causes guessed without the mails were wrong. Both causes read from the mails were right within minutes
  (Jan at 01:43, the portal airline at 02:12).
- 5U's next version of a kind is harder than our fix for the last one. Outage one was the rate API. Outage two was
  the API and the mail fallback. Outage three was a single airline.
- The cause of R91 was read at 01:43 and its fix passed the tests at 01:45. At 02:16 it is not in `main`. Eight
  rounds were lost in between.

## 4. What comes next, ranked by the points at stake

5U's three moves (`industry.md` section 7) applied to what is open. Likelihood and order are our estimate.

| # | Wave | Why we expect it | Earliest signal | What holds it | Where that is today |
| --- | --- | --- | --- | --- | --- |
| 1 | A price source dead or half dead, again and harder | Three times in ten hours, each harder, the last cost 8 rounds. 5U's own 503 text points at the portal page. Guess for the next twist: longer than our wait, a silent trucker, only the portal page works | 503, 404 or 429 on a rate read. An airline of the lane without a price 60 s after the request | Wait for the missing airline inside the 6 minutes (limit 240 s), ask the portal again every 20 s, ask the rate desk, show the agent `no_price_from`. Never write to the customer without a price (R63, R100) | `sam/charges-ready` 561c4ff, 63 tests, not merged. Reading the portal page by code: not built, done once by hand (FRA-ORD, Borealis, 320 kg: 1696.00 EUR) |
| 2 | Two known kinds in one round | R93 was an outage on a "fastest" request. The factor pays 5U's hardest rounds. Guess: insurance during an outage, a change to one of two shipments, a PDF offer with a deadline | None of its own | Every single fix live at the same time | None of tonight's fixes is in main |
| 3 | More lines inside "all-in" | `industry.md` section 1: the trade has 20 such lines. Guess: a minimum premium, a fee with a minimum, delivery at destination, and insurance "as per our frame agreement" with no numbers. R91 and R92 both named a frame agreement (Lindqvist 110 %, 0.40 %. Weidner 110 %, 0.30 %) | "all-in including", "frame agreement", an Incoterm (CIP, DAP, DDP), a percent, a minimum | `charges` by code in every total (flat, or value x cover x rate) | Pull request 8, not merged. Missing: a minimum, and the terms kept per customer. Notes reach a customer's next thread (main); whether these terms get noted is not checked |
| 4 | The deal after the booking | Came: a change before booking (R86, R87, held), a cancellation (R88, tracking 0 and -20; the customer asked four times for the airline's confirmation). Two lines are planted and not collected: "book the first now, we will confirm the second later" (R89 Hofmann, TLV 1812 kg. R90 Rheintal, GRU 1335 kg). Then the airline's side: offload, re-weigh, delay (`industry.md` section 4) | A mail in a booked thread that is no thank-you. An airline mail that is no confirmation | `DELETE /v1/portal/bookings/{ref}` (seen in 5U's API at 01:30), tracking that says cancelled, a second booking in the same deal after the rate expired | DELETE is used by no code. Airline news wakes the deal and tracking says cancelled: `sam/new-cases-prep` c5074c7, not merged |
| 5 | Zephyr's return | R42, Meyer Industrietechnik: "for this shipment or for any of our future inquiries". Planted, never collected | A mail from Meyer on a lane where Zephyr is the cheapest | The note on the customer reaches the new thread | In main, never checked on a new thread |
| 6 | A new sender | Named by 5U's CEO ("a customs broker joining a thread halfway"). 5U's API, read at 01:30, now lets us write to "any other outside sender that mailed you" | A sender who is no customer of the thread, no carrier, no desk | Today an unknown sender is a customer and gets a quote | Not built. Decide who counts |
| 7 | December | In rounds 81 to 101 the latest ready date was 29 Nov. The sheets are valid 1 to 30 Nov. 5U's CEO named "an expired surcharge" | A ready date in December. `dataset_version` not `v1`. A carrier mail with a file and no thread | Sheets keep their validity, a live bid wins over the sheet | In main. Open: a validity without a year lands in next year (333de15), fixed in 44f9499 on `sam/new-cases-prep` |
| 8 | A price from the customer | Came in R101: "another forwarder has already offered us about 1620 EUR all-in". Ours stood (flight 2230.00 plus pickup), accepted, 14 of 14. Guess for the twist: an anchor close to the true price, or a counter-offer after our quote | A price in a customer mail | Every total comes from a tool, margins are no part of the quote | In main, held once |
| 9 | The right answer is no | A verdict for a wrong decline exists (`declined_in_scope`). Lithium batteries alone on a passenger flight, a listed consignee, sea freight | A UN number in the mail body. A destination no carrier serves | The agent may decline with a reason | No rule built, and none should be (`industry.md` section 9) |
| 10 | Another currency | `currency` and `fx_eur_per_usd` sit unused in the API since Saturday | `currency` not EUR on a rate or in a bid. "Please quote in USD" | `pricing.to_eur` | In main. A sheet in USD is skipped without a word |
| 11 | Scoring | The factor came at R84 (5, 3, 2) and was doubled at R92. `frozen_at` and `scores_revealed` exist. The jury has given no humanity point since R74 | `rules` in `/v1/board` changes, `frozen_at` is set, a new `reason` | An alarm in the board watcher | `sam/new-cases-prep`, not merged |
| 12 | Limits and timing | In the API from the start: a lower portal limit, a shorter validity, slower carriers, a closed lane | `X-RateLimit-Limit` under 10, `valid_until` under 15 min, the last carrier reply later than 75 s, `ports` differs from the last read | One call per airline, re-fetch at booking, the lane map follows | In main |
| 13 | The airline's invoice differs from the booking | "Financial Reconciliation" is one of 5U's four workers | A carrier mail with "invoice" | Nothing | Not built. Least likely inside a 6-minute round |

## 5. What to prepare, in this order

No code is on this branch. Each point names where the code already is.

1. **Merge `sam/charges-ready`** (pull request 8 plus the 240 s limit and the portal retry). It holds waves 1 and 3,
   which cost 9 of the last 12 rounds. `make sim` has not run on it. After the merge a quote on a half-empty lane
   waits, so read the first "fastest" round in full.
2. **After a rejected round, read its mails before anyone builds.** The mails are only on the production machine.
   A copy of the register after each rejected round would let Jan and Sam read them too.
3. **Cancel a booking with 5U's DELETE call** when a customer cancels. Round 88 cost 30 points, and it will come
   back combined with something else.
4. **Replay four mails on the fake 5U before 5U sends them:** insurance "as per our frame agreement" from Lindqvist
   with no numbers. "Please book the second shipment now" in the thread of round 89, after the rate expired. A
   ready date of 2 December. A mail from an unknown sender inside a customer's thread.
5. **The alarm on `rules`, the factor, a new `reason` and `frozen_at`** (`sam/new-cases-prep`).
6. **The offer as a PDF.** R76 was lost for it. R81 asked again and was accepted (12 of 13 teams) although main
   cannot attach a file. Either 5U stopped checking, or production runs code that is not in main. If it is needed:
   `sam/pdf-offer` 5a17b9f, on Sam's Mac, not pushed.

What we should not build is in `industry.md` section 9: no rule per Incoterm, no sanctions list, no fee table. And
no fifth prediction list: after each wave, this file gets the row.
