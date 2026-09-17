import { readFileSync } from 'node:fs';
import { defineConfig } from 'astro/config';
import { parse } from 'yaml';

// Site name and URL live only in config/site.yml (CLAUDE.md).
const siteConfig = parse(readFileSync(new URL('../config/site.yml', import.meta.url), 'utf8'));

export default defineConfig({
  output: 'static',
  site: siteConfig.base_url || undefined,
});
