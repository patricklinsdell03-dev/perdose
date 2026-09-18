// Compact data for the basket builder (brief v1.9): every ranked offer with what the client
// needs to price a basket, plus each retailer's delivery rule. Built at deploy time from the
// same export as the tables, so the two can never disagree.
import type { APIRoute } from 'astro';
import { compounds, meta, pageClasses } from '../lib/data';

export const GET: APIRoute = () => {
  const data = {
    generated_at: meta.generated_at,
    retailers: meta.retailers,
    compounds: compounds
      .map((d) => ({
        id: d.compound.id,
        name: d.compound.name,
        unit: d.compound.unit,
        standard_dose: d.compound.standard_dose,
        classes: pageClasses(d)
          .filter((cls) => cls.ranked.length > 0)
          .map((cls) => ({
            id: cls.id,
            label: cls.label,
            slug: cls.slug,
            standard_dose: cls.standard_dose,
            offers: cls.ranked
              .filter((o) => o.amount_per_serving && o.pack.servings && o.price_per_unit)
              .map((o) => ({
                id: o.listing_id,
                product_id: o.product_id,
                name: o.display_name,
                brand: o.brand,
                retailer_id: o.retailer_id,
                ships_from: o.ships_from,
                url: o.url,
                price_gbp: o.price_gbp,
                in_stock: o.in_stock,
                amount_per_serving: o.amount_per_serving,
                servings: o.pack.servings,
                unit: o.amount_unit,
              })),
          })),
      }))
      .filter((c) => c.classes.length > 0),
  };
  return new Response(JSON.stringify(data), { headers: { 'Content-Type': 'application/json' } });
};
