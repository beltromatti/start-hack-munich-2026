# START Milan Forwarding: the vision

The guiding document of our forwarder for the 5U AI challenge: what it is, how it works, why, and how we decide.
Read it first: Sam, Jan, every AI assistant, and Claude after a context compaction. It continues the vision of
SIEVER Mail, the harness Mattia built for an agent that runs a person's mail in production, applied to a
freight desk.

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
  5 % of the best price. One quote per request is judged, normally the first: when the customer changes the goods
  after it (rounds 86-87), the quote for the new goods is the one, timed from the original request.
- +10 for a correct tracking answer (only a booked shipment gets the question), +10 humanity from the jury (one
  pick per round). The `booking` points field is always 0 by design. 5U can correct a round by hand (`adjustment`).
- From round 84, a round only 1, 2 or 3 teams get right multiplies their accuracy, time and cost points (board
  `rules.few_winners`: factors 5, 3, 2; a `factor` per round). The rounds most teams fail are the new kinds 5U
  invents ("think beyond the given use cases", Discord 00:04), so being right where others are not is now worth
  several ordinary rounds: the same aim as before (read everything, always price, decline only what we truly
  do not offer), with more at stake. The rules travel on the board itself; `review.py` prints them when they change.
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
| how to work through a changing page and its checks | the browser opens 5U's sites only; the team key is filled from the environment and redacted |

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

### 2.1 The desk: the same register, for the people who run it

- **The product is the desk** (`frontend/`): what Giulia flagged, shipments, customers, network, efficiency, and every
  session live, with the composer to step in. It reads the API the sessions view reads and keeps nothing of its own on
  the server. The challenge leaderboard is on `/leaderboard/challenge`, for the team only: a forwarder's people care
  about their shipments, not about our rank.
- **Sign-in is real:** accounts in the register (`accounts.py`: a salted hash, a signed cookie, a brake on guessing);
  the first account closes the desk. This machine itself reads freely (the monitor and scripts on localhost); what
  comes through the Cloudflare tunnel carries Cloudflare's headers and must sign in. What a person tells Giulia is
  recorded under their account. Sam's draft switches for "what Giulia may do" and per-person rights were removed: the
  agent never read them, and a control that controls nothing misleads the person who sets it. The desk shows what
  Giulia does as what her tools guarantee.
- **The desk's assistant is the forwarder's pattern, small** (`desk.py`): the model decides what to read with
  read-only tools over the register (shipments with their count and quote total summed by code, one shipment with
  its mails, customers, rate sheets priced by `pricing.py`) and when it knows enough; the system checks that every
  shipment and customer it names exists, and its one action, a message to a shipment's session, happens on a
  person's click. It replaced one call over the page's data with a token cap: the page could only send what it had
  thought of, and a total the model adds up is a price no tool computed. Our own OpenAI key, never the gateway.
- **Charts and money follow the same split.** A person asks to see something; the assistant chooses the measure and
  the grouping (`chart`), code computes every figure (`charts.py`), and a chart can be kept on Efficiency, where it is
  asked again on fresh data. It replaced a keyword regex that drew one fixed matrix. The money is `economics.py`:
  per booking, what the customer pays, what the carriers charge, what is passed on, and the margin left, which is
  zero today because Giulia quotes carrier prices as they are; the room to the next option is the margin we could take.
  After the challenge (Sun 22 Nov, noon) the desk shows a demo margin of 6.5 % set in the register
  (`margin_demo_percent`): the one figure on the desk that is not from the record, below the 7.4 % room.
- **The public address is a Cloudflare Tunnel** (`deploy/tunnel.sh`): the Mac dials out, no port opens, and
  production stays where 5U's API is reachable (decision 17).

## 3. The register: state, not callbacks

