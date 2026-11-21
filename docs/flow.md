# The whole flow: quote, book, track (Sat 21 Nov, ~15:20)

Context for all of us and our agents. The 14:15 discussion designed the pricing step only. Steps 2 and 3 need
state that carries across mails. Main's `backend/app/forwarder.py` (a6d3320) already has all three. This file says
how they connect, where each fact comes from, and what is still weak.

## The memory is the register

There is no separate memory system. Every mail is stored (`store.save_mail`), and every piece of work is a record
in the register (`store.put` / `store.update`), keyed so the next mail finds it:

| Record | Key | Status path | Written by |
| --- | --- | --- | --- |
| RFQ | `rfq-<thread root id>` | collecting -> quoting -> quoted -> booking -> booked / lost | step 1, step 2 |
| Booking | `booking-<thread root id>` | booked / requested (by mail) / failed -> confirmed | step 2 |
| Mail | mailbox id, with `references` (the thread) | handled yes/no, kind | every step |

A follow-up mail finds its RFQ through the thread root (`references` in the poll answer). That is why every reply
must set `in_reply_to`: the thread is the join key.

## Step by step

| Step | Trigger (mail in) | Reads | Does | Writes |
| --- | --- | --- | --- | --- |
| 1 Quote | customer mail, new thread | thread text, tariffs, portal, carrier bids | parse (LLM), bids + portal + sheets (code), price (code), write (LLM), reply in thread | RFQ quoted, amount, chosen offer incl. `rate_id` |
| 2 Book | customer mail in a quoted thread, intent accept | RFQ record | `POST /v1/portal/bookings` with `rate_id` + our `team_reference`. 410: fresh rate, same airline. 503 or email-only airline -> booking mail in the bid thread | Booking record, RFQ booked, confirmation to customer |
| 2b Confirm | airline mail "Booking <ref> confirmed" | Booking records | match by rate_id / team_reference / booking_reference | Booking confirmed |
| 3 Track | mail from `tracking@hackloop.mail` | Booking records | match reference in the text, compute ETA = booked_at + transit_days (code), write (LLM) | tracking answer logged |

## Where each fact comes from (checked in `docs/challenges/5u-api/openapi.json`)

- **booking_reference:** the portal's 201 answer, or the airline's confirmation mail when we booked by mail.
- **Shipment status:** nobody sends it. "There is no status call; keep the booking in your own CRM" slop-ok
  (`POST /v1/portal/bookings`). So the carrier gives us the booking once, and everything after is what we stored.
- **Tracking questions:** from `tracking@hackloop.mail`, only for booked shipments, each correct first answer
  up to +10 (`docs/news.md`, Sat 14:13).
- **Transit days, airline, price:** the rate we booked (`Rate.transit_days`), stored on the booking.

## Architecture decision

Keep main's design: **code decides the next step from the record's status, the LLM only reads and writes.**

- The options are not alternatives. "Skills" are our prompt files (`app/prompts/*.md`), the "orchestrator" is
  `classify()` (by sender and thread, no LLM), and the real question is who picks the next step: code or model.
- **Why code picks:** cost is 40 of 100 points and full marks need about $0 per quote. Time is 15. A tool-calling
  agent re-reads a growing context on every turn, which costs both. A state machine also survives a restart: the
  register says where every shipment is.
- **Where an agent fits:** the red cases only (giraffe, grounded planes, a mail no status covers), as the second
  approach from the 15:50 talk. It gets the same tools and writes to the same register.

## Weak spots in main's code (verified, proposals for whoever owns `forwarder.py`)

1. **Tracking matches on references only** (`on_tracking`). If the question names the shipment by route, weight,
   company or the original thread instead of a reference, we answer "send us the reference". Only the first answer
   counts, so that loses the +10. Fix: fall back to the customer's email or company, then route + weight, over the
   booking records, before asking.
2. **No customer history across threads.** Records are keyed by thread root. A returning customer is a stranger
   (the memory layer asked for at 15:50). Fix: a `customer-<email>` record with quotes, bookings, won/lost, read
   by the writer.
3. **ETA is booked_at + transit_days.** Good enough until 5U adds departure dates or delays. When tracking answers
   start failing on the board (`/v1/board/me` reason codes), that is the first suspect.
