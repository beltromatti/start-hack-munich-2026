# Competitor research: start here

For START Hack Munich, challenge 5U AI "Build the Forwarder". Collected Sat 21 Nov 2026 from public pages and
public videos.

## Where this lives

Branch `research/competitors` in the team repo. It has its own history, separate from `main`: never merge it
(git refuses by default, and so does a GitHub PR). It changes nothing in the forwarder. To open it next to your
checkout:

```sh
git fetch origin research/competitors
git worktree add ../start-hack-competitors research/competitors
```

Not in git: the downloaded videos (`video/clips/`, 234 MB). The links are in `BRIEF.md` section 5; frames,
contact sheets, subtitles and transcripts are here.

## Read in this order for UI work

1. `BRIEF.md`, section 2 "UI patterns worth copying": which screen of which company, with the file to open.
   Section 1 has the words and key numbers the jury (the 5U founders) use for their own product.
2. `index.html`: the picture gallery. The top block "Screens to copy" is the short list. Open it in a browser.
3. `scroll/<site>-NN.jpg`: one full screen per file, top to bottom of each website (1440 px wide). Look at these
   when you need the detail of a pattern.
4. `VISION-VS-CODE.md`: what 5U says its product does against what our code does. The last table rows name what a
   UI can only show with backend data (decision record, approval, memory).

## The screens that matter most

| File | Company | What to take from it |
| --- | --- | --- |
| `scroll/5u-product-06.jpg` | 5U AI | Freight data summary card: route, goods, weight, date |
| `scroll/5u-product-07.jpg` | 5U AI | "Observe your AI Worker": name, SOP, connections, capabilities, preferences |
| `scroll/5u-product-08.jpg` | 5U AI | Building blocks with a role tag: listener, worker, human in the loop, communicator |
| `scroll/5u-product-09.jpg` | 5U AI | "Waiting Offer Approval": urgent tag, route, weight, price, Edit and Send Offer |
| `scroll/nexcade-00.jpg` to `-03.jpg` | Nexcade | Timeline with a clock on every step, "agent steps, your calls, elapsed", held for review, account memory |
| `scroll/cargoone-ai-00.jpg`, `-03.jpg` | cargo.one | Agent steps as stacked cards with fold-out reasoning; one slider from co-pilot to autonomous |
| `scroll/zauber-product-06.jpg` | Zauber | The whole deal as one mail thread: request, rates checked, draft ready, reply |
| `scroll/pallet-04.jpg`, `-05.jpg` | Pallet | Alert, options compared, rule applied, one Approve button; action checklist with the system per step |
| `video/frames/wisor-webinar-demo/` | Wisor | Real product: the mailbox as a pipeline with value and tags per mail |
| `video/frames/raft-first-look/` | Raft | Calm start screen with counts, progress as a short list of steps |

5U's own look: warm off-white, dark navy panels, one orange-red accent, small pill labels, rounded cards
(`scroll/5u-home-00.jpg`, `scroll/5u-product-00.jpg`).

## Everything in this folder

| Path | What |
| --- | --- |
| `BRIEF.md` | Jury vocabulary, UI patterns, pitch proposal, the field, list of videos with links |
| `VISION-VS-CODE.md` | Founders' story against our code, ranked gaps, pitch lines that no longer hold |
| `index.html` | Gallery of all sheets and the screens to copy |
| `sheets/` | One overview picture per website (all its screens side by side) |
| `scroll/` | 207 single screens from 21 websites |
| `shots/` | One tall full-page picture per site (29 sites, some parts blank where the site animates on scroll) |
| `video/sheets/`, `video/frames/` | Contact sheets and single frames from 12 product videos |
| `video/clips/` | The downloaded videos |
| `transcripts/` | 5U CEO interview and blog posts, talks by Zauber, Nexcade, Wisor, Pallet, CargoAi, Augment |
| `img/` | Product images taken from the 5U and Zauber websites |
| `raw/`, `scripts/` | Saved pages and the tools that made the screenshots |

## Where our own UIs are

- Main UI of the team: `frontend/` on `main` (React, served by the backend on the production machine). Read
  `docs/how-we-build.md` and `AGENTS.md` first: short branch, then Mattia merges.
- A rework of that UI with the patterns above (decision record per quote, a clock and an actor on every step,
  freight card, 5U's KPI names): branch `sam/ui-decision-record`, frontend only, not merged.
- Sam also has a local read-only view of the 5U board and mailbox on his Mac (thread view, race per round). It
  is not shared because it reads 5U with the team key.
