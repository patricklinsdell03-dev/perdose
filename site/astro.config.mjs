import { readFileSync } from 'node:fs';
import sitemap from '@astrojs/sitemap';
import { defineConfig } from 'astro/config';
import { parse } from 'yaml';

// Site name and URL live only in config/site.yml (CLAUDE.md).
const siteConfig = parse(readFileSync(new URL('../config/site.yml', import.meta.url), 'utf8'));

export default defineConfig({
  output: 'static',
  site: siteConfig.base_url || undefined,
  trailingSlash: 'always',
  // A sitemap needs absolute URLs, so it is only built once base_url is set in config/site.yml.
  integrations: siteConfig.base_url ? [sitemap({ filter: (page) => !page.includes('/ops/') })] : [],
});