SQLite (`store.py`): mails, records (deal, booking, session, tariff, board), events, kv. Work comes from state: poll
the mailbox from `since_id`, store every mail, then ask "which mails are not handled yet?". A crash or a restart
never loses a request and never answers twice; a session interrupted mid-turn is closed cleanly and resumed. Only
the world (a mail, an airline's news) and a person start work, never the agent's own writes.

## 4. The tools: few, distinct, powerful

| Tool | What the agent does with it | What it guarantees |
| --- | --- | --- |
| `get_offers` | ask for priced options for a shipment as the customer wrote it | carriers asked, prices by code, dates, the option per preference, why there are none |
| `send_mail` | write a quote, a question, a reply, a confirmation | recipient and thread; first quote recorded with its option; the offer as a PDF made from the option (`offer_pdf`); `done` ends the turn |
| `book`, `cancel_booking` | book the option the customer accepted; cancel a booking they withdraw | by rate id on the portal, a fresh rate if expired, by mail if the API is down; the total follows the airline's booking price (`price_changed`); each booking of a deal its own reference; cancelled with 5U's DELETE, the CRM says so |
| `crm`, `deal` | find shipments and deals | a customer's thread sees only that customer's deals; tracking sees all |
| `mail_carrier`, `carrier_status` | ask a carrier something | only carriers on the list, at most two mails to one carrier per deal in ten minutes; the answer comes back to this deal |
| `browser` | open, read, look at screenshots, act in batches and save a rate on the page the team sees live | 5U's sites only (https); `{team_key}` resolves inside the backend; prices are read by code, duplicate references are not added twice, a changed shipment invalidates the old page |
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
  5U moves airlines between portal and mail, so a portal airline off the portal for this lane (or a 404) is asked
  by mail too; when the rate API turns an airline away (503), it is retried for 20 s, 5U's rate desk is asked and
  used if it replies (it answered the ordinary "Rate request FRA-ORD 320 kg" probe in about 60 s, but four
  requests during the rounds 120–123 outage got no answer), a portal rate we saw tonight on that
  lane and break prices the airline (`portal_memory`), and `get_offers` returns the missing portal airlines at once,
  so the agent can work on the browser page while carriers answer. Notifications let the team watch; their
  presence and the alerts switch do not gate the agent. Asks that may never be answered (mails to portal airlines) are sent but not awaited (round 94
  waited 499 s).
- **Pricing:** chargeable weight = max(kg, cbm x 167); also price the break above when it can be cheaper (299 kg
  cost more than 300 kg); minimum on freight; surcharges per billed kg; exact weights in every request (116.9, not
  117). A bid quoted per kg or itemised gets its total from code. A live bid beats the sheet; a carrier that
  declines loses its sheet price; tariffs keep their validity and the one valid on the ready date prices (a
  December tariff mailed in November does not reprice November; Wayzata's 2025 one never prices). A carrier writing
  unprompted is sending its tariff: Elbflug's monthly update (15 % cheaper, in the mail body) went unread for five
  hours when only an attachment or the word "tariff" made a tariff.
- **The trucker** in a door-to-port total is the 50/50 pick (price / cheapest + time / fastest), the only rule that
  matched 5U's best in both of the first scored rounds. The airline follows the customer's preference.
- **A town is enough for a pickup:** it is its zone. Truckers price by zone but answer only a request with a 5-digit
  postcode, so a named town is asked with a real postcode of that town (`kit.ZONE_POSTCODE`). A city is its airport
  in our network ("New Delhi" is DEL): the tool knows, the agent never asks which airport.
- **An option id names one option for the life of a deal:** a changed or second shipment prices as B1, B2..., and
  each option carries its own shipment, so a booking takes the route and goods of what was quoted (round 89).
- **What the customer adds on their own terms** (cargo insurance, a broker's fee, a handling fee) is a field of the
  shipment, added by code to every total.
- **Dates:** one function (`pricing.schedule`): the goods leave when ready (09:00 of the ready date) plus the pickup
  time and arrive transit days later. The quote, the booking and the tracking answer say the same dates.
- **Numbers read by a model are checked against their source:** an amount the bid reader returns must appear in the
  carrier's mail; if not, it is read again, then left out (a trucker's "94.08 EUR" once came back as 9408).
- **The airline's booking price is what it charges.** For an hour (rounds 48-50) the portal booked the quoted rate
  at 10 % more (5655.55 became 6221.11). The booking total is recomputed by code from the airline's price plus the rest
  of the all-in (pickup, insurance, charges: round 92 told a customer a total without its insurance),
  `book` returns `price_changed` with both totals, and the agent says it in the confirmation (round 50: "letting me
  know about the change before invoicing", the customer wrote back). When nothing changed `book` says so, with the
  customer's all-in total next to the airline's flight-only price (round 118 told a customer the flight price as a
  new total). An airline's own mail about the booking is read
  the same way: code says whether its price is the flight price we booked (so the all-in total stays) or another
  one (round 51: the agent took the flight price for a change of the all-in total).

## 6. How the agent writes (and how we write prompts)

Like a good human forwarder who likes the job: warm, quick, competent. One mail, one option, one total, exactly as
the tool gives it; several shipments in one request are several quotes, one total line each; the customer's own
figures (a budget, a competitor's price) stay out, said in words (round 102). The prompts (`backend/app/prompts/`) say what a good outcome is and why, and leave the how to the
model: no procedures, no word lists, no "never" without a reason. A model reads a reason and applies it to cases the
sentence did not mention; it reads a rule and applies it literally, also where it is wrong.

- **Language is the language of their text,** not of their name, company or country; a two-language sign-off
  ("Viele Gruesse / Many greetings") is a courtesy. Round 29 and three tracking answers went out in German to
  English mails before this was said (also in the tracking task); after it, rounds 49 and 69, always German
  companies writing English. So the agent also gets a fact, counted by code from the mail's own words when clear
  ("Their own words are in English."): a fact the agent weighs, not a check on what it writes.
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
- **What stays are the limits the model cannot keep itself,** each with its reason: the 2-minute clock (the agent
  sees `seconds_since_request`; browser work must leave time to quote before the 6-minute close; while a page is
  active, get_offers returns a snapshot instead of blocking on mail and expiring its check (mail handlers keep
  collecting independently). When a rate service temporarily goes down, the agent can explicitly ask get_offers
  to pause this deal for its retry interval and return updated prices. The pause leaves time for the quote; known inputs and submit can run in one batch so a short-lived page check does not
  expire between tool calls; the portal API 20 s); not spamming a
  counterpart (two mails to one carrier per deal in ten minutes: round 88 sent six and lost 20 points); a hung
  gateway costs 45 s a try before OpenAI direct.
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
  airlines by mail, the rate desk, remembered rates, the agent on 5U's portal page); one mail that cannot go out
  never stops the others; booking API 503 (booking by mail with the airline's reference); `/ports` 503 at a restart
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
- **A mail is its body and its attachments, whatever their form** (round 63: truckers priced in a PDF, a Word
  letter and a voice message; round 65: the request itself was a voice message; 5U said stranger formats are
  coming). One reader (`docs.text`) serves customers, carriers and the rate desk: pdf (scanned pages read as
  pictures, with Pillow), xlsx, xls, docx, text in any common encoding, zip and eml opened, pictures read through the gateway
  (`llm.look`), voice messages transcribed with a call of our own (the gateway takes no audio; 5U said to do so),
  prices said aloud accepted by the amount check. Units are read however written and never guessed: an unknown
  one goes back to the agent by name. A trucker's time is the time until it collects, however it is put.
  Our own documents go out the same way: an offer the customer wants as a PDF is made by code from the option
  (`send_mail` with `offer_pdf`), so it says what the quote says, one total (round 76: a customer asked for the
  offer as a PDF for its purchasing and walked away from a quote without one; 5U's API takes attachments).
- **A mail to the customer without a price is a decline** (round 63, `declined_in_scope`): when a carrier has
  not priced yet, wait for it or ask it; the customer cannot help.
- **Prices can move between the quote and the booking** (rounds 48-50): the customer hears it from us, in the
  confirmation, not from the invoice.
- **A request can change after the quote** (rounds 86, 87: "the final packing list came in" a few seconds after our
  quote): the agent prices the new goods and quotes again; the booking follows the options as they are now.
- **A booking can be undone, an offer accepted from another thread.** After a booking, an airline's answer to a
  mail the agent wrote (a cancellation) is booking news that wakes the session, like the airline's own news; an
  offer accepted in a new mail is booked on the deal that holds it (`book` with its `deal_id`, the customer's own
  deals only). A shipment that starts outside Germany (an import) is named out of our service by `get_offers`,
  so the agent says so instead of asking for a German airport (Sam's probe, Sun 00:30).
- **Where a price lives can move; the agent follows it.** 5U moves airlines between the portal and mail and lets
  the rate API answer 503 (rounds 93-100). The engine asks where an airline may sell (portal, mail, rate desk,
  remembered rates); the agent gets missing portal airlines immediately and can use `browser` while mail arrives.
  We initially treated the page's checks as work for a person. The organiser clarified at 04:03–04:08 on Sunday
  (Discord screenshot supplied by Mattia): no human in the loop includes the portal, checks and copied prices;
  an agent's own harness is allowed. That evidence overturns our earlier reading of the brief.
  The same forwarder now observes labels, text and, when needed, a screenshot; chooses the actions; fills
  `{team_key}` through the backend; handles banners and checks; and submits known fields in one ordered batch.
  A failed or expired check comes back as the current page so the agent can refresh and adapt. No separate
  keyword solver or second decision-making agent sits in front of it. `save_rate` reads the displayed price,
  days and reference by code. When a result lists several rates, the agent can select a reference from a distinct
  labelled record. A foreign currency or ambiguous association leaves the other priced options available. The tool
  checks the currency, displayed airline, lane, weight, expiry and that
  the shipment has not changed; inserts the rate idempotently; and returns the freshly computed all-in options
  so the agent can quote without another wait just to refresh prices.
  Round 120 exposed headless automation defaults and a discarded profile; the installed desktop Chrome now
  runs directly with a dedicated persistent profile, connected without device overrides. A notification opens
  this live page beside its browser tool steps in the deal's conversation, with controls in a compact menu.
  Opening or reconnecting the view does not navigate the agent's page. The team can observe and interact, but solving
  the scored work never depends on a person's presence, key entry, answer or pasted result. `ask_person` is no
  longer offered to the agent, and an old session calling it receives the autonomous route immediately.
- **Suspicion is the model's, protection is the tool's.** Impostors write from lookalike addresses seconds after a
  real request ("my mailbox is down, send it here", rounds 105-107). What protects is a guarantee: a conversation
  sees only its own sender's deals, so nothing of a customer reaches anyone else, whatever the agent answers. A code
  check that named an address "an imitation" made the agent decline the real customer in round 107 (the impostor
  had become "on file"); it is gone. The prompt says, with its reason, be wary of moving a customer's offers
  elsewhere, and quote a new address: declining a real customer loses the request.
- **What the customer adds to the price is priced by code too.** Cargo insurance on their terms (round 91: value,
  share insured, premium rate) is a field of the shipment, and get_offers adds the premium to every total; several
  shipments in one mail are several quotes, each option carrying its own shipment, each booking its own reference
  (rounds 89-90).
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
  20 because nobody checked the customers who only had a town; a lookalike-address check lost round 107 because
  nobody walked it through a customer writing again after an impostor). Replay key mails in the sim when wording matters.
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
18. Prices live where 5U puts them: portal, mail, rate desk, remembered rates, 5U's portal page operated by the agent; asks
    that may go unanswered never hold the quote.
19. The challenge runs without human assistance, including the portal (organiser clarification, Sun 04:03).
    The browser goes to 5U's sites only, resolves the key internally and shows the agent's work live to observers.
20. Suspicion is the model's, protection is the tool's: no code judges a sender; a thread sees only its own deals.
    Someone new inside a customer's thread (their broker) is helped like the customer; a mail may go to several
    people of the thread, one mail each, never outside it.
21. The limits that stay are those the model cannot keep: the 2-minute clock and not spamming a counterpart.
22. Where a source turns us away, the answer is where 5U still keeps it: the agent starts the browser at once
    while carriers answer, bounded by the 6-minute close rather than the 2-minute best (rounds 93-100).
    A yes with an open question is answered before booking (round 108).
23. A cause is read in 5U's own words and our data before it is built on. "They waited, the API came back" (a
    teammate's reading of rounds 93-100) ran for twenty minutes as a 4-minute API wait; the brief named the page,
    and our own retries had failed up to 89 s.
24. The desk is the product: real accounts, the leaderboard only for the team, its assistant an agent over the
    register with read-only tools. Nothing on the desk changes what Giulia does except a person's word in a session.

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
- **5U's portal page changes:** the browser agent can inspect text or screenshots and recover after expired checks;
  a new challenge type still needs verification in a real round. The rate desk answered within a minute in the
  02:54 probe and did not answer four requests during the rounds 120–123 outage.
- Notes carried to a customer's next thread are every note of their earlier deals, routine ones included: the
  agent judges them, but they are noise next to the one wish that matters.
- **Untrusted input has no size bound:** a mail body (5U allows 200,000 characters) and its attachments (5 of 10
  MB) enter the agent's first message whole. Measured at 21:50: the longest customer mail 905 characters, the
  largest first message (round 57, with its packing list) 2,285. A real 30-page document (about 15,000 tokens) would
  cost about 0.002 USD at gpt-6-luna's 0.10 USD per million, and the agent sees all of it at once, which the
  document-wins rule needs. Only a pathological size breaks us: past the 1.05 million-token context the request is
  refused and the round is lost. SIEVER Mail's answer is pages the agent reads on demand;
  not built, because for real documents it would add calls, not save them. Decide again if a document ever runs
  to more than a few dozen pages. (Since 22:43 pictures and scanned pages are read too: each is one gateway call,
  about 0.0004 USD.)
