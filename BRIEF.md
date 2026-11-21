# Competitor brief: 5U AI and its field

Research for START Hack Munich, 5U AI "Build the Forwarder". Collected Sat 21 Nov 2026, 15:55–16:30.
Everything here is from public pages and public videos. No sign-ups, no gated content.

Open the picture gallery: `open index.html` in this folder.

## 1. What the jury says about its own product

Source: written interview with CEO Yagiz Abik (CargoForwarder Global, 28 Jul 2026), the 5U blog post
"One second. What's actually happening in logistics?" (24 Sep 2025), the funding release and 5u.ai.
Full texts: `transcripts/5u-ceo-interview-cargoforwarder.txt`, `transcripts/5u-blog-one-second.txt`,
`transcripts/5u-blog-funding.txt`.

**Their words. Use them, they will recognise them.**

| Their term | What they mean | Where we have it |
| --- | --- | --- |
| AI Worker (never "bot", never "chatbot") | A colleague that does the job end to end | Our forwarder agent |
| Stateful | A thread can go quiet for three months, the Worker picks up the same case | One session per mail thread |
| Decision Layer / Context Layer | Every decision kept as a record: what, on what data, with what confidence | Show a decision record per quote |
| Self-heal | A source breaks, the Worker finds another route, finishes, and saves the new way to memory | Our disruption handling |
| Memory | Corrections are written to memory. "Your colleague taught me this. Do you approve changing it?" | Show a "learned" entry after a disruption |
| Shadow mode | Runs next to the humans first, nothing goes out | Our dry runs on recorded rounds |
| Grader / evaluation platform | Simulates thousands of freight scenarios, every SOP change is regression-tested before production | Jan's synthetic mails and the replay of recorded rounds |
| Human approval flow | "Here's my pricing, can I send it?" Thumbs-up or correction, approval is removed for routine cases later | Green / yellow / red |
| SOP | The customer's process in plain language | `human.md`, pick rules |

**One trap.** Abik: "workflows are jails for agents, RPA 2.0" and "freight is too messy for if-this-then-that".
Our line "AI reads, code prices" can sound like a rigid workflow. Say it this way: *one agent per thread
decides, and it uses a price calculator as a tool*. Avoid "workflow", "pipeline", "rules engine" in the pitch.
Say "agent", "tools", "memory", "decision record".

**Their numbers.**
- 15 minutes per quotation for a human, about 2 minutes for the Worker, tens in parallel.
- A mid-sized forwarder gets 200 to 300 quotation requests a day, 3 to 4 people only answer them, many stay unanswered.
- Up to 70% of forwarding work is repetitive copy-paste between two screens.
- Live customers reach 85–95% automation on single use cases.
- Win rates more than doubled within weeks at selected customers.
- "Requests arriving at midnight from Toronto are won while everyone sleeps."

**Their own KPIs (from the blog). Put these exact names on our dashboard.**
- Time-to-First-Response (TTFR) on RFQs: "the clock that shapes win rate"
- Ask Rate vs. Error Rate: "high ask, low error = healthy guardrails"
- Exception Half-Life: time from first signal to a concrete next step
- Closed-Loop Percentage: finished jobs with confirmation sent and systems aligned
- Thread Reopens per Job
- Delta: Customer Truth vs. System Truth

**Their definition of intelligent** (blog): "holds the whole story, chooses the next step, asks when unsure,
and proves what it did." Four claims, four beats for our demo.

Other lines of theirs: "From inbox to invoice." "We do not propose another tool. We propose the work being done."
"Software that keeps the plot." "A calmer Tuesday." "We are not a family, we are a sports team, and we are here to win."

Team on the jury side: Yagiz Abik (CEO, traded electronics from Shenzhen at 18, the "attacker"),
Fehmi Sener (CTO, ex BMW, thesis with CEVA on ML, the "playmaker"). They met on a football pitch at TUM.

## 2. UI patterns worth copying

Pictures are in `scroll/` (one screen per file) and `sheets/` (overview per site). Video frames in `video/frames/`.

**From 5U AI itself** (`scroll/5u-product-06.jpg` to `-09.jpg`)
1. Freight Data Summary card: route, goods, weight and pieces, date. Four rows, one icon each.
2. "Observe your AI Worker" card: Name, SOP, Connections, Capabilities, Preferences, Active switch.
3. Four building blocks with a role tag: Email Listener (TRIGGER), AI Worker (PROCESSING),
   Human in the Loop (PROCESSING), Communicator (COMMUNICATION).
