# Pitch deck

Branch `jan-pitch-deck`, cut from `main`. All deck work happens here, never on `main`.
Nothing outside `pitch/` is touched on this branch.

## Open it

Open `pitch/deck/index.html` in a browser. Arrow keys move between slides.

## Change it

| File | What |
|---|---|
| `storyboard.html` | The source of every slide (section `#story6`). Edit slides here. |
| `deck/build.py` | Builds `deck/index.html` from the storyboard. Slide order and speaker notes are in `ORDER`. |
| `swarm-overkill/index.html` | The swarm slide. Table driven: change `AGENTS`, `TASKS`, `SIDE`, `HEAD`. |
| `frames/r/` | The pictures the slides use. |
| `tokens.css` | Colours and fonts. |

Rebuild after a change:

```
uv run --with beautifulsoup4 python pitch/deck/build.py
```

## Rules

- Product facts on a slide come from the code on `main`. No number without a source.
- Two people editing `storyboard.html` at once will conflict. Pull before you start, commit small.
