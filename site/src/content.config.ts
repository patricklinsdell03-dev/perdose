// Learn pages (brief §20). Only pages that `make content-check` listed in data/export/learn.json
// are loaded, and only if the file still matches the fingerprint taken when it was checked:
// the deploy runs this build alone (no Python), so an unchecked edit must not slip through.
// Drafts never enter the site.
import { createHash } from 'node:crypto';
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { defineCollection } from 'astro:content';
import { z } from 'astro/zod';
import { parse } from 'yaml';

// Builds always run from site/. The two overrides exist only to test the route locally.
const MANIFEST = resolve(process.cwd(), process.env.PERDOSE_LEARN_MANIFEST ?? '../data/export/learn.json');
const CONTENT_DIR = resolve(process.cwd(), process.env.PERDOSE_CONTENT_DIR ?? '../content');

const normalise = (text: string) => text.replace(/^﻿/, '').replace(/\r\n/g, '\n');
const fingerprint = (text: string) => createHash('sha256').update(normalise(text), 'utf8').digest('hex');

interface ManifestPage {
  compound_id: string;
  sha256: string;
}

const learn = defineCollection({
  loader: {
    name: 'approved-learn-pages',
    load: async ({ store, parseData, renderMarkdown, logger }) => {
      store.clear();
      if (!existsSync(MANIFEST)) return;
      const pages: ManifestPage[] = JSON.parse(readFileSync(MANIFEST, 'utf8')).pages ?? [];
      for (const page of pages) {
        const path = resolve(CONTENT_DIR, page.compound_id, 'learn.md');
        const text = existsSync(path) ? readFileSync(path, 'utf8') : null;
        if (text === null || fingerprint(text) !== page.sha256) {
          logger.warn(`${page.compound_id}: learn.md is missing or changed since make content-check; not published`);
          continue;
        }
        const match = /^---\n([\s\S]*?)\n---\n([\s\S]*)$/.exec(normalise(text));
        if (!match) continue;
        const data = await parseData({ id: page.compound_id, data: parse(match[1]) });
        store.set({ id: page.compound_id, data, body: match[2], rendered: await renderMarkdown(match[2]) });
      }
    },
  },
  schema: z.object({
    compound_id: z.string(),
    review_status: z.literal('approved'),
    reviewed_on: z.coerce.string(),
    generated_at: z.coerce.string(),
    content_version: z.number(),
    at_a_glance: z.string().optional(),
  }),
});

export const collections = { learn };
