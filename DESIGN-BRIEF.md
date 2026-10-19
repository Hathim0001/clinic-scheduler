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

- The five links used all day sat in the header and the rest in a "More" menu (replaced by the side navigation below).
- Appointment actions show only what is allowed, with one sentence on why the rest are not.
- The day view's side panel shows booked and free counts and a one-press "Book it" for the next free time until a booking is selected.
- The booking form says what pressing the button will do, or what is still missing, and the button reads "Booking…" or "Moving…" while it saves.
- The queue heading names the day when it is not today; the report fits at laptop width; the clock bar is compact on a phone.

Not done: no testing with real clinic staff, and no screen-reader walkthrough by a person (axe and keyboard checks only).

## Redesign: "linen and scrub", October 2026

The first design was a document with a header; a second pass made it a dark-sidebar dashboard, which
read as a generic SaaS kit (navy rail, teal accent, identical icon-and-number cards, all-caps labels).
This section replaces both, and the "serif and ink-green on chart paper" direction above. It was
written with the project's design skills (frontend-design, ui-ux-pro-max, uiux, uicolor, a11y).

- **Subject:** the reception desk of a small outpatient clinic. The job is to see the day, book, and
  check people in, calmly, many times an hour.
- **Palette (60-30-10):** linen seafoam page and white paper cards (60), sage for booked entries and
  free slots (30), hospital blue for the one primary action (10). A single marigold marks "now" and is
  used for nothing else. Neutrals lean a whisper toward seafoam and shadows are tinted blue, never
  pure black. Status is still words first; colour only helps.
- **Type:** Source Sans 3 (a humanist sans built for reading) for the working surface, and Fraunces in
  its "soft" setting for page titles and the day's figures: the calm of a printed patient leaflet.
  Both are bundled, so the content security policy and the no-third-party rule still hold. Labels are
  sentence case, not tracked capitals.
- **Navigation:** a light rail in the same paper as the cards (Schedule, Patients, Clinic), the current
  page in a soft blue pill, attention counts on Messages and Doctors, a drawer below 960 px. An
  "API reference" link opens the interactive Swagger page for administrators.
- **The memorable thing:** the *day ribbon* on the Overview. Each doctor's day is a strip with one cell
  per slot (filled booked, open free, hatched passed) and a marigold tick where now falls; the words
  beside it say the same ("8 of 24 slots booked, next free 10:00"). The day view carries the same
  marigold "Now" line through the appointment book.
- **Overview:** four figures on one sheet (not four boxes), the ribbons, the next visits, and a
  "Needs a look" list that reads "All clear" when it is.
- **Checks:** unit tests for the overview, the ribbon text and the navigation; the accessibility sweep
  covers the overview too (40 scans, light and dark, desktop and phone).
