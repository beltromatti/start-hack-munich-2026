# Who does what (5U AI)

Draft from Sam's vision session, Sat 21 Nov. Compare with Jan's and Mattia's notes, then fix it together.

## Vision so far (Sam)

**Our question:** "How does an autonomous forwarder stay right at 2 a.m. when the world changes without warning?"
Lead on pricing, accuracy and speed; the competitive advantage is **Jan's prediction engine**, which ties the
whole system together.
**Where the engine sits: as the watcher** (is this an outlier or a disruption?). Real data will be thin, so we
**simulate** more data as we go and learn from our own mistakes.

- **AI reads, code prices.** The funnel (routing, reading RFQs, bids, tariff sheets) is AI-led.
  The price itself comes from our own pricing engine, in code, no LLM.
- **Different, not just better:** everyone does prices. We focus on **supply-chain disruptions and outliers**
  and how the system handles them.
- **Self-improving harness:** learns from replies and from whether a quote gets accepted;
  prepared ("pre-trained") for the disruptions and how we handle them.
- **Human-sounding mail:** a `human.md` with the tone, improved over time. Not AI-sounding.
- **Autonomous overnight and competitive.** Human in the loop only where something suddenly changes.
- Look and feel: strong UX/UI combined with a well-thought-out, competitive pricing system.

## Roles

| Who | Owns | Notes |
| --- | --- | --- |
| **Sam** | Product, design, UX/UI (Mobbin references, Sempli code reuse), sessions UI and dashboard, `human.md` tone | |
| **Jan** | Prediction engine (his own, trained on residual values) and how it feeds pricing, disruptions and outliers | Open questions below |
| **Mattia** | _open_ | To agree with Mattia |

## Open questions for Jan (prediction engine)

1. What exactly does it predict, and from which inputs?
2. What data was it trained on (residual values of what: IT, medical, industrial equipment)?
3. What would it predict here: best price, carrier speed, chance of acceptance, outlier / disruption risk?
4. How fast and how cheap is one prediction (the 6-minute window, 2 minutes for full time points, LLM cost scored)?
5. Can it run locally without the LLM gateway?

## Open questions for the team

- Who watches the system overnight, and what does it do on its own when nobody is there?
- How does the system notice an unannounced change (failed quotes, new fields, portal errors)?
- What must run at 16:00 (first RFQ)?
