// Display formatting only (brief §10: store full precision, round at display time).
import type { CompoundRule, Offer } from './data';

const UNIT_LABEL: Record<string, string> = { mg: 'mg', mcg: 'µg', IU: 'IU', serving: 'serving' };

/** 5000 mg -> "5 g"; 100 mcg -> "100 µg"; 1000 IU -> "1,000 IU". */
export function amount(value: number, unit: string): string {
  if (unit === 'mg' && value >= 1000) return `${trim(value / 1000)} g`;
  if (unit === 'mcg' && value >= 1000) return `${trim(value / 1000)} mg`;
  return `${trim(value)} ${UNIT_LABEL[unit] ?? unit}`;
}

function trim(value: number): string {
  return value.toLocaleString('en-GB', { maximumFractionDigits: value < 10 ? 2 : 1 });
}

/** "per 100 mg magnesium", "per 1,000 IU", "per 5 g". */
export function doseLabel(compound: CompoundRule, dose: number): string {
  if (compound.unit === 'serving') return dose === 1 ? 'per serving' : `per ${trim(dose)} servings`;
  const what = compound.comparison_quantity.replace(/^elemental /, '');
  const short = ['mineral_elemental', 'oil_components'].includes(compound.normalisation_type) ? ` ${what}` : '';
  return `per ${amount(dose, compound.unit)}${short}`;
}

/** "Calcium" -> "calcium", but "Vitamin D3", "MSM" and "L-theanine" keep their capitals. */
export const lowerFirst = (text: string) => (/^[A-Z][a-z]/.test(text) ? text[0].toLowerCase() + text.slice(1) : text);

// Forms whose label does not read well after the compound's name. Keyed by class id, which
// never changes (brief §5); the label itself stays as it is for tabs.
const FORM_HEADINGS: Record<string, string> = {
  col_bovine: 'Bovine collagen',
  col_marine: 'Marine collagen',
  col_other: 'Collagen (unspecified source)',
  b3_niacinamide: 'Niacinamide (vitamin B3)',
};

/** The name of one form's table: "Magnesium Bisglycinate (glycinate)", "Thiamine (vitamin B1)",
 * "Other forms of zinc". Used for page headings, titles and share cards. */
export function formHeading(compound: CompoundRule, cls: { id: string; label: string }): string {
  const { name } = compound;
  const { label } = cls;
  if (FORM_HEADINGS[cls.id]) return FORM_HEADINGS[cls.id];
  if (label.toLowerCase().includes(name.toLowerCase())) return label;
  if (name.toLowerCase().includes(label.toLowerCase())) return name;
  if (/^other forms\b/i.test(label)) return `Other forms of ${lowerFirst(name)}`;
  if (/^blends\b/i.test(label)) return `${name} ${lowerFirst(label)}`;
  return `${name} ${label}`;
}

/** Per-dose prices: 3 significant figures, never fewer than 2 decimals (£0.0833, £0.233, £2.23). */
export function perDose(value: number | null): string {
  if (value === null) return '—';
  const decimals = Math.min(4, Math.max(2, 2 - Math.floor(Math.log10(value))));
  return `£${value.toFixed(decimals)}`;
}

export const money = (value: number | null) => (value === null ? '—' : `£${value.toFixed(2)}`);

const UNIT_NAMES: Record<string, [string, string]> = {
  capsule: ['capsule', 'capsules'],
  tablet: ['tablet', 'tablets'],
  softgel: ['softgel', 'softgels'],
  gummy: ['gummy', 'gummies'],
  sachet: ['sachet', 'sachets'],
  drop: ['drop', 'drops'],
  gram: ['g', 'g'],
  ml: ['ml', 'ml'],
};

/** "180 tablets · 90 servings", "500 g · 100 servings", "3 × 90 tablets · 270 servings". */
export function pack(offer: Offer): string {
  const { units, unit_type, multipack_count, servings } = offer.pack;
  const parts: string[] = [];
  if (units && unit_type) {
    const [one, many] = UNIT_NAMES[unit_type] ?? [unit_type, unit_type];
    const size = unit_type === 'gram' && units >= 1000 ? `${trim(units / 1000)} kg` : `${units} ${units === 1 ? one : many}`;
    parts.push(multipack_count > 1 ? `${multipack_count} × ${size}` : size);
  }
  if (servings) parts.push(`${trim(Math.round(servings * 10) / 10)} servings`);
  return parts.join(' · ') || '—';
}

export function perServing(offer: Offer): string {
  if (offer.amount_per_serving === null) return '—';
  const text = amount(offer.amount_per_serving, offer.amount_unit);
  return offer.amount_basis === 'estimated_from_compound' ? `≈ ${text} (estimated)` : text;
}

export const BASIS_TEXT: Record<string, string> = {
  stated_elemental: 'stated on the label',
  stated_compound: 'stated on the label',
  stated_extract: 'extract weight stated on the label',
  stated_constituent: 'active constituent content stated on the label (or its stated percentage of the extract)',
  per_serving: 'priced per serving — compare what each serving contains before choosing',
  stated_component_sum: 'added up from the components stated on the label',
  stated_total: 'label gives only a total, not the individual components',
  estimated_from_compound: 'estimated from the compound weight using our conversion factor',
};

export function days(value: number | null): string {
  if (value === null) return '—';
  if (value >= 365) return `${trim(Math.round((value / 365) * 10) / 10)} years`;
  if (value >= 60) return `${Math.round(value / 30.4)} months`;
  return `${Math.round(value)} days`;
}

export function isoToLong(iso: string): string {
  return new Date(`${iso.slice(0, 10)}T12:00:00Z`).toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    timeZone: 'Europe/London',
  });
}

export function monthYear(iso: string): string {
  return new Date(`${iso.slice(0, 10)}T12:00:00Z`).toLocaleDateString('en-GB', {
    month: 'long',
    year: 'numeric',
    timeZone: 'Europe/London',
  });
}
