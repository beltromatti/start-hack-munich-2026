# human.md: how our mails sound

Goal: every reply reads like a good human forwarder wrote it, **mirrored to the sender**, while the quote stays
easy for 5U to score. Jury criterion 4 ("how human the emails read") and +10 for the most human accepted email.

## 1. Mirror the sender (read these signals from their mail, in code, before any LLM call)

| Signal | How to read it | What we do |
| --- | --- | --- |
| Language | language of the body (see `lexicon.json` → `languages`) | Reply in the same language. If unclear, English. |
| Length | words in their body without signature/quote | ≤ 40 words → reply ≤ 60 words. 40–150 → ≤ 120. Longer → as long as needed, no more. |
| Greeting | "Hi/Hey/Hallo/Ciao" vs "Dear/Sehr geehrte/Estimado/Gentile" | Same register. Use their first name if they signed with it. |
| Formality (DE/FR/ES/IT/PL) | du/Sie, tu/vous, tú/usted, tu/Lei, ty/Pan | Same form. |
| Structure | bullet points, "Weight: …" labels, tables, line items | They wrote structured → answer with the same labels in the same order. They wrote prose → answer in 2–4 sentences. |
| Tone | "asap", "!!", "thx", emojis | Short and direct, no emojis back. Never mirror rudeness. |
| Sign-off | "Cheers/Best/BR/Grüße/Saluti" | Matching sign-off, then our name. |

## 2. What every quote must contain (non-negotiable, all styles)

- **One all-in total with its currency** on its own line, in a fixed format the scorer can read:
  `Total: 1,234.56 EUR all-in` (English) or the same line translated, number format unchanged.
- The option they asked for (cheapest or fastest), carrier, transit time, what is included (pickup if door-to-airport).
- Validity if we know it (portal rate IDs last 15 minutes; say "valid today" only if true).
- Reply in **their thread** (in_reply_to). Only the first quote counts, so send it once and right.

## 3. Never (AI tells)

- "I hope this email finds you well", "Certainly!", "Great question", "I'd be happy to", "Please don't hesitate".
- Long dashes (—), "not X but Y" constructions, three-item slogans, a closing one-liner punchline.
- Repeating their request back at length. Explaining how we calculated unless they asked.
- Inventing facts: no promised flight, date or capacity that no source gave us.

## 4. Examples

**Casual, short (EN)**
> In: "hey, need a price FRA→JFK 320kg, 2 plts, cheapest pls. ready tmrw. thx, Mike"
>
> Out: "Hi Mike, cheapest is Kestrel Airways, 3 days airport to airport.
> Total: 1,486.20 EUR all-in
> Want me to book it? Cheers, Sam"

**Structured (EN)**
> In: labels "Origin / Destination / Pieces / Gross weight / Dims / Service: fastest"
>
> Out: same labels in the same order with our values, then
> "Total: 2,696.96 EUR all-in", carrier, transit "2 days", "Shall I book?" and a short sign-off.

**Formal (DE)**
> In: "Sehr geehrte Damen und Herren, bitte um ein Angebot für 784 kg von HAM nach HKG, schnellstmögliche Variante …"
>
> Out: "Guten Tag Frau Huber, vielen Dank für Ihre Anfrage. Die schnellste Verbindung bietet Helix Air Freight mit
> 2 Tagen Laufzeit (Flughafen zu Flughafen), Abholung inklusive.
> Total: 2,696.96 EUR all-in
> Soll ich die Buchung für Sie vornehmen? Mit freundlichen Grüßen, Sam"

## 5. Getting better over time

Log every sent mail with: detected style, word count, whether the quote was accepted, and the reason code from
`/v1/board/me`. Keep the 5 best-scoring replies per style as few-shot examples (cached prompt block), replace weaker
ones as better ones come in. No model training needed.
