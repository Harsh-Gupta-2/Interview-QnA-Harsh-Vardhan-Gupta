# Java Interview Handbook

Static site for GitHub Pages. `index.html` is the self-contained handbook.

Deploy: Settings > Pages > Deploy from branch > main / (root).

## Single source of truth

**Do not edit `index.html` by hand.** It is generated from:

| File | What it holds |
| --- | --- |
| `data/questions.csv` | Every question, one row each. **Edit this.** |
| `data/meta.json` | Sections (title, target), sources, resume triggers, company playbooks, page text. |
| `src/template.html` | Page layout, styles and script. |

Commit a change to any of these and the **Build site** GitHub Action validates
it, rebuilds `index.html`, commits it, and GitHub Pages publishes it (about 1–3
minutes). If the data is invalid the Action fails with the spreadsheet row
number, and the live site keeps the last good version.

To preview locally: `python build/build.py`, then open `index.html`.
`python build/build.py --check` only validates and reports whether `index.html` is stale.

## Editing questions.csv

Open it in Google Sheets, LibreOffice, or Excel (save as **CSV UTF-8**).
Row 1 is the header; keep the column names.

| Column | Format |
| --- | --- |
| `id` | `JH-S05-017`: the section (`S05`) comes from the id, so a new question in section 5 is `JH-S05-<next number>`. Must be unique. Changing an id resets its "practiced" tick. |
| `topic`, `question`, `answer`, `trap` | Text (required). |
| `level` | `L1`, `L2`, `L3` or `L4`. |
| `level_basis` | `est.` or `source`. |
| `round` | e.g. `Technical`, `Design`, `HR`, `Screening`, `Managerial`, `Machine-coding`. |
| `evidence` | `E0` (unverified pattern) to `E3`. |
| `frequency` | For `E0`: `est. very common`, `est. common` or `est. occasional`. Otherwise e.g. `seen in 2 sources`. |
| `harsh_status` | `UNTESTED`, `GAP`, `SHAKY` or `STRONG`. |
| `resume_hooks`, `company_types`, `keywords`, `verify` | Lists separated by ` \| `, e.g. `R:Java \| R:Spring`. May be empty. |
| `companies` | JSON, e.g. `[{"name": "Accolite", "sources": ["S010"], "year": null}]`. Sources must exist in `meta.json`. May be empty. |
| `followups` | JSON, e.g. `[{"q": "Why?", "a": "Because..."}]`. May be empty. |
| `notes` | Text, may be empty. |
| `code` | JSON object for an executed Java example, usually empty. |
| `fs_link` | Usually empty. |

Computed by the build (no column for them): `section`, `section_title`,
`hot_score` and `score_factors` (from the score rule in `meta.json`), the Hot
List, section counts, gap drills (`GAP`/`SHAKY` by topic), resume trigger
question lists, company coverage, source links and the question totals in the
scope notice.

## PDF

The PDF is not included: it must be regenerated with build/build-pdf.ps1 (needs Chrome on Windows).
