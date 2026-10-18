# Design brief

Written with the `design-grill` and `frontend-design` skills (`ui-skills/` and `.claude/skills/`).
Every UI change reads this first.

## Subject

A scheduler for one clinic. **Primary user:** a receptionist working at a desk under time pressure,
mostly on a desktop, sometimes on a tablet or phone. **Primary job:** find a free slot, book it
without making a mistake, and see the day at a glance.

## Direction (answers from the interview)

- **Personality:** calm and precise. Reassuring, unhurried, nothing ambiguous.
- **Feeling:** confident that what is on screen is true, and that a warning is a real one.
- **Colour:** clinical ink-green on cool chart paper, with amber for cautions and oxblood for danger.
  Not teal on white, not cream with terracotta.
- **Type:** a serif for page titles and the clock-like numerals, a neutral sans for forms and tables.
  System fonts only: no network requests, no new dependency.
- **Motion:** only in response to an action (hover, press, expand, confirm). Nothing moves on its
  own. `prefers-reduced-motion` is respected.

## The one memorable thing

The day view is an **appointment book**, not a grid of cards. Times run down a left gutter in the
serif, each slot is a ruled line, a booked slot is written in ink with a bar on its edge, and a free
slot is an empty line that fills when you point at it. Everything else stays quiet.

## Tokens

| Name | Light | Dark | Role |
|---|---|---|---|
| Paper | `#F1F4EF` | `#0E1A17` | page |
| Sheet | `#FAFBF8` | `#14231F` | surfaces |
| Ink | `#14302A` | `#E4EEE9` | text |
| Pine | `#1F5A4C` | `#5FC0A3` | primary action, focus of attention |
| Ledger | `#CBD5CC` | `#2A3D37` | rules and borders |
| Amber | `#6E4A0C` on `#FAF0D6` | `#F0D58C` on `#2F2610` | caution (deposit, test clock) |
| Oxblood | `#7D2222` on `#F9E6E3` | `#FFB9B1` on `#341715` | danger, no-show |

Spacing is a 4px scale, radius is 6 for controls and 10 for containers, borders carry structure and
shadow is kept for things that float (the dialog). All values live in the `:root` block of
`frontend/src/styles.css`.

## Rules for this UI

- Status is always text plus a shape, never colour alone.
- No all-caps labels, no eyebrows, no numbering except where the content is a sequence (the four
  booking steps).
- One border radius per level of hierarchy, one shadow, no gradients.
- Buttons say what they do ("Book this slot", "Save details").
- Every state is designed: loading, empty, error, success, disabled.

## UI pass, October 2026

What changed, from a review of the rendered screens at 1280, 768 and 390 px:

- The header keeps the five links used all day; Report, Doctors, Messages, Staff and the rule proof sit in a "More" menu that shows the attention count on its button.
- Appointment actions show only what is allowed, with one sentence on why the rest are not.
- The day view's side panel shows booked and free counts and a one-press "Book it" for the next free time until a booking is selected.
- The booking form says what pressing the button will do, or what is still missing, and the button reads "Booking…" or "Moving…" while it saves.
- The queue heading names the day when it is not today; the report fits at laptop width; the clock bar is compact on a phone.

Not done: no testing with real clinic staff, and no screen-reader walkthrough by a person (axe and keyboard checks only).
