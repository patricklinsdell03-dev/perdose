// Learn pages (brief §20): the rubric and the approved pages written by `make content-check`
// to data/export/learn.json. The pages themselves load through src/content.config.ts.
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { type CollectionEntry, getCollection } from 'astro:content';

export interface Rubric {
  status: 'proposed' | 'approved';
  grades: Record<string, string>;
  weighting: string;
}

const path = resolve(process.cwd(), process.env.PERDOSE_LEARN_MANIFEST ?? '../data/export/learn.json');
const manifest: { rubric?: Rubric; pages?: { compound_id: string }[] } = existsSync(path)
  ? JSON.parse(readFileSync(path, 'utf8'))
  : {};

export const rubric: Rubric | null = manifest.rubric ?? null;

let pages: Promise<Map<string, CollectionEntry<'learn'>>> | undefined;

/** Approved learn pages whose text still matches what was checked, keyed by compound id.
 * With nothing approved the collection is not queried at all (Astro warns on empty ones). */
export function learnPages(): Promise<Map<string, CollectionEntry<'learn'>>> {
  if (!manifest.pages?.length) return Promise.resolve(new Map());
  pages ??= getCollection('learn').then((entries) => new Map(entries.map((entry) => [entry.id, entry])));
  return pages;
}
