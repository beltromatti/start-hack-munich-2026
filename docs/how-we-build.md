# How we build the forwarder

For Sam, Jan, and the AI assistants that work with them. Read this before you change anything.

This is not a rulebook. It is how we think about the system, with what actually happened on Saturday as the
examples, so you (and your assistant) can reason the same way about cases nobody has seen yet. When this file
and a habit pull in different directions, follow the reasoning here, and if you think the reasoning is wrong,
say so: that is how it gets better.

Where it comes from: the harness Mattia built for SIEVER Mail, an agent that runs a person's mail, calendar and
files in production (`reference/siever-mail/`, English summary in its `README.md`).

---

## 1. The one idea: the model decides, the system guarantees

Everything else follows from one split.

- **The model decides what makes sense:** what the customer wants, which tool to use next, whether a carrier's
  odd answer matters, how to write to a person. Language, judgement, the unexpected.
- **The system guarantees that it can do so coherently:** prices and totals, who may be mailed, which thread a
  reply goes into, that a quote is recorded once, that a restart loses nothing. Numbers, identities, state.

We do not make the model do the system's job (it would invent a price), and we do not make the code do the
model's job (it would break on the first mail nobody wrote a rule for).

*In our code:* `pricing.py` computes every amount a customer sees; the agent only copies it. The agent decides
everything about language and next steps.

## 2. One agent, one session per deal

The challenge looks like a pipeline (read, price, reply) but a deal is a life: quote, then book, then track,
with people writing whatever they like in between. That needs memory and judgement across mails.

So there is one forwarder agent, and every thread has its own session that lives as long as the deal. A new mail
in the thread resumes it, with everything that happened before still in front of the agent.

*What this bought us on Saturday:*
- The first tracking question said "Status of our shipment 51447 to ORD, 676 kg", no booking reference. A
  matcher on references would have answered "please send the reference" and lost the bonus. The agent searched
  the CRM with the words it had and found the shipment.
- After a booking the customer wrote "Thanks for confirming". The agent decided nothing needed sending
  (`no_reply`). Nobody wrote a rule for thank-you mails.

"Router plus three agents" from 5U's slides is the same thing seen from outside: the router is plain code (by
sender and thread), the three agents are three tasks of one identity (quote, book, track).

## 3. Intelligence in the agent, guarantees in the tools

A new capability is a **tool** the agent can choose to use, or a **field** an existing tool returns. Not a step
bolted in front of the agent, not a classifier that decides for it, not if-then rules on mail text.

The tools are where hard guarantees live, and only there: the total comes from code; mail goes only to people in
the thread and carriers on our list; the first quote of a thread is recorded with its option; bookings use real
references.

*Examples:*
- Tracking: 5U told us the status comes from the airline by mail. We did not build a tracking pipeline; we gave
  the agent `carrier_status`, a tool that asks the airline and waits. When the airlines turned out to answer
  status questions with their quote form, the tool said so in its result, and the agent answered from our record
  instead. One tool, the agent's judgement around it.
- A pre-sort table of keywords (`lexicon.json`, "if the mail says 'günstigste', it is cheapest") was removed.
  The model already understands "günstigste", "le moins cher" and every phrasing nobody listed; the table could
  only be wrong where the model is right.

## 4. No hard checks on what the model writes

It is tempting to check the model's text in code ("block the quote unless it contains exactly one amount"). We
don't. A check on text is a rule about language, and language is exactly where rules break: the check blocks a
good mail it did not foresee, and gives the model nothing to learn from.

Instead: **teach with the prompt** (the criterion and the reason), and **measure with diagnostics** (we log when
a quote mail carries a second amount, and look at it).

*Example:* the research stress test found a quote with two totals. The fix that stayed is a sentence in the
prompt, "one mail, one option, one total: name the other option in words, no price", with the reason. The gate
that blocked sending was turned into a log line.

## 5. Flexibility from the data model, not from examples

5U changes the setup about once an hour, without warning, and it will get harder. If every failure is answered
by a patch for that one mail, we chase them all night. So when something fails, the question is: **what kind of
change is this, and how does the system handle the whole kind?** (`docs/likely-changes.md` lists the kinds.)

