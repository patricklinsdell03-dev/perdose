// Share card per class page, generated at build time (brief §12.2): static, no runtime cost.
import type { APIRoute, GetStaticPaths } from 'astro';
import sharp from 'sharp';
import type { ClassData, CompoundData } from '../../../lib/data';
import { compoundSlug, compounds, pageClasses } from '../../../lib/data';
import { doseLabel, isoToLong, perDose } from '../../../lib/format';
import { site } from '../../../lib/site';

export const getStaticPaths: GetStaticPaths = () =>
  compounds.flatMap((data) =>
    pageClasses(data).map((cls) => ({
      params: { compound: compoundSlug(data.compound.id), cls: cls.slug },
      props: { data, cls },
    })),
  );

const escape = (text: string) => text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

export const GET: APIRoute = async ({ props }) => {
  const { data, cls } = props as { data: CompoundData; cls: ClassData };
  const c = data.compound;
  const heading = cls.label.toLowerCase().includes(c.name.toLowerCase()) ? cls.label : `${c.name} — ${cls.label}`;
  const from = cls.ranked[0]?.price_per_std_dose ?? null;
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
  <rect width="1200" height="630" fill="#ffffff"/>
  <rect width="1200" height="14" fill="#0b6e4f"/>
  <g font-family="DejaVu Sans, Segoe UI, Arial, sans-serif" fill="#1a1d21">
    <text x="80" y="150" font-size="34" fill="#5c6670">Cheapest ${escape(doseLabel(c, cls.standard_dose))} · UK</text>
    <text x="80" y="260" font-size="${heading.length > 28 ? 58 : 76}" font-weight="700">${escape(heading)}</text>
    ${from !== null ? `<text x="80" y="400" font-size="96" font-weight="700" fill="#0b6e4f">from ${escape(perDose(from))}</text>` : ''}
    <text x="80" y="480" font-size="34" fill="#5c6670">${cls.ranked.length} products compared · prices checked ${escape(isoToLong(data.generated_at))}</text>
    <text x="80" y="570" font-size="40" font-weight="700">${escape(site.name)}</text>
  </g>
</svg>`;
  const png = await sharp(Buffer.from(svg)).png().toBuffer();
  return new Response(new Uint8Array(png), { headers: { 'Content-Type': 'image/png' } });
};
