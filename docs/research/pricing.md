# Pricing: where a quote can land outside 5 %

Research branch `research/pricing`, Sat 21 Nov 15:30, before the first RFQ. Questions 1 to 3 of the research
brief. Every number below was computed from the repo, Jan's answer key or the live mailbox snapshot. What is a
guess is marked as a guess.

## Short answer

| # | Finding | Points at risk | Status |
| --- | --- | --- | --- |
| 1 | `pricing.py` matches Jan's answer key in **18 of 18** priced cases, to the cent | none | checked |
| 2 | **Which trucker goes into the all-in total is undocumented, and the candidates differ by up to 88.80 EUR** (zone 60). On a 1000 EUR shipment that is 9 %: the quote is rejected | every door-to-port request under about 1600 to 1800 EUR | switch ready, rule open until the board shows it |
| 3 | The 50/50 "balanced" formula in `pick()` almost always returns the fastest offer | requests without a stated preference | switch ready |
| 4 | The 4 airlines without a sheet (Zephyr, Himalaya, Lagoon, Pampero) are asked at one weight only. On the sheets the next break is cheaper for 14.0 % of weights, by more than 5 % for 8.4 % | about 1 round in 100 (5 of 41 destinations) | patch 7daaaf6 |
| 5 | Currency: a non-EUR price is only converted when it is USD and a portal call brought a rate before | 0 today (all 34 portal rates and 35 mails are EUR), a likely hourly change | patch 86205fb |

## 1. Mechanics: answer key against `pricing.py`

`backend/research/check_key.py` prices every `quote` case of `origin/jan:backend/synthetic/expected.json` with
main's `pricing.sheet_price`, the forwarder's portal logic (actual weight plus next break when
`next_break / chargeable < 1.5`) and `pricing.quote`, offline from `portal_cache.json`.

```
cd backend && uv run python -m research.check_key <path to backend/synthetic>
mismatches: 0 | cache misses: []
```

Covered and correct: next break (299 kg billed as 300), volume weight (120 kg, 1.8 cbm = 300.6 kg), lbs just
under a break, breaks at 250 against 300 per airline, minimum before surcharges, surcharges on billed weight,
cheapest and fastest.

Limits of this check: the key was built with the same rules as `pricing.py`, so it proves the code, not 5U's
scorer. No case in the key prices the pickup leg, a non-EUR rate or a request without a preference. Those are
sections 2 to 5.

Also checked on all 158 sheet lanes:

- The `< 1.5` shortcut in `portal_offers` is safe. The largest drop between two breaks (rate plus surcharges)
  is 1.321 (Yellowtail MUC-JNB, 250 to 500 kg), so the next break is never cheaper once it is 1.5 times the
  weight. On the 17 cached portal pairs the largest drop is 1.22.
- Billing two breaks up is never the cheapest (0 cases for 1 to 2000 kg).
- Every sheet starts at break 0, so no weight falls below the first break.
- The sheets carry no footnotes beyond the four rules in `tariffs.json` (read: Yellowtail txt, Cobalt pdf).

## 2. The trucker in the all-in total (questions 1 and 3)

The brief says three things and does not connect them:

- "Quote one option, the one the customer asked for: cheapest or fastest."
- "Among carrier bids, the right one is the most balanced: price and speed weigh 50/50."
- "Every quote states one all-in total."

Live trucker bids for zone 60 to FRA (mails 164 to 168, Sat 14:10 UTC):

| Trucker | EUR | Pickup |
| --- | --- | --- |
| Bodenseefracht | 88.60 | 26 h |
| Westfalenroute | 96.80 | 23 h |
| Isarwelle Spedition | 129.80 | 16 h |
| Domblick Kurierdienst | 151.60 | 15 h |
| Taunusfracht | 177.40 | 3 h |

Cheaper is slower in every pair, so every rule picks a different truck:

| Rule | Picks | EUR |
| --- | --- | --- |
| cheapest | Bodenseefracht | 88.60 |
| 50/50, each scaled 0..1 between best and worst (`minmax`) | Westfalenroute (score 0.48) | 96.80 |
| 50/50, each relative to the best (`ratio`, what `pick()` does today) | Taunusfracht | 177.40 |
| fastest | Taunusfracht | 177.40 |

What the code does today (`pricing.quote`): cheapest trucker, and the **fastest trucker when the customer asked
for fastest**. That is one reasonable reading. If the scorer instead uses the cheapest or the balanced trucker,
a "fastest" door-to-port quote is 80.60 to 88.80 EUR too high: more than 5 % on every shipment under 1612 to
1776 EUR.

Hint that the 50/50 rule is about truckers (a reading, not proof): the brief says "bids from 2 to 5 carriers".
Counted in `carrier-list.csv`: truckers per zone are exactly 2 to 5 (4 zones with 2, 7 with 3, 11 with 4,
10 with 5). Email-only airlines per destination are 1 to 7.

**Settled by rounds 1 and 2 (Sat 16:00 and 16:07, `docs/research/round-log.md`): the trucker in 5U's best price
is the 50/50 pick with the `ratio` formula, whatever the customer asked for.** `PICKUP_RULE=balanced` is the
default on this branch. My estimate before the rounds (`cheapest`) was wrong, and so is main's "fastest trucker for
fastest".

