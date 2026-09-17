import type { APIRoute } from 'astro';
import { site } from '../lib/site';

export const GET: APIRoute = () => {
  const lines = ['User-agent: *', 'Allow: /', 'Disallow: /ops/'];
  if (site.base_url) lines.push(`Sitemap: ${new URL('/sitemap-index.xml', site.base_url).href}`);
  return new Response(`${lines.join('\n')}\n`, { headers: { 'Content-Type': 'text/plain' } });
};
