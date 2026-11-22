# Pitch deck

Branch `jan-pitch-deck`, cut from `main`. All deck work happens here, never on `main`.
Nothing outside `pitch/` is touched on this branch.

## Open it

Open `pitch/deck/index.html` in a browser. There is no build step.

| Key | What |
|---|---|
| Arrow keys, space, enter | next and previous slide. On the swarm slide space plays the scene first |
| `n` | speaker notes |
| `f` | full screen |
| `#s4` in the address | jump to slide 4 |

To show it as a claude.ai artifact, run `python3 bundle.py <out dir>`. It writes a flat copy (no `../` paths, no document tags) that is published with its files.

## Change it

| File | What |
|---|---|
| `deck/index.html` | Every slide, written by hand. One `<section class="st">` per slide, its speaker note in `<p class="note">`. |
| `deck/deck.css` | The look. Colours and fonts are the Desk's own (paper #eef2e8, ink #141414, green #15884a, Inter, JetBrains Mono). |
| `swarm-overkill/index.html` | The swarm scene of slide 3. Change the data tables (`NAMES`, `REGIONS`, `SAYS`), open it with `?t=7.6` to hold one moment. |
| `shots/` | Real screens of the Desk and the voice app, demo build, example data. |
| `sources/headlines.md` | The press pieces of slide 2 with date, headline and the words that may be quoted. |
| `deck/frames/` | Pictures the slides use. |
| `storyboard.html` | The old deck, kept as archive. |

## Rules

- A product fact on a slide comes from the code on `main`. A number comes from a named source or is labelled example data.
- The agent is called Giulia on every slide, never "she".
- Ten slides are spoken, in the order of their `data-o` number, wherever they stand in the file: question, press, swarm, team photo, three principles, product, what we do differently, Auer, vision, close. Each slide has one centred headline and as few words as possible. A `<section class="st bk">` is backup and plays after the close.
- The position is AI first: Giulia acts, a person oversees. Slide 5 states the approach as three principles on a white ground: one agent per deal, prices come from code, your word wins. Slide 7 states the difference: others ask for approval, Giulia acts. The Desk's three states (green, amber, red, from `Desk.tsx` and `Ground.tsx` on `main`) are named there and on the product slide. The result of the scored night is said at the close. The four-step architecture and the earlier slides "AI first: Giulia acts" and "Giulia decides. Code guarantees." are backup.
- The Auer slide quotes real mails from the scored run word for word (ids 38215, 38231, 38270). Times are CET.
- The three numbers on the close are from the 5U board, Sunday 10:53. Refresh them and the time from the final board.
- Slide 9 is the vision, one loop with four labels. What is built is said as "today", the rest as the plan.
- The swarm scene of slide 3 plays once (`?once`), holds its last frame, and a key or click then moves the deck on.
- Serif type appears only in the press clippings of slide 2.
- Pull before you start and commit small.