How we find the real rule: the first door-to-port round. `research.rounds` prints, per request, the trucker
each rule would take. Compare with the verdict and the accuracy points on `/v1/board/me`.

### Patch (commit d077f79, defaults unchanged)

Three settings in `config.py`, read by `pricing.quote` and `pricing.pick`. Nothing in `forwarder.py` changes.

| `.env` | Values | Default (= today) |
| --- | --- | --- |
| `PICKUP_RULE` | `asked` (cheapest, fastest when asked), `cheapest`, `balanced` | `asked` |
| `BALANCE_RULE` | `ratio`, `minmax` | `ratio` |
| `UNSPECIFIED_RULE` | `balanced`, `cheapest`, `fastest` | `balanced` |

Changing a rule in production is one line in `.env` and `pkill -f "bin/uvicorn app.main"`.

Tests (`tests/test_pricing.py`): `test_balance_rules_disagree_on_live_trucker_bids`,
`test_pickup_rule_decides_the_all_in_total`, `test_minmax_with_two_offers_takes_the_cheaper`,
`test_request_without_preference_follows_the_switch`.

## 3. The 50/50 formula (question 2)

`pick()` scores `total / lowest + days / fewest`. Days differ by a factor of 2 to 7 between offers, prices
by 1.1 to 1.5, so speed decides. On the test case 700 EUR / 5 d, 720 / 4 d, 900 / 2 d it takes the 900 EUR
offer. `minmax` takes 720 / 4 d. Which one 5U uses cannot be told from the brief or the synthetic key (the key
has no balanced case). It only matters when (a) the parser returns `unspecified`, or (b) the trucker rule
is `balanced`.

For (a): the brief says every customer asks for cheapest or fastest. A request read as `unspecified` is then
most likely a missed word, and today it gets the near-fastest, most expensive option. `UNSPECIFIED_RULE=cheapest`
is the safer miss (guess: a quote under the best price is more likely accepted than one 20 % over).

## 4. Next break for airlines without a sheet

`start_rfq` asks a sheet airline at the sheet's cheapest billed weight (correct), the portal at two weights
(correct), but an airline with no sheet at the chargeable weight only. Only Zephyr, Himalaya Bridge, Lagoon
Isles and Pampero fly to ASU, KTM, PPT, TNR, ULN.

Size, measured on the 158 sheet lanes for 50 to 1500 kg in 5 kg steps: the next break is cheaper for 14.0 %
of weights, by more than 5 % for 8.4 %, worst case 30.8 %. If these airlines price like the others (not
verified: the mailbox has one Zephyr price, 120 kg FRA-KTM 657.60 EUR), a request to one of the 5
destinations just under a break is quoted too high.

### Patch (commit 7daaaf6)

- `pricing.breaks_to_try(cw)`: the breaks above the chargeable weight that can still be cheaper (under 1.35x;
  the largest drop on any sheet is 1.32x). 280 kg gives 300, 230 kg gives 250 and 300, 120 kg gives none.
- `start_rfq`: an email airline with no sheet at all is asked at the chargeable weight and at those breaks.
  Sheet airlines are still asked once, at their sheet's cheapest billed weight. `best_by_carrier` already keeps
  the cheaper of two live prices.
- `ready()`: a request waits until every request mail is answered, not every sender (else the quote could go
  out between the two answers of one airline).

Cost: 1 or 2 more mails and bid reads per sheetless airline, only on the 5 destinations, only near a break.
Tests: `test_sheetless_airline_is_also_asked_at_the_next_break`, `test_a_sheet_airline_is_asked_once`,
`test_breaks_to_try_for_a_carrier_without_known_breaks`.

## 5. Currency

`forwarder.eur()` converts only USD, and only with the last `fx_eur_per_usd` a portal call returned. The API
says the field is "EUR per 1 unit of `currency`", so a GBP price would carry its rate in the same field and
overwrite the USD rate. A USD bid by mail before any USD portal rate is dropped (logged as an error), and the
bid form has no field for a rate stated in the mail. Today nothing is in another currency. 

### Patch (commit 86205fb)

- `forwarder.eur()`: the rate is kept per currency (`self.fx["USD"]`, `self.fx["GBP"]`). A rate stated with a
  price applies to that price's currency. A price in a currency with no rate seen is still dropped, never guessed.
- Bid form and `prompts/bid.md`: new field `fx_eur_per_unit`, filled only when a non-EUR mail states a rate.
  This changes the bid prompt for every bid read. Leave this commit out if you do not want to touch the prompt
  before the first currency change shows up.

Test: `test_prices_in_other_currencies_convert_with_their_own_rate`.

We always quote in EUR. If a customer asks for a total in USD we do not convert. No such mail seen yet.

## How to re-run

```
cd backend && uv run pytest -q                                   # 21 passed
cd backend && uv run python -m research.check_key <synthetic>     # 0 mismatches
cd backend && FIVEU_BASE_URL=... FIVEU_API_KEY=... uv run python -m research.rounds   # read-only round log
```
