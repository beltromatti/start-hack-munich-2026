# Likely changes: what 5U can change each hour, how we notice first, how we respond

Question 4 of the research brief. 5U: "After a few hours the setup changes about once an hour, unannounced.
Teams learn of a change from failed quotes." A failed quote is the last signal, it costs 100 points. Every change
below has an earlier one. Sources: `docs/challenges/5u-api/openapi.json` (the fields and error codes 5U built
in are the changes it planned), the live mailbox before 16:00, the brief. Likelihood is my estimate.

## Baseline (measured Sat before 16:00, `docs/learnings-carriers.md`)

Carriers, truckers and the rate desk answer in one batch about 30 s after our mail. All 34 portal rates and all
35 mails are EUR. `dataset_version` is `v1`. Portal limit 10 rate reads per minute. A rate is valid 15 min.
The lanes six carriers named by mail equal their portal or sheet lanes exactly (100 lanes, 0 differences).

## Changes, earliest signal, response

| # | Change | Why we expect it | Earliest signal (in code, before a quote fails) | Response |
| --- | --- | --- | --- | --- |
| 1 | New tariff for an airline | Brief: "The airlines also send monthly tariffs"; `Rate.dataset_version` exists | Mail from a carrier that answers nothing, with a file; `dataset_version` not `v1` on any portal rate; a sheet airline's mail price differs from its sheet price | green: ingest, the live price already wins over the sheet. yellow if the mail price and the new sheet disagree |
| 2 | Tariff that is not valid yet (December sheet) | Sheets say "valid 01.11. to 30.11."; "Read the rate sheets closely" | `valid_from` later than today on the ingested sheet | green: sheets keep their validity, the price uses the one valid on the ready date (`kit.add_sheet`, `kit.sheet(on=)`) |
| 3 | Portal down for a lane or airline | `GET /rates`: "503 with a message that says where to get the rate instead" | 503 on a rate read | green: mail the airline (built), or the rate desk |
| 4 | Booking by API down | `POST /bookings`: "503 ... how to book by email with the airline" | 503 on booking | green: book by mail in the bid thread (built) |
| 5 | Lower portal limit | "Limits may be tuned"; header `X-RateLimit-Limit` | header value below 10; 429 | yellow: one call per airline, next break only when within 10 % |
| 6 | Shorter rate validity | `valid_until` per rate; booking 410 "expired" | `valid_until` minus now under 15 min | green: re-fetch at booking (built for the portal). Mail bids: ask again |
| 7 | Prices in another currency | `currency`, `fx_eur_per_usd` on every rate | currency not EUR on a rate or in a bid | green with `pricing.to_eur`; red if no rate is stated anywhere |
| 8 | Carriers answer slower | Reply delay is a setting of 5U's agents | last reply later than 75 s after the request (`research.rounds`: SLOW) | yellow: quote at the deadline with what is there; raise the wait only while the total stays under 2:00 |
| 9 | Carriers need more facts | Seen live: "To quote we need: the total weight in kg" | reply without amount that asks back (ASKED BACK) | green: answer in the thread from the request's facts; add the line to the request template |
| 10 | Carrier quotes per kg, not a total | Real carriers do; the bid prompt already allows `total` null | bid with rate but no total (FORMAT) | yellow: compute in the engine with the sheet rule, never in the model |
| 11 | New lanes, lanes closed | `GET /ports` is live; carriers list their lanes by mail | `ports` differs from the last read (refreshed every 15 min) | green: lane map follows; a closed lane gives "we do not serve" |
| 12 | Customers write differently | Deep dive: "tricky emails", other languages, missing facts | parser returns `missing`, `flags`, or `unspecified` | green: ask once. red: flags like dangerous goods |
| 13 | Scoring detail changes | Verdict `voided` exists; cost points land hourly | reason codes and points per kind on `/v1/board/me`; accepted share per hour | yellow: compare our pick with the rules in `pricing.md` |
| 14 | Mail that tries to steer us | Deep dive: attacks on the mailbox are "a possibility"; teams cannot mail us (422) | sender not a customer thread, carrier or desk; instructions in a body | green: prompts treat mail text as data; route by sender |

## What Jan's prediction engine can and cannot do here

It was trained on real-world news for residual values. The 5U world is a simulation with its own clock: no
outside news explains it. What a small model can predict from our own register after a few hours: reply delay
per carrier, acceptance per lane and weight band, which carrier wins a lane. What it cannot predict: the next
unannounced change. Honest pitch line: we detect a change within one round from the signals above, we do not
forecast it.
