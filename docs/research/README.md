# Branch `research/pricing`: what it did and what to take

For Mattia and his assistant. Sam's research chat works here, never on main. Branched from main `ddfb03e`.
See everything at once: `git diff origin/main...origin/research/pricing`. `make test`: 21 passed.

Written after the 15:35 talk: the forwarder moves from a workflow to **one agent per order** with tools, a
register that tells the truth, and the **price engine as a tool**. So this branch keeps its findings where they
survive that change: in `pricing.py` (pure functions, no workflow state) and as rules for the agent's tools.

## Take as is: price engine (`backend/app/pricing.py`, `config.py`)

| Commit | Function | What it settles |
| --- | --- | --- |
| `d077f79` | `quote(..., pickup_rule, balance, unspecified)`, `balanced(offers, rule)` | Which trucker goes into the all-in total is undocumented; the candidates differ by 88.80 EUR in zone 60. Three `.env` switches (`PICKUP_RULE`, `BALANCE_RULE`, `UNSPECIFIED_RULE`), defaults = behaviour so far |
| `7daaaf6` | `breaks_to_try(cw)` | For a carrier with unknown breaks: the breaks above the chargeable weight that can still be cheaper (280 kg: 300; 230 kg: 250 and 300) |
| `9a7f28e` | `to_eur(amount, currency, fx, rates)` | Exchange rate per currency; a price with no known rate is dropped, never guessed |

`7daaaf6` and `86205fb` also patch `forwarder.py` (`start_rfq`, `ready`, `eur`) and the bid form. If the
workflow is being replaced, skip those hunks and keep the rules below.

Evidence and numbers: `docs/research/pricing.md`.

## Rules the agent's tools have to keep (today they live in `forwarder.py`)

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
| Workflow today (measured by Mattia, about 0.0008 USD) | 0.0008 | 39.7 |
| Agent, 10 turns x 8k context, nothing cached, 2k out | 0.0090 | 36.4 |
| Same, 80 % of the input cached | 0.0032 | 38.7 |
| Agent, 25 turns x 15k context, nothing cached, 5k out | 0.0400 | 24.0 |

`gpt-6-luna`: 0.10 USD per million input tokens, 0.01 cached, 0.50 output. `gpt-5-nano`: 0.05 / 0.005 / 0.40.
Cached input costs a tenth, so the order of the prompt decides: what never changes first (system prompt, tool
definitions, kit facts), the order's own mails and tool results last. Not verified on the gateway: whether it
passes OpenAI's prompt caching through (check `usage.prompt_tokens_details.cached_tokens` on the second call).

## Tracking (5U at the booth, `origin/jan:docs/news.md`; not built here)

The status comes from the carrier by mail, and only our first answer to a tracking question counts. So the
answer has to wait for the carrier's reply (about 30 s) unless a fresh status is already in the register.
Answering at once from `booked_at + transit_days`, as `on_tracking` does today, risks the +10 per shipment.
Jan's steps 3a to 3c in `origin/jan:docs/flow.md` describe the flow.

## Open: decided by the first scored rounds, not by us

- Trucker rule (cheapest, 50/50 or the fastest when asked) and the 50/50 formula. My estimate until then:
  `PICKUP_RULE=cheapest`.
- Whether a quote below the best price is accepted.

`backend/research/rounds.py` (read-only: GET on board and mailbox, no mail, no portal, no gateway) lists per
request the bids that arrived and the trucker each rule would take, next to `/v1/board/me`. Results go to
`docs/research/round-log.md` on this branch.