4. "Waiting Offer Approval" card: URGENT tag, route, weight, price, sender, two buttons: Edit and Send Offer.
5. Look: warm off-white, dark navy panels, one orange-red accent, small uppercase pill labels, rounded cards.

**Nexcade** (`scroll/nexcade-00.jpg` to `-04.jpg`). The best reference for our sessions view.
- A timeline per request with a clock on every line: "09:14:02 CASSIE New email · rate request, 2 pallets, 480 kg, HKHKG → GBLHR, air".
- A counter in the header: "Agent steps 2 · Your calls 0 · Elapsed 0m 09s".
- A "Held for review" note: nothing goes to a customer, carrier or TMS until the team releases it.
- A map of sources: "The answer exists. It's in seven places." Inbox, TMS, rate portal, spreadsheet, tariff sheets, house rules, someone's head.
- Account memory: "Tail lift at Reading · saved to the account, from quotation". Then the next request uses it.
- A Replay button.

**cargo.one** (`scroll/cargoone-ai-00.jpg` to `-03.jpg`)
- Agent steps as stacked cards: Parsing Agent (completed), Rate Retrieval Agent (in progress), each with a fold-out "Reasoning" and chips for the extracted fields.
- "You control the pace": one slider with Co-pilot, Supervised, Autonomous.
- Six steps: request parsing, rate retrieval, quote assembly, validation (margin, anomalies, logged), delivery, central logging.

**Zauber** (`scroll/zauber-product-06.jpg` and following)
- The whole story as one mail thread: customer mail, then "Checked rates from: special-deals-sheet.xlsx, Maersk Spot, MSC", then "Draft ready" with a Send button, then the reply.
- "SOP update suggestion: You've regularly changed the delivery address of ACME Inc. Should I remember this?"

**Pallet** (`scroll/pallet-04.jpg`, `-05.jpg`). The best reference for disruptions.
- Alert, three numbers, "Recommended action · 3 options compared" as a small table (option, delivery, cost), "Rule applied ✓ Passed", one Approve button.
- An action checklist with the system next to each line: Read PO attachment (PDF), Check stock (WMS), Enter order, Book carrier (TMS), Create invoice (ERP).

**Wisor** (`video/frames/wisor-webinar-demo/`, live demo in their webinar from 44:20)
- The mailbox as a pipeline: inbox value in money, outstanding profit, tags per mail: Quote Ready, Missing Details, Incomplete Pricing.

**Raft** (`video/frames/raft-first-look/`)
- A calm start screen: "Good morning, Dylan!" with four counts. Progress as a short list of steps. "Packing list is missing", then the drafted mail.

**What every one of them shows.** The original mail, the extracted shipment, the sources checked, a draft,
one approve button, and a log. Nobody shows a chat window as the main screen.

## 3. Pitch

**What the field repeats**
- The gap between work and waiting. Nexcade: "It's 20 minutes work but it's taken 22 hours."
- Mail stays. Zauber: "You cannot move stakeholders away from email." "Email is the fabric of the future."
- Night and time zones. Zauber: "AI can already go while you're sleeping." 5U: midnight from Toronto.
- Best process every time. Zauber: "Run your best process every time."
- Control. Nexcade: "Every step on the record. Nothing leaves without you."
- Real against fake agents. Pallet: "Force every vendor to run a real test."
- Self-repair. Nexcade: if the rate is missing from the sheet, the agent mails the carrier.
- Air freight detail. CargoAi: "Everything below 300 kilos, you automatically go find a rate, book and sell to the customer."
- People stay. Zauber: 80% of manual work run by AI, the long tail stays human. Augment: "Your team actually gets to log off."

**Objections the jury will have in mind**
- Is it a workflow in disguise? (see the trap above)
- What happens when a source changes? Show it live.
- Can I see why it priced this way? Show the decision record.
- When does it ask? Show ask rate against error rate.
- What does it cost per quote? We have the number from the gateway.

