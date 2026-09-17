import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { parse } from 'yaml';

export interface SiteConfig {
  name: string;
  base_url: string;
  tagline: string;
  disclosure: string;
  contact_email: string;
}

// Builds always run from site/ (npm --prefix site, Cloudflare Pages), so the
// repo-level config is one directory up.
const path = resolve(process.cwd(), '../config/site.yml');

export const site: SiteConfig = parse(readFileSync(path, 'utf8'));