*Examples of fixing the kind:*
- A carrier might quote per kg, or itemised, without a total. Instead of handling "Solace's new format", the bid
  reader now captures the parts (rate per kg, minimum, surcharges, fees) and code computes the total for any
  carrier that does it.
- The airlines send monthly tariffs. A December tariff mailed in November would have repriced November
  shipments. Instead of "ignore tariffs for now", every sheet now keeps its validity and the price uses the one
  valid on the shipment's ready date.
- A customer wrote "New Delhi"; the agent asked which airport. We did not add "Delhi means DEL" for that mail: the
  tool now knows every city in our network, and the prompt says why a question costs more than an inference.

## 6. Prompts are soft: goals, criteria, the reason why

The prompts (`backend/app/prompts/`) say what a good outcome is and why, and leave the how to the model.
No procedures ("first do X, then Y"), no word lists, no word limits, no "never" without a reason.

A model reads a reason and applies it to cases the sentence did not mention; it reads a rule and applies it
literally, including where it is wrong.

*Example:* the agent wrote each mail twice, once as its own message and again inside `send_mail` (double tokens,
cluttered journal). The fix is one sentence that explains how the system works: "a mail exists only inside
send_mail; your own messages are notes for the team". Not a filter.

## 7. One place for each thing

Prices only in `pricing.py`. Model calls only in `llm.py`. State only in the register (`store.py`). One UI.

Two implementations of the same thing drift apart, and then one of them is wrong without anyone noticing.

*Examples (both removed):*
- `backend/synthetic/` carried its own pricing function to compute an answer key. Its tests passed while testing
  that copy, not the engine that quotes customers.
- A second dashboard on Cloudflare read 5U directly. It showed numbers that could disagree with our CRM, and it
  kept the team key on a personal account.

## 8. Measure, then decide

We decide from what the live system shows, not from what seems likely.

*Examples:*
- Which trucker 5U counts for door-to-port was a guess until rounds 1 and 2. We tested every rule against both
  rounds' real bids; only the 50/50 ratio rule matches both (`docs/challenges/5u-facts.md`). One rule, one test,
  from data.
- The accuracy formula (linear, zero at 10 % above the best price) came from one partly-scored round.
- Cost: a whole deal (quote, booking, tracking) costs about $0.0016 of model calls. Measuring is also how we
  found that a separate watcher's diagnoses cost 25 times our deals, on the same credits the gateway needs.
- Carriers did not understand "320 kg chargeable" and asked back: we found it by sending real mails, and the
  request template changed.

## 9. Simple, and only what is used

Every part must be used by the agent or by the system that runs it. A module that sits next to the agent and
watches it with its own rules is a second brain: it disagrees, it costs, and nobody owns its mistakes. If the
agent needs to know something, give it to the agent (a field in a tool result, a sentence in the prompt).

Deleting is a feature. On Saturday at 16:30 we removed a rule-based anomaly watcher, a second pricing engine,
dev scripts nothing imported, a duplicate dashboard and documents that contradicted the system. Everything that
mattered from them (fixes, evidence, the change catalog) was kept in its one place.

## 10. The human's word wins

A person can step into any deal from the UI: write to the agent ("offer them the faster option") or answer the
customer directly. The agent follows and does not undo it later. That is the "sessions UI" 5U asked for, and it
is also how the team corrects the system without touching code.

---

## Before a change, ask yourself

- Is this a **judgement** (belongs to the agent: prompt, or a tool it can choose) or a **guarantee** (belongs in
  a tool or the register)?
- Am I fixing **this mail**, or **the kind of change** it belongs to?
- Is there **already one place** for this? Then change it there.
- Does the **agent use it**? If not, why does it exist?
- How will we **know it worked**? Which round, mail or number will show it?

## How we work together

- `main` is what runs. Pull it, read this file and `AGENTS.md`, work on a short branch, `make test` and
  `make sim` (real model, fake 5U, nothing scored), then ask Mattia to merge.
- Never run `make live`: one machine answers the real mailbox; two would answer twice.
- A proposal is easiest to take when it says: what happened (round, mail, number), what kind of change it is,
  and the smallest change in the right place.