**Proposal for the three minutes**
1. 0:00 Hook. "02:13. A request from Toronto lands. Nobody is awake." A human needs 15 minutes. Many requests get no answer.
2. 0:20 One live thread. Mail in, shipment extracted, sources checked, price from the calculator tool, quote out. Show seconds and cost on screen.
3. 1:10 The world changes. A carrier answers in another currency, or a sheet is out of date. The agent notices, finds another route, finishes, and writes it to memory. For a real outlier it asks one precise question.
4. 1:50 Proof. Our board numbers in their KPI names: Time-to-First-Response, price gap to best, cost per quote, ask rate against error rate. Every change is replayed on recorded rounds before it goes live.
5. 2:30 Why us. One agent per thread with tools, the price is computed and not guessed, we learn from the whole board.
6. 2:50 Close on their four: holds the whole story, chooses the next step, asks when unsure, proves what it did.

For the two minutes of questions: offer them to send a request themselves and make it harder.
Zauber's founder sells this way and says slides do not work when "everyone's pitching AI".
HappyRobot's seven-minute "Rapid Fire Demo" is a good model for pace: https://www.youtube.com/watch?v=CXpGJqO4mOw

## 4. The field

Funding and customers as reported by the linked sources or shown on the company's own site. Not checked further.

| Company | Where | What | Notes |
| --- | --- | --- | --- |
| **5U AI** | Munich | AI Workers for forwarders: Rate Manager, Track & Trace, Document Entry | Founded 2025. $3.2M pre-seed, Emerge Capital, Jul 2026. Customer named: TCI International Logistics |
| **Zauber** | Berlin | Agents for sea and air forwarders, inside Outlook and CargoWise | Founded 2024 by Erik Muttersbach, ex CTO of Forto. Hellmann quoted on the site. Own claim: live in 40+ country branches |
| **Nexcade** | London | Agents for the rate life cycle: procurement, pricing, booking | $6M seed led by Project A, Jul 2026. Logos on site: XPO, Zencargo, Cardinal |
| **cargo.one** | Berlin | Air freight booking platform, now AI quoting and an MCP server | Hellmann quoted. Saudia Cargo uses its AI worker |
| **CargoAi** | Paris | Air cargo marketplace, CargoCOPILOT agent | Own claim: 446,000 quote requests read in two years |
| **Wisor** | Israel | Mail to quote, rate management on top of the TMS | Public webinar with live demo |
| **Raft** | London | "AI workforce for supply chain", strong on documents and customs | |
| **Starboard** | Toronto | Quoting agent for forwarders | $5.5M seed led by Eclipse, Dec 2024. About 25 design partners |
| **Freightmate AI** | US | Documents and data entry for forwarders | $5M seed led by FUSE |
| **Pallet** | US | Agents for logistics operations, memory of house rules | Priced per successful outcome |
| **Vooma** | US | Agents for brokers: quote, build, schedule, track | |
| **HappyRobot** | US | Voice and mail agents for freight | The Loadstar writes of a $1.2bn valuation |
| **Augment** | US | "AI teammate" Augie | $85M round, Redpoint made a film about it |
| **Burt** | US, YC W26 | AI teammates for brokers and forwarders | |
| **Prox** | US, YC F25 | Agents for 3PLs | |
| **Evos** | New York | AI operators for the back office | $9M pre-seed |
| **Levity, Nimble, Fretie, FreighAI** | Berlin and others | Mail automation and quoting for forwarders | Smaller |
| **C.H. Robinson, Flexport** | US | Incumbents with their own agents | |

Asia and Australia: the searches found no funded agent startup for forwarders there. What exists are rate
and TMS vendors with AI features (Freightify, GoFreight, Fr8Labs). Screenshots are in `shots/`, not checked in depth.

Where 5U sits: the youngest and smallest of the funded European three (Zauber, Nexcade, 5U). Zauber sells to the
top 20 forwarders, Nexcade leads with pricing and tenders. 5U goes for mid-sized European forwarders, deploys on
site and talks about a team of Workers and the Decision Layer.

## 5. Videos

