# How to review a translation sheet

SchemeLogic's chat answers citizens in Hindi, Urdu, Marathi and Tamil. Most of that text was produced
by a machine. **Until a person has confirmed it, the app labels the language as "machine-translated, not
yet reviewed".** This sheet is how that confirmation happens.

## What to open

`docs/i18n/REVIEW_hi.csv`, and later `REVIEW_ur.csv`, `REVIEW_mr.csv` and `REVIEW_ta.csv`. Open it in
Excel or Google Sheets. It is UTF-8 and the scripts display correctly. Rows to translate by hand come
first, then rows that have a translation. Rows marked "not translated yet" are not ready, so skip them.

Work on a copy, or tell whoever maintains the repo before you start. The file is regenerated as new
translations arrive, but your four columns are kept.

## Rows marked TRANSLATE BY HAND (they come first)

The machine translation of these rows was rejected and is not used: the app shows the English
instead. Nobody will retry them by machine. Write the translation yourself in `corrected translation`,
set `reviewer verdict` to `FIX`, and add your name.

## For each row

| Column | Meaning |
|---|---|
| `where it appears` | Chat message, answer button, question to the citizen, eligibility result, screen text. |
| `English` | The original. This is what the app means. |
| `machine translation` | What the app shows now. Some screen-text rows are marked "hand-written"; review those the same way. |
| `automatic checks` | Problems a script found. Fix these first. |
| `English words kept` | English left in the translation. Sometimes correct (scheme names, "BPL", "Aadhaar"). Sometimes not ("Yes", "No"). |
| `pre-check note` | A machine's suggestion. It is **not** a review, so use your own judgement. |

Fill in:
- **`reviewer verdict (OK / FIX)`**: `OK` if the translation is right as it is; `FIX` if it needs changing.
- **`corrected translation`**: only for `FIX`. Write the whole corrected sentence.
- **`reviewer`**: your name or initials.
- **`comments`**: optional, anything others should know.

## What "right" means

1. **The meaning is exact.** Ages, amounts (₹), dates and conditions must match the English. A wrong
   number can tell someone they are eligible when they are not.
2. **Plain and polite**, the way a helpful government-office worker would speak to any citizen.
3. **Leave anything in `{curly braces}` exactly as it is**, for example `{scheme_id}` or `{question}`. The app
   fills these in. Keep `**` (bold markers) around the same words.
4. **Keep these terms in English as written:** BPL, APL, SC/ST, SC, ST, OBC, Group D, Class IV, MTS,
   Aadhaar, NRI, e-Shram, MGNREGA, NFSA, AAY, SECC, RSBY, Kisan Credit Card, HIV, AIDS, and scheme names
   (PM-KISAN, AB-PMJAY, PMAY-G, PMMVY, IGNOAPS). "pucca" and "kutcha" are ordinary words in Hindi and
   Marathi (पक्का, कच्चा) and in Urdu (پکا, کچا): write them in the language, in the right form (for
   example पक्की, कच्चे). In Tamil, keep them as written.
5. **Be consistent.** Translate the button words "Yes", "No" and "Prefer not to say" once (rows
   `reply.yes`, `reply.no`, `reply.decline`). Then use the same words wherever a message mentions those
   buttons. Pick one spelling (for example, के लिए and not के लिये) and use it throughout.

Start with the rows the app shows most: `reply.*`, `verdict.*`, `question.*`, `field.*`, then `chat.*`,
then the rest.

## When you're done

Send the sheet back. The maintainer applies it with:

```
PYTHONPATH=. python scripts/translate_catalogue.py --import-review hi docs/i18n/REVIEW_hi.csv
PYTHONPATH=. python scripts/export_ui_strings.py
```

- An `OK` row is stored as reviewed, but only if its translation hasn't changed since the sheet was made.
- A `FIX` row stores your correction as reviewed, if it passes the automatic checks. Corrections that
  fail (for example, a lost `{placeholder}`) are listed back to you.

A language's notice disappears from the app once **every** entry for it is reviewed.
