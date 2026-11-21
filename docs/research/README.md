# Branch `research/pricing`: what it did and what to take

For Mattia and his assistant. Sam's research chat works here, never on main.
**Main up to `dea5acc` (agent on the Responses API, Jan's synthetic mails) is merged in (`155f295`), so the
branch merges into main without conflicts.**
See everything at once: `git diff origin/main...origin/research/pricing`. `make test`: 31 passed.
Sam approved the tone of the three example mails in `prompts/forwarder.md` (Sat 15:50).

## What changes in the agent's engine

| Where | Change | Default |
| --- | --- | --- |
| `forwarder.options()` + `pickup_variants()` | Which trucker an option carries follows `PICKUP_RULE`: `asked` (cheapest, and the fastest as option `A1f`), `cheapest` (one option per airline, cheapest trucker), `balanced` (one option per airline, the 50/50 trucker). `recommended` follows it, so the agent quotes it | `asked` = main today |
| `forwarder.options()` | A request without a preference gets `UNSPECIFIED_RULE` (`balanced`, `cheapest`, `fastest`) as `recommended`; the 50/50 formula is `BALANCE_RULE` (`ratio`, `minmax`) | `balanced`, `ratio` = main today |
| `forwarder._ask_everyone()` | An airline with no sheet and not on the portal is also asked at the next break up (`pricing.breaks_to_try`) | new: 1 or 2 more mails on 5 destinations |
| `forwarder.waiting_for()` | `get_offers` waits per request mail, not per sender (a carrier asked at two weights answers twice) | same result when every carrier is asked once |
| `forwarder.eur()` -> `pricing.to_eur()` | Exchange rate per currency; a rate stated in a bid mail is read (`fx_eur_per_unit` in the bid form and `prompts/bid.md`) | EUR prices unchanged |
| `pricing.balanced()`, `pricing.quote(..., pickup_rule, balance, unspecified)` | The rules as pure functions, with tests on the live zone-60 trucker bids | unchanged |
| `prompts/forwarder.md` "How you write", `options()` rows carry `billed_kg` | Writing criteria from the humanizer checklist and three example mails: answer first, no thanks-for-your-request opener (27 of 35 carrier mails have one), one forwarder detail, a close that changes | prompt text only |

Why: `docs/research/pricing.md` (evidence and numbers). **Round 1 (Sat 16:00, `docs/research/round-log.md`)
settled half of the open rule: a "fastest" request is scored with the fastest trucker (or the 50/50 pick), not
the cheapest. Leave `PICKUP_RULE` at its default `asked`.** Before the round I estimated `cheapest`; that was
wrong and would have cost accuracy points.

## Rules the engine keeps (all in `forwarder.py`, under `get_offers`)

1. **Which weight to ask.** Sheet airline: its sheet's cheapest billed weight (`sheet_price` returns it).
   Portal: actual weight, plus the next break when `next_break / chargeable < 1.5`. Airline with no sheet and not
   on the portal (Zephyr, Himalaya Bridge, Lagoon Isles, Pampero; only they fly to ASU, KTM, PPT, TNR, ULN):
   chargeable weight plus `breaks_to_try`. On the sheets the next break is cheaper for 14.0 % of weights, by
   more than 5 % for 8.4 %.
2. **When to price.** When every request mail is answered or the deadline passed. Count answers per request
   mail, not per sender: a carrier asked at two weights answers twice. Carriers answer in one batch about 30 s
   after the request.
3. **Which price wins per carrier.** A live price (portal, mail) replaces that carrier's sheet; of two live
   prices the cheaper (`best_by_carrier`).
4. **The total.** Air leg plus trucker for door-to-port, one number, from `pricing.quote` only. The model never
   adds, converts or rounds. `language.money_ok` checks the mail carries exactly that amount.
5. **Bid mails name the weight on its own line** (`Total weight: 320 kg`), else the carrier asks back and 30 s
   are gone (`docs/learnings-carriers.md`).

## Cost budget for an agent (prices from `llm.py`, rule from the brief)

Cost points per accepted quote = 40 x (1 - spend / 0.10 USD). **Every 0.01 USD is 4 points.** Spend is the
whole hour's gateway spend divided by the accepted quotes of that hour, so tokens for rejected quotes, tracking,
status mails and tariff sheets count too.

| Per accepted quote | `gpt-6-luna` cost | Cost points |
| --- | --- | --- |
| Agent as built: about 3 turns (get_offers, send_mail, journal line), about 10k input, 0.5k output | about 0.001 | 39.6 |
| 10 turns x 8k context, nothing cached, 2k out | 0.0090 | 36.4 |
| Same, 80 % of the input cached | 0.0032 | 38.7 |
| 25 turns x 15k context, nothing cached, 5k out | 0.0400 | 24.0 |

The first row is my estimate from the prompt and tool sizes, not a measurement: read the real number from
`cost_usd` in the events of the first live deals.

`gpt-6-luna`: 0.10 USD per million input tokens, 0.01 cached, 0.50 output. `gpt-5-nano`: 0.05 / 0.005 / 0.40.
Cached input costs a tenth, so the order of the prompt decides: what never changes first (system prompt, tool
definitions, kit facts), the order's own mails and tool results last. Not verified on the gateway: whether it
passes OpenAI's prompt caching through (check `usage.prompt_tokens_details.cached_tokens` on the second call).

## Tracking: ask the airline before the first answer (commit `6c761dd`, take it or leave it)

5U at the booth (`origin/jan:docs/news.md`): the shipment status comes from the carrier, by mail, and only our
first answer to a tracking question counts. Worth 10 points per booked shipment. Three gaps on main:

1. `prompts/tasks/tracking.md` says to answer from the CRM. The CRM holds the booking and an estimated arrival
   (`booked_at + transit_days`), no carrier status.
2. A tracking thread has nothing to price, so `get_offers` with shipment null returned
   `no shipment yet` and the agent could not wait for a carrier's reply.
3. `crm` returned the airline's name, not its address, and `mail_carrier` needs the address.

The commit closes all three: `collect_offers` waits and returns `carrier_messages` when there is nothing to
price, `crm` returns `airline_email`, the task prompt says the airline knows the status. Costs about 35 s and
two or three more turns per tracking question. Not verified live: what a 5U carrier answers to a status
question (the fake's wording is assumed), and whether 5U times the tracking answer.
Tests: `test_a_tracking_session_can_ask_the_airline_and_wait_for_its_status`,
`test_crm_gives_the_airlines_address_for_a_status_question`.

## Open: decided by the first scored rounds, not by us

- "Cheapest" with pickup: cheapest trucker or the 50/50 pick. And the 50/50 formula. Round 1 only showed that
  "fastest" does not take the cheapest trucker.
- Whether a quote below the best price is accepted.

`backend/research/rounds.py` (read-only: GET on board and mailbox, no mail, no portal, no gateway) lists per
request the bids that arrived and the trucker each rule would take, next to `/v1/board/me`. Results go to
`docs/research/round-log.md` on this branch.
