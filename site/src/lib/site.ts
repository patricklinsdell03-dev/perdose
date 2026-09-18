import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { parse } from 'yaml';

export interface SiteConfig {
  name: string;
  base_url: string;
  tagline: string;
  disclosure: string;
  contact_email: string;
  amazon_tag?: string;
}

/** Amazon search link for a product, carrying the Associates tag. Interim until the API
 * gives real Amazon rows; never styled as a buy button (brief v1.8). */
export const amazonSearchUrl = (name: string, brand: string | null): string | null =>
  site.amazon_tag
    ? `https://www.amazon.co.uk/s?k=${encodeURIComponent([brand, name].filter(Boolean).join(' '))}&tag=${site.amazon_tag}`
    : null;

// Builds always run from site/ (npm --prefix site, Cloudflare Pages), so the
// repo-level config is one directory up.
const path = resolve(process.cwd(), '../config/site.yml');

export const site: SiteConfig = parse(readFileSync(path, 'utf8'));
