# The founders' story against our code

A snapshot of Sat 21 Nov, 16:31. `main` has moved since: check a point against the current code before you
quote it.

Code state: `main` at 73e8158 (Sat 21 Nov, 16:31), after Mattia's clean-up at 16:28. Their story: the 5U CEO
interview and blog (see `BRIEF.md`), plus Zauber, Nexcade, cargo.one and Pallet. Line numbers are from `main`;
the detailed read was done on 9e76777 and the points that changed since are corrected here.

## Bottom line

Our architecture is the one the 5U CEO describes. One stateful agent per thread, tools that guarantee the numbers,
no workflow in front of it. `docs/how-we-build.md` reads like his interview. We are behind in five places: a failed
mail dies quietly, decisions are logged but not shown as a record, nothing is remembered across deals, nothing can
be held for approval, and our testing got thinner at 16:28. Four of the six pitch lines in `docs/roles.md` no
longer match the code.

## Where we match. Say it, it is real.

| Their claim | Our code |
| --- | --- |
| Stateful: a quiet thread is picked up with full context | One session per thread in SQLite, saved every turn, repaired after a restart (`agent.py`). Saturday: a tracking question without a reference was found through the CRM search |
| "Workflows are jails for agents" | The model reads the request, picks the next tool, the option and the words. Code computes every number and decides who may be mailed (`how-we-build.md` 1 to 3) |
| Self-heal: a source breaks, the Worker finds another route | Portal down or over the limit: mail the airline. Booking API down: book by mail. Carrier silent: the sheet stands in. Live price replaces the sheet. Other currency converted. Per-kg bids and sheet validity since 16:22. Airlines answered status questions with their quote form: the agent answered from our record |
| A person can step in | Tell the agent or answer the customer from the UI, the agent follows (`main.py` 102 to 128) |
| Small models for narrow tasks | Agent on gpt-6-luna at low effort, carrier replies read by gpt-5-nano (`config.py` 28 to 31). About $0.0016 per deal |
| 15 minutes down to 2 | Median 0:39 to the first response over the first five rounds |

## Where we fall short, by value per hour

1. **A failed mail dies quietly. This one costs points.** After the third failed try the mail is marked handled
   (`forwarder.py` 124 to 130), and a run that ends without an answer only writes a log line (`agent.py` 79 to 80).
   A missed request is a lost round. Fix, under an hour: a red flag on the deal and a place in the UI that shows it.
2. **Decision record.** 5U's "Decision Layer": what was decided, on what data, with what confidence. We log a
   `decision` event per quote and every tool call with its result, served by `/api/deals/{id}`. Missing: one record
   per quote with carriers asked and answered, options compared, the rule in force (`PICKUP_RULE`), and a
   confidence computed in code. Fix, one to two hours: write it where the quote is recorded (`tools.py` 199 to 204)
   and show it as a card.
3. **Memory across deals.** There is none. `crm` only searches (`tools.py` 213), a person's instruction stays in its
   session. Round 1 mailed five airlines that do not fly the lane. 5U: corrections go into memory, and "the memory
   defends itself". Fix, two hours: remember "does not serve this lane" per carrier with an expiry, and standing
   instructions, and give both to the agent as context.
4. **Approval.** `send_mail` sends at once (`tools.py` 156). The yellow and red flag is a note and stops nothing.
   5U shows "Waiting Offer Approval", Nexcade "nothing leaves without you", cargo.one a slider from co-pilot to
   autonomous. Fix, two hours: a hold switch (off, flagged, all), off in scored rounds. Jury only, but it is the
   first thing a forwarder asks.
5. **Grader.** 5U replays every change in simulation before production. We have 31 tests on a scripted model and
   `make sim`. The stress test with 44 real-model cases and the answer key left `main` at 16:28. Nothing replays
   recorded rounds. Fix: `make grade` with a pass or fail, then a replay from the register.
6. **The supply side is a pipeline.** Carrier replies and tariffs go through a fixed path with a small model, and
   code picks who is asked and which option is recommended. That is a sound choice. The honest line is "an agent
   with tools", not "no workflow anywhere".
7. **Their KPIs.** Response time, ask rate (out-mails of kind `question`), closed loop and reopens are all in the
   register. There is no endpoint and no tile for them in the main UI.
8. **Shadow mode.** None next to production, only the fake 5U. Too large for tonight. Say "simulation".

## Pitch lines in `docs/roles.md` that no longer hold

- Line 2, "LLM only for outliers, green, yellow, red": the model handles every request, there is no triage.
  What is true: a whole deal costs about $0.0016.
- Line 4, "we learn from the whole field": board snapshots are stored, nothing reads them.
- Line 5, "Jan's prediction engine as the watcher": removed from `main` at 16:28. `docs/likely-changes.md` has the
  honest line: we detect a change within one round, we do not forecast it.
- Line 1, "no LLM in the price": every number is computed in code, but the model copies the amount into the mail and
  picks the option. A wrong copy is logged, not blocked. That is on purpose (`how-we-build.md` 4). Say "every number
  is computed in code".
- "Self-improving harness" and `human.md` do not exist as such. The tone lives in the agent prompt.

Points 2 and 3 above (decision record, memory) would give Jan a new part in the story that the code can carry.

## What the others do better, on paper

- **5U**: Grader, shadow mode, memory that asks before it is changed, specialised small models.
- **Zauber**: SOPs per customer in plain language, and the system proposes SOP changes from what operators correct.
- **Nexcade**: every step with a clock, "held for review", account memory shown and reused on the next request.
- **cargo.one**: one slider for autonomy, and validation that checks margin and anomalies before delivery.
- **Pallet**: options compared, rule applied, one approve button, and a judge that retries until house rules hold.

## Dashboards

Mattia removed `overview/` from `main` at 16:28: one UI, and the team key should not sit on a personal Cloudflare
account. The Cloudflare page still runs on the old version. The new thread view is built on it (branch
`sam/thread-view`, three commits, not pushed, not deployed). The same patterns fit the main UI in `frontend/`,
which already has every mail, tool step and cost from the register.
