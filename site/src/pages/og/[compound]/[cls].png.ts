// Share card per class page, generated at build time (brief §12.2): static, no runtime cost.
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import type { APIRoute, GetStaticPaths } from 'astro';
import opentype from 'opentype.js';
import sharp from 'sharp';
import type { ClassData, CompoundData } from '../../../lib/data';
import { compoundSlug, compounds, pageClasses, ukRanked } from '../../../lib/data';
import { doseLabel, formHeading, isoToLong, perDose } from '../../../lib/format';
import { site } from '../../../lib/site';

export const getStaticPaths: GetStaticPaths = () =>
  compounds.flatMap((data) =>
    pageClasses(data).map((cls) => ({
      params: { compound: compoundSlug(data.compound.id), cls: cls.slug },
      props: { data, cls },
    })),
  );

const escape = (text: string) => text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

// The image renderer only knows the build machine's system fonts, so the text is drawn as
// outlines of our own typeface (Red Hat Display, brief §12.4). Same card on every machine.
const require = createRequire(import.meta.url);
const loadFont = (weight: 400 | 700) => {
  const file = require.resolve(`@fontsource/red-hat-display/files/red-hat-display-latin-${weight}-normal.woff`);
  const bytes = readFileSync(file);
  return opentype.parse(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength));
};
const FONTS = { 400: loadFont(400), 700: loadFont(700) };

function line(text: string, x: number, y: number, size: number, weight: 400 | 700, fill: string): string {
  const font = FONTS[weight];
  const drawable = [...text].every((char) => font.charToGlyphIndex(char) !== 0 || char === ' ');
  if (!drawable) {
    // A character outside the bundled font: let the renderer fall back to a system font.
    return `<text x="${x}" y="${y}" font-size="${size}" font-weight="${weight}" fill="${fill}" font-family="DejaVu Sans, Segoe UI, Arial, sans-serif">${escape(text)}</text>`;
  }
  return `<path fill="${fill}" d="${font.getPath(text, x, y, size).toPathData(1)}"/>`;
}

export const GET: APIRoute = async ({ props }) => {
  const { data, cls } = props as { data: CompoundData; cls: ClassData };
  const c = data.compound;
  const heading = formHeading(c, cls);
  const from = ukRanked(cls)[0]?.price_per_std_dose ?? null;
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
  <rect width="1200" height="630" fill="#f4f5f8"/>
  <defs><clipPath id="pill"><rect x="960" y="85" width="160" height="70" rx="35"/></clipPath></defs>
  <g transform="rotate(-24 1040 120)"><g clip-path="url(#pill)"><rect x="960" y="85" width="80" height="70" fill="#ff5c4d"/><rect x="1040" y="85" width="80" height="70" fill="#0e5e6f"/></g></g>
  ${line(`Cheapest ${doseLabel(c, cls.standard_dose)} · UK`, 80, 150, 34, 400, '#5f5e70')}
  ${line(heading, 80, 260, heading.length > 28 ? 58 : 76, 700, '#1c1b29')}
  ${from !== null ? line(`from ${perDose(from)}`, 80, 400, 96, 700, '#0e5e6f') : ''}
  ${line(`${cls.ranked.length} products compared · prices checked ${isoToLong(data.generated_at)}`, 80, 480, 34, 400, '#5f5e70')}
  ${line(site.name.toLowerCase(), 80, 570, 40, 700, '#1c1b29')}
</svg>`;
  const png = await sharp(Buffer.from(svg)).png().toBuffer();
  return new Response(new Uint8Array(png), { headers: { 'Content-Type': 'image/png' } });
};
