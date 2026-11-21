# START Milan Forwarding: the vision

The guiding document of our forwarder for the 5U AI challenge: what it is, how it works, why, and how we decide.
Read it first: Sam, Jan, every AI assistant, and Claude after a context compaction. It continues the vision of
SIEVER Mail, the harness Mattia built for an agent that runs a person's mail in production
(`reference/siever-mail/vision.it.md`, English digest in its `README.md`), applied to a freight desk.

It is not a rulebook. It is how we think, with what really happened as the examples, so that a person or an
assistant can reason the same way about a case nobody has seen yet. It must stay true: when the code and this file
disagree, one of them is wrong, so find out which and fix it. When the reasoning here is wrong, say so and change
it here, in its place, with the reason. Small, considered edits; no new layers of text.

---

## 0. In one sentence

A digital air export forwarder that runs one mailbox on its own, day and night: one agent with one identity reads
every mail, prices, quotes, books and answers tracking questions, on top of a system that guarantees every number,
every recipient and every state change.

**The model decides what makes sense. The system guarantees it can do so coherently.** Semantic freedom on
deterministic ground. Everything below follows from this split.

### 0.1 The challenge, as it is scored

- A request (RFQ) every 6 minutes, from 5U's customer agents, in one shared mailbox; it expires 6 minutes later.
- Per accepted quote, up to 100 points: accuracy 45 (full at the best price, zero at 10 % above it), LLM cost 40
  (`40 x (1 - spend / 0.10 USD)`, spend = gateway spend per accepted quote over the board's cost window: the hour
  at first, 18 minutes in the board's rules at 21:00), time 15 (full within 2 minutes). A quote is accepted within
  5 % of the best price. Only the first quote of a thread counts.
- +10 for a correct tracking answer (only a booked shipment gets the question), +10 humanity from the jury (one
  pick per round). The `booking` points field is always 0 by design. 5U can correct a round by hand (`adjustment`).
- The setup changes about once an hour, unannounced, and gets harder: traps in mails and documents, outages, new
  limits, prices that move. We learn of a change from a failed quote unless we notice it first
  (`docs/likely-changes.md` lists the kinds, the earliest signal and our response).
- The winner is chosen on the leaderboard and on the pitch, UX and design, codebase, and how human the mails read.

## 1. The split: who decides, who guarantees

| The model (one agent) decides | The system (tools, engine, register) guarantees |
| --- | --- |
| what the customer wants, from any wording, language, attachment | every price and total (`pricing.py`, Decimal), every date (`pricing.schedule`) |
| which tool to use next, and when it is done | who may be mailed: people in the thread, carriers on the list, the 5U desks |
| how to read an odd carrier answer, a conflict, a trap | the thread a reply goes into, the first quote recorded with its option |
| what to ask, and whether to ask at all | that an amount read from a carrier mail is in that mail |
| how to write to a person | that a restart loses nothing and answers nothing twice |

We never make the model do the system's job (it would invent a price), and never make the code do the model's job
(it would break on the first mail nobody wrote a rule for).

**No hard checks on what the model writes.** A check on text is a rule about language, and language is exactly
where rules break: it blocks a good mail it did not foresee and gives the model nothing to learn from. We teach with
the prompt (the criterion and its reason) and measure with diagnostics. A research stress test found a quote with
two totals: the gate that blocked sending became a log line, and the fix that stayed is one sentence in the prompt
("one mail, one option, one total"), with its reason.

## 2. One agent, one session per deal

The challenge looks like a pipeline (read, price, reply), but a deal is a life: quote, then book, then track, with
people writing whatever they like between. So there is one forwarder (persona Giulia, START Milan Forwarding) and
every thread has its own session, kept in the register for as long as the deal lives. Every new mail in the thread
resumes it with everything before it.

- The first tracking question said "Status of our shipment 51447 to ORD, 676 kg", no booking reference. A matcher
  on references would have asked for one and lost the bonus; the agent searched the CRM with the words it had.
- "Thanks for confirming" after a booking: the agent decided nothing needed sending (`no_reply`). Nobody wrote a
  rule for thank-you mails.
- **The router is code**, by sender and thread, never by what a mail claims: the tracking desk goes to the tracking
  task; the rate desk, carriers, tariffs and booking confirmations to system handlers; anyone else is a customer.
  Only a carrier on our list can confirm, change or reprice a booking (a "Booking ... confirmed" subject from any
  other address is a mail the agent reads, not a confirmation).
- **Two tasks of one identity:** `customer` (quote, ask, book, reply) and `tracking`. 5U's "router plus three
  agents" is this seen from outside.
- **Carrier mail wakes nobody.** Bids are read into the deal's offers by a small model; the agent sees them when it
  asks (`get_offers`). Airline news about a booking (a delay, a change, a cancellation) goes on the booking and
  wakes the deal's session; a confirmation of exactly what we booked stays quiet.
- **A customer is known across threads:** a new thread starts with our notes from that customer's earlier deals.
  Round 42: "Please do not offer Zephyr Steppe Cargo (ZS) for this shipment or for any of our future inquiries."
  The agent judges what still applies.
- **The human's word wins:** a person can write to any session ("offer them the faster option") or answer the
  customer from the UI; the agent follows and does not undo it. That is the sessions UI 5U asked for, and how the
  team corrects the system without touching code.

## 3. The register: state, not callbacks

SQLite (`store.py`): mails, records (deal, booking, session, tariff, board), events, kv. Work comes from state: poll
the mailbox from `since_id`, store every mail, then ask "which mails are not handled yet?". A crash or a restart
never loses a request and never answers twice; a session interrupted mid-turn is closed cleanly and resumed. Only
the world (a mail, an airline's news) and a person start work, never the agent's own writes.

## 4. The tools: few, distinct, powerful

| Tool | What the agent does with it | What it guarantees |
| --- | --- | --- |
| `get_offers` | ask for priced options for a shipment as the customer wrote it | carriers asked, prices by code, dates, the option per preference, why there are none |
| `send_mail` | write a quote, a question, a reply, a confirmation | recipient and thread; first quote recorded with its option; `done` ends the turn |
| `book` | book the option the customer accepted | by rate id on the portal, a fresh rate if expired, by mail if the API is down; the total follows the airline's booking price (`price_changed`) |
| `crm`, `deal` | find shipments and deals | a customer's thread sees only that customer's deals; tracking sees all |
| `mail_carrier`, `carrier_status` | ask a carrier something | only carriers on the list; the answer comes back to this deal |
| `note` | leave a flag or a fact for the team (and for later threads) | it stays on the deal |
| `no_reply` | decide nothing needs sending, with the reason | the required outcome is met; `done` ends the turn |

A new capability is a tool the agent can choose, or a field a tool returns, never a step bolted in front of the
agent, a classifier that decides for it, or if-then rules on mail text. Tracking: 5U said the status comes from the
airline by mail, so the agent got `carrier_status`, not a tracking pipeline; when the airlines turned out to answer
with their quote form, the agent answered from our records. A keyword table ("günstigste" means cheapest) was
removed: the model understands every phrasing nobody listed, the table could only be wrong where the model is
right. Permissions are per task: the same catalogue, each tool knows what the task may see.

## 5. The engine: prices, carriers, dates (all code)

- **Who is asked:** the rate portal (airlines on the lane), every email airline that serves the destination, the
  truckers of the pickup zone. An airline that told us its lanes in the last two hours ("We fly ...") is not asked
  for a lane outside them; the agent sees who was skipped (`not_asked`) and can still ask. Unknown is always asked.
- **Pricing:** chargeable weight = max(kg, cbm x 167); also price the break above when it can be cheaper (299 kg
  cost more than 300 kg); minimum on freight; surcharges per billed kg; exact weights in every request (116.9, not
  117). A bid quoted per kg or itemised gets its total from code. A live bid beats the sheet; a carrier that
  declines loses its sheet price; tariffs keep their validity and the one valid on the ready date prices (a
  December tariff mailed in November does not reprice November).
- **The trucker** in a door-to-port total is the 50/50 pick (price / cheapest + time / fastest), the only rule that
  matched 5U's best in both of the first scored rounds. The airline follows the customer's preference.
- **A town is enough for a pickup:** it is its zone. Truckers price by zone but answer only a request with a 5-digit
  postcode, so a named town is asked with a real postcode of that town (`kit.ZONE_POSTCODE`). A city is its airport
  in our network ("New Delhi" is DEL): the tool knows, the agent never asks which airport.
- **Dates:** one function (`pricing.schedule`): the goods leave when ready (09:00 of the ready date) plus the pickup
  time and arrive transit days later. The quote, the booking and the tracking answer say the same dates.
- **Numbers read by a model are checked against their source:** an amount the bid reader returns must appear in the
  carrier's mail; if not, it is read again, then left out (a trucker's "94.08 EUR" once came back as 9408).
- **The airline's booking price is what it charges.** For an hour (rounds 48-50) the portal booked the quoted rate
  at 10 % more (5655.55 became 6221.11). The booking total is recomputed by code from the airline's price plus the pickup,
  `book` returns `price_changed` with both totals, and the agent says it in the confirmation (round 50: "letting me
  know about the change before invoicing", the customer wrote back). An airline's own mail about the booking is read
  the same way: code says whether its price is the flight price we booked (so the all-in total stays) or another
  one (round 51: the agent took the flight price for a change of the all-in total).

## 6. How the agent writes (and how we write prompts)

Like a good human forwarder who likes the job: warm, quick, competent. One mail, one option, one total, exactly as
the tool gives it. The prompts (`backend/app/prompts/`) say what a good outcome is and why, and leave the how to the
model: no procedures, no word lists, no "never" without a reason. A model reads a reason and applies it to cases the
sentence did not mention; it reads a rule and applies it literally, also where it is wrong.

- **Language is the language of their text,** not of their name, company or country; a two-language sign-off
  ("Viele Gruesse / Many greetings") is a courtesy. Round 29 and three tracking answers went out in German to
  English mails before this was said (also in the tracking task); since then, round 49 once.
- **Register and warmth mirror the sender.** A friendly opener gets a few words of our own back after the greeting,
  then the business; nothing is added when they wrote none.
- **Answer what they asked:** a date when they ask when it arrives (from the option, as an estimate); for something
  we do not hold yet (a cutoff time), what we know for the same need and what is still to be confirmed.
- **Explain how the system works, instead of forbidding.** The agent wrote each mail twice, as its own message and
  inside `send_mail`; the fix was one sentence: "a mail exists only inside send_mail".
- **Examples get copied:** a sample phrase in a prompt came back word for word, and a reason given in the prompt
  can come back as the mail's own words. Give the criterion and the reason, describe the kind of sentence, never the
  sentence.
- **Two lines that pull apart confuse the model:** when a line is added, check it against the others ("answer
  first" silently beat "answer their friendly line" until both were reconciled).

## 7. Effort, limits, cost

- **No caps on steps, tokens or output.** The model decides how much a deal needs. A cheap model (`gpt-6-luna`, low
  effort) for the agent, `gpt-5-nano` for reading bids. One stop only, for spinning: 10 turns without progress.
- **The one system constraint is the required outcome:** the mail being handled gets an answer or a reasoned
  `no_reply`; if the model stops before, the system tells it once.
- **Cost is 40 % of the score, so we measure it.** A whole deal (quote, booking, tracking) costs a few tenths of a
  cent; a lost round still spends and divides by fewer quotes. What we cut, we cut where nothing is lost: the model
  marks a reply `done` (no closing call), airlines that told us their lanes are not asked again, a matching
  confirmation does not wake the agent, tracking answers from our records instead of asking the airline. Measuring
  is also how we found that a separate watcher's diagnoses cost 25 times our deals.

## 8. Errors: two families

- **The stack** (5U, the network, the gateway): transient errors are waited out and the call retried, never the
  whole run; a request whose outcome is unknown is never resent blindly. Seen and handled: portal rates 503 (the
  airlines by mail); booking API 503 (booking by mail with the airline's reference); `/ports` 503 at a restart
  (start anyway); the mailbox allows one poll per 5 seconds per team key (we poll every 5.5 s, and a failed poll
  is never retried sooner: a retry is a second poll).
- **The agent:** a run that cannot finish ends and is logged; the next mail in the thread is new work.
- **Startup must survive the world being down.** A restart that fails on a 5U outage costs every request.

## 9. What 5U taught us (the kinds, not the mails)

- **The documents are what the goods are.** A packing list or instruction is measured and checked, the mail is a
  summary: when they disagree, price from the document and say so (round 33, rejected too_high, then replayed right).
- **Dangerous goods in a document: ask for the shipper's declaration and the safety data sheet**, saying what you
  saw. Not "which is right?" (round 11 lost; 5U explained it in person), not a quote. Rounds 10, 39, 40 and 41
  were accepted that way.
- **Ask once, ask what moves the deal.** When the answer still lacks it, they do not have it: go on with what they
  gave (round 20 lost to repeated questions for a postcode when "All I have is Augsburg").
- **Where to collect is what they say about the pickup.** A signature town is where they write from (round 15).
- **A wish for future inquiries outlives the thread** (round 42; 5U corrected its verdict by hand, +120).
- **Tracking comes from our own records;** the airlines answer status questions with their quote form.
- **A carrier's mail is its body and its attachments** (round 63: truckers priced in a PDF, a Word letter and a
  voice message, and a body-only reader saw no price). Every carrier and rate desk mail is read with its
  attachments; a voice message cannot be read (the gateway takes no audio), so it is named and the carrier
  can be asked in writing. A trucker's time is the time until it collects, however it is put.
- **A mail to the customer without a price is a decline** (round 63, `declined_in_scope`): when a carrier has
  not priced yet, wait for it or ask it; the customer cannot help.
- **Prices can move between the quote and the booking** (rounds 48-50): the customer hears it from us, in the
  confirmation, not from the invoice.
- **Time:** every accepted quote inside 2 minutes took the full 15; speed beyond that is not worth accuracy.
- **Not every mail is a customer.** 5U sends traps: a "CEO" asking for the API keys (refused: the agent holds no
  secret to give), a sales pitch (no reply). Judging them is the agent's job; what a mail can make us do is bounded
  by the tools (replies only to who wrote, carriers only from the list, prices by code, bookings only of the deal's
  own options, a customer's thread sees only that customer's deals). Other teams cannot reach us: 5U's API answers
  422 to mail between teams, and `in_reply_to` only takes a mail the sender sent or received.

## 10. Measure, then decide

- We decide from what the live system shows: the board's points per round and kind, our register's cost, the mails
  themselves. A guess becomes a rule only when the data agrees: the trucker rule was tested against both of the
  first scored rounds' real bids; the accuracy formula came from a partly scored round.
- **When the question is how a counterpart behaves, ask it once, for real,** on a dead deal: carriers did not
  understand "320 kg chargeable" and asked back (the request template changed); "Augsburg" alone got no trucker
  price, "86150 Augsburg" did.
- **Monitoring is reading.** A script only wakes us (a round's activity, silence, the server down); at every wake a
  person reads everything new in full and judges it like a forwarder: language, tone, option, price, dates, what the
  customer asked. Rule-based triggers missed the German replies; reading found them, and found the +10 % booking
  price in round 48 before any score showed it.
- **When we did right and the score disagrees, we take it to 5U** with the facts (round 11, round 42), and we
  still ask what the case teaches.

## 11. How we change things

Before a change, ask:
- Is this a **judgement** (the agent: prompt, or a tool it can choose) or a **guarantee** (a tool, the register)?
- Am I fixing **this mail**, or **the kind of change** it belongs to? 5U changes something every hour; patches for
  single mails are a race we lose. A carrier quoting per kg became "any carrier's parts make a total", not "Solace's
  new format"; a booking at +10 % became "the total follows whatever the airline books at".
- Is there **already one place** for it? Then change it there. Prices only in `pricing.py`, model calls only in
  `llm.py`, state only in `store.py`, one UI, this vision here. Two implementations drift apart, and one of them
  is wrong without anyone noticing (a second pricing function in the synthetic tests, a second dashboard reading
  5U with the team key: both removed).
- Does **the agent or the system use it**? A module that watches the agent with its own rules is a second brain:
  it disagrees, it costs, and nobody owns its mistakes. Deleting is a feature.
- How will we **know it worked**? Which round, mail or number will show it?

Then:
- **Walk the change through the real threads it touches before it goes live** (the 17:29 postcode rule lost round
  20 because nobody checked the customers who only had a town). Replay key mails in the sim when wording matters.
- `make test` stays green; anything touching money or sending gets a test. Commit messages say what happened (round,
  mail, number), what kind of change it is, and how it was checked.
- Deploy only in a quiet window (after a round's quote and booking settle). One machine runs production.

### How we work together

- `main` is what runs. Work on a short branch, `make test` and `make sim` (real model, fake 5U, nothing scored),
  then ask Mattia to merge. Never `make live`: one machine answers the real mailbox, two would answer twice, and the
  team key's limits (portal 10 per minute, mailbox one poll per 5 seconds) are shared by everyone who uses it.
- A proposal is easiest to take when it says what happened (round, mail, number), what kind of change it is, and the
  smallest change in the right place.

## 12. Decisions in brief

1. One agent, one session per thread; tasks `customer` and `tracking`; the router is code, by sender and thread.
2. Results are tool calls; the required outcome (answered, or a reasoned no_reply) is the only system constraint.
3. Every number and date a customer reads is computed by code; amounts read by a model are checked in their source.
4. No hard checks on the model's text: teach with the prompt and its reason, measure with diagnostics.
5. No caps on steps, tokens, output; one stop for spinning (10 turns); the model may end a turn with `done`.
6. Prompts give criteria and reasons, never procedures or sentences to copy; new lines are reconciled with old ones.
7. The language of a reply is the language of the customer's text; warmth and register mirror the sender.
8. Documents win over the mail on the goods; dangerous goods in a document: ask for the papers, once.
9. Ask once, only what moves the deal; a named town is a pickup place, a signature is not.
10. A customer's notes carry to their new threads; a customer's thread sees only that customer's deals.
11. Door-to-port: the 50/50 trucker; the next weight break when cheaper; exact weights; real postcodes for towns.
12. Tracking answers from our records; airline news on a booking reaches the deal; matching confirmations are quiet.
13. The booking total follows the airline's booking price, and a change is said in the confirmation.
14. Outages: retry the call, fall back to mail (rates, bookings), start without the portal; keep to rate limits,
    and never retry a mailbox poll inside the limit.
15. Cost is measured and cut only where nothing is lost.
16. Monitoring is a person reading every round in full; scripts only wake.
17. One production machine (the Mac: the AMD notebook's egress proxy blocks 5U's API); the team key only in `.env`.

## 13. Open, and known limits

- **The `adjustment` on rounds booked at +10 %** comes with no reason and is revised by hand: round 49 (customer
  never told) -22.5; round 48 (told in a correction after a confirmation without the price) -22.5, then -32.5,
  at 21:55 -10; round 50 (told in the confirmation) none. It looks like 5U expects the booked price in the
  confirmation, which is what `price_changed` does now. To confirm with 5U.
- **Mailbox 429s:** 12 between 20:00 and 21:00 although we poll every 5.5 s. From 21:00 a failed poll is never
  retried early, and 429s still came (21:01, 21:03): another client polls with the team key. Each costs a few
  seconds, not a mail; whoever reads the mailbox besides production should stop or use the UI.
- No replay engine yet over the real threads before a prompt change (planned; meanwhile, walk the change through
  the threads by hand and replay key mails in the sim).
- Cancellations and changes asked by a customer have no tool of their own: the agent can write to the airline
  (`mail_carrier`) and the airline's answer reaches the deal, but the booking status does not change by itself.
- Notes carried to a customer's next thread are every note of their earlier deals, routine ones included: the
  agent judges them, but they are noise next to the one wish that matters.
- **Untrusted input has no size bound:** a mail body (5U allows 200,000 characters) and its attachments (5 of 10
  MB) enter the agent's first message whole. Measured at 21:50: the longest customer mail 905 characters, the
  largest first message (round 57, with its packing list) 2,285. A real 30-page document (about 15,000 tokens) would
  cost about 0.002 USD at gpt-6-luna's 0.10 USD per million, and the agent sees all of it at once, which the
  document-wins rule needs. Only a pathological size breaks us: past the 1.05 million-token context the request is
  refused and the round is lost. SIEVER's answer (§2.3, §13.6 of its vision) is pages the agent reads on demand;
  not built, because for real documents it would add calls, not save them. Decide again if a document ever runs
  to more than a few dozen pages.
