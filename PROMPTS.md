# Prompt log

Every prompt given to an AI assistant while building this project, in order. The tool is Claude Code
(Anthropic) throughout. "Outcome" says what was done with the answer.

The entries before the repository existed (1 to 6) were drafted from the session transcript by the
assistant; the author should check them against what was actually typed.

| # | Date | Prompt | Outcome |
|---|---|---|---|
| 1 | 2026-10-17 | `logout` | Asked how to sign out; nothing built |
| 2 | 2026-10-17 | `F:\KJBN Labs Hackathon` | The assistant read both assignment PDFs and summarised Problem 2, the deliverables and the rubric; used as a reading aid |
| 3 | 2026-10-17 | The long planning brief "MASTER PROMPT: ANALYZE BOTH PDFS AND GENERATE AN IMPLEMENTATION-READY HACKATHON PLAN.MD" (full text: [docs/prompts/01-planning-brief.md](docs/prompts/01-planning-brief.md)) | Produced `plan.md` revision 1 and the first concurrency experiment; adopted after review |
| 4 | 2026-10-17 | `/effort` and `claude --model sonnet --effort max` (the second was typed into the chat by mistake) | Session settings; no code resulted |
| 5 | 2026-10-17 | `/model sonnet` | Session setting; no code resulted |
| 6 | 2026-10-17 | "now read through the plan file and make improvements for the plan.md file with the new model and effort" | Produced `plan.md` revision 2 and the evidence scripts that check its claims (schema, rules, hostile input, concurrency); adopted after review |
| 7 | 2026-10-17 | "start the implementation of the plan" | Started the implementation in this repository, milestone by milestone |
| 8 | 2026-10-17 | "github is Hathim0001" (reply to a question about which identity to commit under) | Commits use the repository-local identity `Hathim0001`; the machine's global git identity is not used |
| 9 | 2026-10-17 | `+` (sent while the React interface was being built) | Read as "keep going"; the work continued with the UI, its tests, Docker and CI |
| 10 | 2026-10-17 | "create a private repo in github" | Created the private repository `Hathim0001/clinic-scheduler` and added it as `origin`. Nothing was pushed. Installing the GitHub CLI with winget stalled on a Windows permission prompt, so a checksum-verified portable copy was used; the GitHub login (device code) was removed afterwards |
| 11 | 2026-10-17 | "Yes" (to "Want me to push `main` now?") | Pushed `main` to the private repository. The first attempt was refused because the temporary GitHub login lacked the `workflow` permission needed for `.github/workflows/ci.yml`; after a second approval the push succeeded and the first CI run passed (backend, frontend, secret scan, compose smoke test). The login was removed afterwards |

Automated notices in the session (a usage limit resetting, a background command finishing) are not
prompts and are not logged. The assistant also made some decisions on its own while implementing the
plan; they are visible as commits and, where they changed a rule or an assumption, in
[README section 8](README.md#8-business-rules-and-assumptions).
