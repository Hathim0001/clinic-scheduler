# UI and UX audit

A page-by-page, component-by-component audit of the front end: every route at 1280, 768 and 390 px,
then scripted interaction tests in real Chrome. What was found, what was fixed, and what is left.

## How it was done

1. **A sweep of every route** (15 routes, 3 widths): console errors, failed requests, horizontal
   overflow, heading structure, duplicate ids, page titles, broken images, text under 13 px and
   touch targets under 40 px.
2. **A visual review** of a screenshot of every page at the three widths, against the checklist in
   the brief: hierarchy, spacing, alignment, consistency of buttons, cards, tables and icons.
3. **35 scripted interactions**: every menu link, back and forward, deep links and reloads, the phone
   menu (open, focus, Tab, Escape, tapping outside), free and booked slots, form validation, the
   cancel confirmation, rule validation, search, filters, quick ranges, the API being unreachable and
   keyboard focus.
4. **Automated accessibility** (axe-core) on every page at desktop and phone width.

## Found and fixed

| # | Defect | Fix |
|---|---|---|
| 1 | Filter bars (Day view, Queue, Report) had their controls pushed out of line: the rhythm rule that spaces the blocks of a card also offset the second and third control in a card that is itself a row | A card that is a row opts out; every control in a row has one height |
| 2 | The "My day" menu icon drew as a broken glyph | Replaced with a clean person icon |
| 3 | The open phone menu did not take focus, Tab wandered out into the page behind it, and focus was lost on closing | One focus-trap hook: focus moves in, Tab wraps, Escape closes, the page behind does not scroll, focus returns to the menu button |
| 4 | Dialogs (change password, hours conflict) had the same gaps | A shared `Modal` with the same behaviour, named for screen readers, closing on Escape or a click outside |
| 5 | Cancelling a visit opened a cramped panel inside a narrow table cell | It is now a proper dialog that names the patient and the time, with the choice and the two actions |
| 6 | Text quoted fixed numbers (30 days, 2 hours, 60 days, 30 minutes, a 9-minute undo timer) that an administrator can now change | The deposit rule, the late-move notice, the waitlist hold, the "too far ahead" message and the undo bar all read the clinic's own rules |
| 7 | Four pages had no tab title ("Clinic Scheduler" only), including the 404 | Every page has its own title; an unknown address says "Page not found" |
| 8 | The Calls, Messages and Staff tables inherited the Report's compact type, so text sizes differed from the Queue | Only the Report's table is compact |
| 9 | The "sign-in is off" notice was a full yellow block above every page title | One slim line across the top, labelled "Demo mode" |
| 10 | The queue repeated the same "why this button is off" sentence on every row, and the Doctor column wrapped | Kept for screen readers, not drawn on every row; the column no longer wraps; the action buttons get room for two to a line |
| 11 | On a phone, many controls were 25 to 38 px tall (clock controls, small buttons, link buttons, standalone links) | Controls are at least 44 px tall below 640 px; standalone links and checkboxes have bigger targets |
| 12 | The reviewer's test-clock strip took five rows of a phone screen | It folds behind one "Change the test clock" button |
| 13 | Avatar initials were 11 px | 13 px and above |
| 14 | "Remove this doctor" and "Erase this patient's data" looked like ordinary buttons | Destructive actions use the danger style |
| 15 | The Patients page was empty below the search box, and the privacy card had a button hanging off a sentence | A line says how to search; the sentence and its button are aligned, the destructive action is set apart |
| 16 | The 404 page offered a plain link that said "day view" and went elsewhere | A primary button to the overview |
| 17 | The report's tables forced a horizontal scroll on a tablet, and the Queue's six columns were squeezed there | Tables become one card per row up to 960 px |
| 18 | An input's focus ring depended on a transition, so it could appear a moment late | A solid outline plus a soft ring, immediately |

## Checked and fine

No console errors or failed requests on any route; every menu link opens its own page with exactly
one heading; back, forward, reload and deep links keep the chosen doctor, date and filters; garbage
in the address (a bad date, an unknown patient, bad booking ids) degrades to a clear message, never
a blank page; the API being unreachable shows an explanation and "Try again"; the book button stays
off until the form is complete and says what is missing; every focusable control has a visible focus
indicator; the first Tab lands on the skip link; no image or icon fails to load; the layout does not
shift while data loads (skeletons hold the space).

## Left alone, on purpose

- **Checkboxes and radio buttons are about 22 px** on a phone. Their label is the tap target and
  fills the row, which is the accepted pattern; the box itself is larger than the browser default.
- **Inline links inside sentences** are not given extra height (WCAG 2.2 exempts them).
- **The Staff table is not paginated.** A clinic has a handful of accounts; paging would add a control
  nobody needs.
- **There is one theme** (white). The dark colours are kept in the stylesheet but not switched on.
- **No real-device testing.** Everything above was checked in desktop Chrome at three widths and by
  axe-core. A real phone, Safari and a screen reader are still untried.
