# Learn page review checklist (brief §20.4)

A learn page is drafted by `make content COMPOUND=<id>` and saved as
`content/<id>/learn.md` with `review_status: draft`. Nothing is published until a person has
worked through this list and approved it. Allow 30–45 minutes per page.

**Before the first page can be approved:** the evidence grading rules must be approved once
(`config/content.yml` → `grading` → `status: approved`). Until then `make content-check` refuses
every approved page. The rules are printed in `data/export/learn.json` and explained in
DECISIONS.md (2026-09-18).

## 1. Read the run's report

The run printed a list of "to fix before approval" items; the same list is saved as
`draft_problems` in `content/<id>/evidence.json`. Every item must be dealt with: edit the page
by hand, or redraft (`make content COMPOUND=<id>` again — saved AI answers are reused, so only
changed steps cost anything).

## 2. Check the words

- [ ] No treat / cure / prevent / boost language anywhere, including the `at_a_glance` summary
      at the top of the file. Findings are described as "trials measured … and found …", never
      as what the supplement does for the reader.
- [ ] Nothing reads as advice: no "you should", no recommended doses (doses appear only as
      what studies used).
- [ ] No brand, product, retailer or company names above "Compare prices".
- [ ] Every card's topic is an outcome ("Blood pressure", "Mood scores"), not a disease or a
      treatment.
- [ ] UK spelling; plain English a non-scientist can follow.
- [ ] The fixed line is present at the end of "Things to know": "If you take medication, are
      pregnant, or have a health condition, check with a pharmacist or GP first."

## 3. Check the facts against the sources

- [ ] Open two or three of the cited studies on PubMed (each citation is a link). Does the
      page describe what the study measured and found fairly — not stronger, not weaker?
- [ ] For each card, look at the topic in `evidence.json`: the grade shown on the page must be
      the `grade` there (the page and the file are written by the same code; a difference means
      someone edited the page by hand).
- [ ] "What it is" and "How it works" contain nothing that the cited studies do not support.
      Cut any sentence you are unsure of.
- [ ] The forms table: the "what's different" notes are simple facts; the percentages and
      "per serving" figures are filled in by the code from `config/compounds.yml` and our price
      data — leave those as they are.

## 4. The "What people report" section

For now every page carries the placeholder "No community discussions have been summarised for
this page yet." under the fixed anecdote heading. That is expected (DECISIONS.md 2026-09-18).

## 5. Approve

At the top of `learn.md`, change:

```
review_status: approved
reviewed_by: <your name>
reviewed_on: <today, YYYY-MM-DD>
```

Then `make check`. The content check must show the page as `PASS (approved)`; if it shows
`FAIL`, the reasons are listed and the page will not be published. Commit `content/<id>/` and
`data/export/learn.json` together, then push. The page appears at `/learn/<id>/` and its
summary on the supplement's price page.

**Editing an approved page later:** after any edit, run `make check` again and commit the
refreshed `data/export/learn.json`. The site only publishes a page whose text matches the
fingerprint recorded by the check, so an edit that was not re-checked simply stops that page
being published until it is.

## First page only

Brief §20.5: have one page read by a solicitor familiar with ASA/CAP rules and the Nutrition
and Health Claims rules before publishing the rest.
