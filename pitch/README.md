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
- Ten slides are spoken: question, press, swarm, team photo, Auer, Lindqvist, product, memory, vision, close. A `<section class="st bk">` is backup and plays after the close, wherever it stands in the file.
- Slides 5 and 6 quote real mails from the scored run word for word (ids 38215, 38231, 38270 and 39221, 39471). Times are CET.
- The three numbers on the close are from the 5U board, Sunday 10:53. Refresh them and the time from the final board.
- Slide 9 is the vision. What is built says "today", the rest is said as the plan.
- Serif type appears only in the press clippings of slide 2.
- Pull before you start and commit small.
