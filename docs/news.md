# News and times (from Discord, Hack League app, 5U)

Newest on top. Source in brackets.

- **Sat ~15:15 Tracking status comes from the carrier, by mail.** In transit, not yet, departed: that status has to
  live in our CRM, and the agent reads it with tool calls. There is no API for it. We get it by **mailing the
  carrier and asking where the shipment is**. Carriers don't mind repeated asks ("you are the customer, they answer
  you"). Replies can name a position or a disruption (Jan's examples: Malacca/Singapore Strait, Strait of Hormuz).
  Build: a direct line CRM <-> carrier. The booking record keeps the airline's address and thread, a status request
  goes out, the reply is parsed (LLM) into status, location and ETA on the booking, and the customer's tracking
  question is answered from that record (Jan asked 5U at the booth).
- **Sat ~15:15 Margin is not what we optimise.** Question: carrier says €50, we quote €55, the customer says "only
  for €40". 5U: that can happen at some point, but margin is not important. **The main job is finding the truly
  cheapest option once every criterion is counted** (chargeable weight, next weight break, surcharges, pickup
  trucking, cheapest vs fastest as asked). That matters more than the price we add on top, and we are not scored
  against the other teams' quotes. Whatever profit there is comes from buying cheaper. Consistent with 14:00: margin
  shows in the CRM as insight, the quote stays at our best cost (Jan asked 5U at the booth).
- **Sat 14:37** Only models through the 5U gateway count (list in Swagger). Other models / local GPUs: cost can't be
  measured, those quotes get zero points ("on time", likely meant cost). 5U is working on more models (taci).
- **Sat 14:13** Tracking bonus is **per shipment**: every booked shipment can get a tracking question later, each
  correct answer up to +10, only the first answer counts, unbooked shipments get no tracking question (fehmi).
- **Sat 13:47–14:05** 5U mailed **kit cards** (API key + Base URL) from fehmi@5u.ai to each team's registered
  email. "START Milan" was on the missing list at 13:47, gone from it at 13:49. Without the card: no API key.
- **Sat 13:44** Scoring confirmed **45-40-15** (accuracy / LLM cost / time); an older doc showed 30 for cost (taci).
- **Sat 14:00** Confirmed by Jan: first RFQ **16:00**, **every team pitches** (not only top 5), jury criteria are the
  brief's (1. pitch, 2. UX and design, 3. codebase, 4. how human the emails read). **Margins: yes, in the CRM** as
  insight per lane and quote. The quoted price stays at our best cost: a margin on top pushes the quote above the
  best price, and more than 5 % above is rejected. Kit card: `docs/challenges/5u-kit.md` (Jan).

- **Sat 13:2x** Allocated: **5U AI "Build the Forwarder"** (Hack League app, Cases).
- **Sat 12:55** 5U posted the official brief + deep-dive slides: `docs/challenges/5u-official-brief.pdf`,
  `docs/challenges/5u-deep-dive-slides.pdf` (Discord #5u-ai).
- **Sat 12:53** First 5U mail (RFQ) planned for **16:00** (fehmi, Discord #5u-ai).
- **Sat 12:29** OpenAI credits by email: $50 ChatGPT/Codex + $20 API, subject "START Hack Munich vouchers",
  redeem by Sun 23:59 (announcements).
- **Sat 11:45** 5U: every team can pitch to them at the end and compete for the top 3 (Discord #5u-ai).

## Fixed times
| When | What |
| --- | --- |
| Sat 16:00 | 5U: first RFQ, then one every 6 min all night |
| Sat 16:00–17:00 | Recruiting hour |
| Sat 19:00–21:30 | Dinner |
| Sun 12:00–12:45 | Submission form open, **hard cutoff 12:45** |
| Sun 13:15–14:45 | Demos, one room per challenge: 3 min pitch, 2 min Q&A |
| Sun 15:30 | Challenge winners; 16:45 overall awards |

Prizes 5U: 1. fly an ultralight plane yourself (Jochen Schweizer) + €300, 2. Hans Zimmer concert tickets + €200,
3. founders dinner + €100.
