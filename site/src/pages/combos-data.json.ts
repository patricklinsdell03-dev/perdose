// Data for the Combinations section (Patrick, 2026-09-18): every product that carries two or
// more of our compounds (or is a multivitamin), with each compound's amount per serving in
// that compound's unit, and one offer per retailer. Built from the same export as the tables.
import type { APIRoute } from 'astro';
import { meta, products, rules } from '../lib/data';

export const GET: APIRoute = () => {
  const units = Object.fromEntries(rules.map((c) => [c.id, c.unit]));
  const names = Object.fromEntries(rules.map((c) => [c.id, c.name]));
  const items = products()
    .map((product) => {
      const actives: Record<string, number> = {};
      const otherNames = new Set<string>();
      const offers = new Map<string, { retailer_id: string; ships_from: string; url: string; price_gbp: number; in_stock: boolean; servings: number | null }>();
      let multivitamin = false;
      for (const active of product.actives) {
        if (active.status === 'unverified') continue;
        const id = active.data.compound.id;
        if (id === 'multivitamin') multivitamin = true;
        for (const offer of active.offers) {
          if (offer.amount_per_serving !== null && id !== 'multivitamin') actives[id] = offer.amount_per_serving;
          for (const name of offer.other_actives) otherNames.add(name);
          if (!offers.has(offer.retailer_id)) {
            offers.set(offer.retailer_id, {
              retailer_id: offer.retailer_id,
              ships_from: offer.ships_from,
              url: offer.url,
              price_gbp: offer.price_gbp,
              in_stock: offer.in_stock,
              servings: offer.pack.servings,
            });
          }
        }
      }
      return {
        id: product.id,
        name: product.name,
        brand: product.brand,
        multivitamin,
        actives,
        other_names: [...otherNames].filter((n) => !(n in names)),
        offers: [...offers.values()].filter((o) => o.servings),
      };
    })
    .filter((p) => p.offers.length && (p.multivitamin || Object.keys(p.actives).length >= 2));
  const data = {
    generated_at: meta.generated_at,
    retailers: meta.retailers,
    compounds: rules.filter((c) => c.id !== 'multivitamin').map((c) => ({ id: c.id, name: c.name, unit: c.unit, standard_dose: c.standard_dose })),
    units,
    items,
  };
  return new Response(JSON.stringify(data), { headers: { 'Content-Type': 'application/json' } });
};
