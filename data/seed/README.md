# Seed data — provenance

Real listings read from the retailers' own public product pages on **2026-09-17** by Claude, one page at a time, at Patrick's instruction (docs/DECISIONS.md). 71 rows: `bulk.csv` (28), `myprotein.csv` (28), `holland_barrett.csv` (15). Columns follow brief Appendix D. Every row's `url` is the page it came from — spot-check any row by opening it.

Nothing is invented. Where a page did not show something, the field is blank.

## How each field was filled

- **price_gbp** — the current selling price on the page that day (the sale price where one was showing), not the struck-through "was" price. These retailers run near-permanent promotions; "effective price" handling is v1.1 (brief §19).
- **ean / merchant_pid** — from the page's embedded product data (Bulk, Myprotein: one code, barcode and price per pack size). H&B pages show an H&B SKU but no barcode, so `ean` is blank there.
- **title** — the page's product name plus the pack-size label of that variant, e.g. `Magnesium Bisglycinate Tablets - 180 Tablets`.
- **description** — only the factual label sections: directions, ingredients, the nutrition table (table rows shown as `[cell ; cell]`), and H&B's short "Benefits" bullets where they state an amount. Marketing copy, health-claim sentences, storage/allergen warnings and customer reviews were left out.
- **in_stock** — all 71 were in stock.

## Inferences (the only places a value was not literally printed next to its label)

1. **Bulk Creatine Monohydrate Powder**: the page lists sizes 100g / 250g / 500g / 1kg and four product codes ending `-0100`, `-0250`, `-0500`, `-1000`. The 500g ↔ `-0500` ↔ £10.99 pairing was confirmed on the page; the other three are paired by the same code pattern (which holds for every other Bulk product, e.g. `-0180` = 180 Tablets).
2. **Myprotein** lists some variants' prices without size labels next to them. Paired by: the variant shown as selected (its id appears in the image URL) and, where only two sizes exist, the cheaper price belongs to the smaller pack. Affects: Essential Magnesium, Essential Omega-3, Vitamin D3 & K2, Vitamin C Capsules, Vitamin D3 Softgels (non-vegan sizes only — the three vegan sizes could not be paired, so they are **not included**), Impact Creatine (largest size recorded by its stated "294 Servings", not by weight).

## Refreshing

Prices go stale. To refresh, re-read the same URLs and update `price_gbp`, `in_stock`, `captured_on`. Live affiliate feeds replace these files in Phase 6.
