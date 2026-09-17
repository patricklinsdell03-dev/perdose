// Smoke test on the built site (brief §15). Run after `astro build`.
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

const dist = new URL('../dist/', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1');
const failures = [];
const check = (ok, message) => ok || failures.push(message);

function htmlFiles(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return name === 'pagefind' ? [] : htmlFiles(path);
    return name.endsWith('.html') ? [path] : [];
  });
}

// 1. The prototype's definition of done: magnesium bisglycinate, ranked, from >= 2 retailers.
const page = join(dist, 'c/magnesium/bisglycinate/index.html');
check(existsSync(page), 'magnesium bisglycinate page was not built');
if (existsSync(page)) {
  const html = readFileSync(page, 'utf8');
  const retailers = new Set([...html.matchAll(/data-retailer="([^"]+)"/g)].map((m) => m[1]));
  check(retailers.size >= 2, `magnesium bisglycinate has ${retailers.size} retailer(s), needs 2`);
  check(/rel="sponsored nofollow noopener"/.test(html), 'outbound links are not marked sponsored');
  check(/Prices last checked/.test(html), 'no "prices last checked" date on the table');
}

// 2. Every page carries the affiliate disclosure and the not-medical-advice line (CLAUDE.md rule 4).
const files = htmlFiles(dist);
for (const file of files) {
  const html = readFileSync(file, 'utf8');
  check(html.includes('class="disclosure"'), `${file}: no disclosure line`);
  check(html.includes('Not medical advice'), `${file}: no medical-advice line`);
}

// 3. No health-claim wording in our own copy. Retailer wording never reaches a page except as
//    quoted label facts, so these should not appear anywhere.
const BANNED = [/\bcures?\b/i, /\btreats?\b/i, /\bprevents?\b/i, /\bboosts?\b/i, /clinically proven/i, /\bdetox/i, /immune support/i];
for (const file of files) {
  const text = readFileSync(file, 'utf8').replace(/<script[\s\S]*?<\/script>/g, '').replace(/<[^>]+>/g, ' ');
  for (const pattern of BANNED) check(!pattern.test(text), `${file}: banned wording ${pattern}`);
}

// 4. Search index and share images exist.
check(existsSync(join(dist, 'pagefind/pagefind-ui.js')), 'Pagefind index missing');
check(existsSync(join(dist, 'og/magnesium/bisglycinate.png')), 'share image missing');

if (failures.length) {
  console.error(`smoke: ${failures.length} problem(s)\n - ${failures.slice(0, 20).join('\n - ')}`);
  process.exit(1);
}
console.log(`smoke: ok (${files.length} pages)`);