| Who | What | Link | Local |
| --- | --- | --- | --- |
| 5U AI | Founder on The SaaS CFO, 21 min | https://www.youtube.com/watch?v=Vi9qMHzGVYY | not transcribed, YouTube blocked the captions |
| 5U AI | Founder on egirişim, 29 min, Turkish | https://www.youtube.com/watch?v=hDJZJp89yVM | not transcribed |
| Zauber | "How AI Is Rebuilding Freight Forwarding", 29 min | https://www.youtube.com/watch?v=Yt4P2TkTXYw | `transcripts/zauber-platform-engineering.txt` |
| Zauber | "Most Forwarders Won't Survive the AI Shift", 61 min | https://www.youtube.com/watch?v=UyCZujh320M | `transcripts/zauber-supply-chain-tech-podcast.txt` |
| Zauber | The Loadstar podcast, 26 min | https://www.youtube.com/watch?v=FfdQdX7r4sY | not transcribed |
| Nexcade | "The End of Manual Pricing?", 32 min | https://www.youtube.com/watch?v=LllIYMO-I0o | `transcripts/nexcade-lets-talk-supply-chain.txt` |
| Wisor | Webinar with live demo from 44:20 | https://www.youtube.com/watch?v=N0SC7Qmfbfs | transcript and `video/frames/wisor-webinar-demo/` |
| Wisor | Rate management demo, 2 min | https://www.youtube.com/watch?v=N1IxLrJISlg | `video/frames/wisor-rate-mgmt-demo/` |
| Raft | First look at the platform, 1 min | https://www.youtube.com/watch?v=rp5b9j324KE | `video/frames/raft-first-look/` |
| Pallet | "Why 95% of AI Agents are Fake", 12 min | https://www.youtube.com/watch?v=wAiY5Guo7N4 | `transcripts/pallet-ceo-95pct-fake-agents.txt` |
| Augment | Platform overview, 4 min | https://www.youtube.com/watch?v=-tNYQntaadY | `video/frames/augment-augie-overview/` |
| Redpoint (VC) | Film on Augment's $85M round, 4 min | https://www.youtube.com/watch?v=dr_17s30hwY | `transcripts/augment-redpoint-85m.txt` |
| YC Root Access | HappyRobot, 28 min | https://www.youtube.com/watch?v=W_UgM6iT7Do | not downloaded |
| HappyRobot | Rapid Fire Demo at FreightWaves F3, 7 min | https://www.youtube.com/watch?v=CXpGJqO4mOw | not downloaded |
| Burt | YC W26 launch video, 1 min | https://www.youtube.com/watch?v=Jj7XKdMwE1Q | not downloaded |
| Vooma | Scheduling worker demo, 5 min | https://www.youtube.com/watch?v=BcNogehN3CY | `video/frames/vooma-schedule/` |
| CargoAi | Interview on Air Cargo Update, 11 min | https://www.youtube.com/watch?v=fUjrRquJO7M | `transcripts/cargoai-air-cargo-update.txt` |

## 6. The webinar idea

There is no recorded Zauber webinar to sign up for. Zauber's only event of that kind was an in-person
"AI master class" at the Xeneta Summit in Munich on 4–5 Nov 2026, and no recording is public. Neither 5U AI nor
Zauber show a real product screen in any public video. Their websites carry stylised product mock-ups, which are
in the gallery. The closest thing to a real competitor demo is Wisor's webinar, which is public on YouTube.

## Sources

- https://cargoforwarder.eu/2026/07/28/5u-ai-from-football-to-agentic-ai-freight-start-up/
- https://5u.ai/ · https://5u.ai/product · https://5u.ai/blog/one-second-whats-actually-happening-in-logistics · https://5u.ai/blog/5u-ai-raises-3-2m-pre-seed-funding
- https://tech.eu/2026/07/28/5u-ai-lands-32m-pre-seed-for-ai-freight-workforce-platform/
- https://gozauber.com/ · https://gozauber.com/product
- https://nexcade.ai/ · https://theloadstar.com/ls_press_release/nexcade-raises-6m-to-build-ai-agents-for-freight-forwarders/
- https://www.cargo.one/ai/forwarder-quoting-workflow
- https://www.ajot.com/news/cargoais-ai-agent-now-handles-70-of-air-cargo-email-inquiries-for-airlines-and-forwarders
- https://theloadstar.com/starboard-bets-ai-can-give-smaller-forwarders-a-fighting-chance/ · https://eclipse.capital/blog/a-smarter-supply-chain-our-investment-in-starboard/
- https://www.freightwaves.com/news/freightmate-ai-raises-5m-highlights-need-for-flexible-freight-forwarding-tech
- https://www.forwardernews.com/news/2026-10-18-evos-raises-9m-for-ai-operators
- https://theloadstar.com/ai-has-reached-forwarders-pl-now-the-arguments-begin/
- https://www.ycombinator.com/launches/Pc6-burt-ai-teammates-for-logistics
