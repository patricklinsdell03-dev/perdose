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

## Healthspan (added later the same day)

`healthspan.csv` (28 rows), read from healthspan.co.uk product pages on 2026-09-17. Own-brand retailer (Healthspan and Healthspan Elite ranges). This brings the total to 99 rows.

- **price_gbp** — the "One-Time Purchase" price (the reduced price where one was showing). Never the "Subscribe & Save" price. Each price was cross-checked against the per-tablet price printed beside it.
- **merchant_pid** — Healthspan pages show no product code or barcode, so the page's URL slug is used as the id; `ean` is blank.
- **Pack size** — where a page offers two sizes, only the size shown as selected when the page opens is recorded (its price is the one displayed). Affects: Super Strength Vitamin D3 (240), Vitamin C 1000mg (320), Super Strength Omega 3 (120), High Strength Omega 3 (240). The other size is **not included**.
- **description** — directions, ingredients and the "Information table". Table rows are written `nutrient ; amount ; NN% NRV`; the page prints the NRV figure as a bare number under a "% NRV" heading. ® symbols and the allergen-advice sentence were dropped.
- **in_stock** — every page showed a live buy box with a price; none was marked out of stock.
- **Delivery** — a "free UK delivery on all orders, this week only" banner was showing. The standing rule shown is free over £30; the under-£30 charge was not displayed, so it is left out of `config/retailers.yml`.

## Multivitamins and three combinations (added 2026-09-18, Patrick's stopgap)

19 rows read from product pages on 2026-09-18, same conventions as above: Healthspan 6 (MultiVitality Gold / 50 Plus / 70 Plus / Vegetarians & Vegans / Pro, Elite Gold A-Z), Holland & Barrett 7 (ABC-Z Multivits, Ultra Man, Multivitamin Gummies, Vitabiotics Wellwoman 50+ sold by H&B, plus Calcium Magnesium Vitamin D & Zinc, High Strength Glucosamine & Chondroitin Complex, Omega 3 Fish Oil + D3), Bulk 6 (Multivitamin & Multimineral, Complete Multivitamin Complex 90 and 270, Vegan Multivitamin Complex, Multivitamin Gummies 60 and 120). Bulk pack sizes come from each variant's product code (`-0090` = 90), as before; Healthspan records the size selected when the page opens. Marketing and health-claim text on the pages was left out. Myprotein multivitamins were not collected. H&B's product pages publish their standard delivery charge (£3.49, 1–3 days) in their structured data, now in `config/retailers.yml`.

## Refreshing

Prices go stale. To refresh, re-read the same URLs and update `price_gbp`, `in_stock`, `captured_on`. Live affiliate feeds replace these files in Phase 6.
