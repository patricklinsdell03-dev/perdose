// Reads the pipeline's export (data/export/*.json) at build time. The site never computes a
// price from a label: every number here was computed in Python (CLAUDE.md rule 2).
import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { resolve } from 'node:path';

const EXPORT_DIR = resolve(process.cwd(), '../data/export');

export interface FormRule {
  id: string;
  names: string[];
  elemental_factor: number | null;
}

export interface ClassRule {
  id: string;
  label: string;
  slug: string;
  standard_dose: number;
  forms: FormRule[];
}

export interface CompoundRule {
  id: string;
  name: string;
  category: string;
  tier: number;
  comparison_quantity: string;
  unit: 'mg' | 'mcg' | 'IU';
  standard_dose: number;
  label_convention: 'elemental_default' | 'ambiguous' | 'compound_default';
  normalisation_type: string;
  aliases: string[];
  classes: ClassRule[];
}

export interface Offer {
  listing_id: string;
  product_id: string;
  brand: string | null;
  name: string;
  retailer_id: string;
  url: string;
  image_url: string | null;
  price_gbp: number;
  in_stock: boolean;
  price_date: string;
  pack: {
    units: number | null;
    unit_type: string | null;
    units_per_serving: number | null;
    multipack_count: number;
    servings: number | null;
  };
  form_id: string;
  amount_per_serving: number | null;
  amount_unit: string;
  amount_basis: string;
  is_primary: boolean;
  price_per_unit: number | null;
  price_per_std_dose: number | null;
  cost_per_month: number | null;
  days_supply: number | null;
  tested_flag: string | null;
  claimed: string[];
  other_actives: string[];
  review_reasons: { code: string; text: string }[];
  evidence: Record<string, string>;
  components: { name: string; amount: number; unit: string }[];
  branded_extract: string | null;
}

export interface ClassData {
  id: string;
  label: string;
  slug: string;
  standard_dose: number;
  ranked: Offer[];
  combinations: Offer[];
  unverified: Offer[];
}

export interface CompoundData {
  generated_at: string;
  compound: CompoundRule;
  classes: ClassData[];
}

export interface Meta {
  generated_at: string;
  retailers: { id: string; name: string; shipping: { rule: string; threshold_gbp?: number; flat_gbp?: number } }[];
  counts: { products: number; compounds: Record<string, number>; classes: Record<string, number> };
}

function read<T>(name: string): T {
  return JSON.parse(readFileSync(resolve(EXPORT_DIR, name), 'utf8')) as T;
}

export const rules: CompoundRule[] = read('compounds.json');
export const meta: Meta = read('meta.json');

const compoundDir = resolve(EXPORT_DIR, 'compounds');
export const compounds: CompoundData[] = (existsSync(compoundDir) ? readdirSync(compoundDir) : [])
  .filter((file) => file.endsWith('.json'))
  .map((file) => read<CompoundData>(`compounds/${file}`))
  .sort((a, b) => a.compound.name.localeCompare(b.compound.name));

/** URL segment for a compound: `vitamin_d3` -> `vitamin-d3`. */
export const compoundSlug = (id: string) => id.replaceAll('_', '-');

/** Classes that get their own page: at least one product, and a known form (brief §12.5). */
export const pageClasses = (data: CompoundData) =>
  data.classes.filter((cls) => cls.id !== 'unknown' && cls.ranked.length + cls.unverified.length > 0);

/** The class shown first on a compound page: the one with the most ranked products. */
export const defaultClass = (data: CompoundData) =>
  [...pageClasses(data)].sort((a, b) => b.ranked.length - a.ranked.length)[0];

export const retailerName = (id: string) => meta.retailers.find((r) => r.id === id)?.name ?? id;

export const CATEGORY_LABELS: Record<string, string> = {
  vitamins: 'Vitamins',
  minerals: 'Minerals',
  'amino-acids': 'Amino acids & derivatives',
  sports: 'Sports & performance',
  'fatty-acids': 'Fatty acids',
  botanicals: 'Botanicals & extracts',
  nootropics: 'Nootropic ingredients',
  'general-health': 'General health ingredients',
};

export interface ProductView {
  id: string;
  brand: string | null;
  name: string;
  image_url: string | null;
  /** One entry per compound the product carries, each with its offers. */
  actives: { data: CompoundData; cls: ClassData; status: 'ranked' | 'combination' | 'unverified'; offers: Offer[] }[];
}

/** Every product, gathered back together from the per-compound files (a D3+K2 product is in two). */
export function products(): ProductView[] {
  const byId = new Map<string, ProductView>();
  for (const data of compounds) {
    for (const cls of data.classes) {
      const groups = [
        ['ranked', cls.ranked],
        ['combination', cls.combinations],
        ['unverified', cls.unverified],
      ] as const;
      for (const [status, offers] of groups) {
        for (const offer of offers) {
          let product = byId.get(offer.product_id);
          if (!product) {
            product = { id: offer.product_id, brand: offer.brand, name: offer.name, image_url: offer.image_url, actives: [] };
            byId.set(offer.product_id, product);
          }
          let active = product.actives.find((a) => a.data === data && a.cls === cls && a.status === status);
          if (!active) {
            active = { data, cls, status, offers: [] };
            product.actives.push(active);
          }
          active.offers.push(offer);
        }
      }
    }
  }
  return [...byId.values()];
}
