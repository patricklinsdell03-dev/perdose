"""The normaliser prompt (brief Appendix C) and the per-listing user message.

Any change to SYSTEM_PROMPT or to how the user message is built must bump `prompt_version`
in config/llm.yml, so cached extractions are redone (brief §9.4).
"""

from pipeline.compounds import Compound, Registry
from pipeline.normalise.rules import find_term

MAX_CANDIDATES = 8
SECTION_KEYWORDS = ("per serving", "ingredients", "nutritional information")

SYSTEM_PROMPT = """\
You extract structured facts from UK supplement product listings. You never estimate,
never compute prices, and never add information that is not in the text.

Input: a product title and description from a retailer. Output: a single JSON object
matching the provided schema. Rules:

1. actives: one entry for EVERY candidate compound (the user message lists the
   candidates, at most 8) that is present as an active in this product. Fill each
   entry's compound_id, form_raw, form_id, amount_per_serving, amount_unit,
   amount_refers_to, components, extract_ratio, branded_extract and evidence.
   If none of the candidates is present, actives is an empty list. A multivitamin
   or a broad blend still gets an entry per candidate it contains.
2. form_raw: copy the form words exactly as written (e.g. "bisglycinate", "MK-7",
   "KSM-66", "ethyl ester"). form_id: map to the closest id from that compound's
   form list supplied in the user message; null if unsure.
   is_single_ingredient: true only when exactly one active is present, counting
   candidates and other_actives together.
3. pack_units / pack_unit_type: the count of capsules, tablets, softgels, gummies,
   sachets, or grams/ml for powders and liquids (write "1kg" as 1000 grams). For
   "3 x 90 tablets" set pack_units 90 and multipack_count 3.
4. units_per_serving: how many units the label says make one serving ("2 capsules
   provide", "5g scoop", "5ml"). If not stated, leave it null.
5. amount_per_serving + amount_unit: the headline amount per serving of that active,
   in the unit written on the label. Do not convert units. amount_refers_to:
   - "elemental" if the text says providing/elemental/as <mineral>/NRV or gives
     the mineral amount separately from the compound mass;
   - "compound" if the number is clearly the salt/chelate mass (e.g. "magnesium
     bisglycinate 2000mg" with a separate "providing 200mg magnesium" -> put 200 in
     amount_per_serving as elemental and 2000 in components as "compound_mass");
   - "total_oil" for fish/krill/algae oil mass;
   - "extract" for herbal extract mass;
   - "unclear" if you cannot tell. Do not guess. A bare number after a mineral salt
     name ("Magnesium Citrate 200mg") with no cue words is "unclear".
6. components: every sub-amount stated, with these names: "EPA", "DHA",
   "total_omega_3", "compound_mass", "extract_mass" (the mass of extract when the
   headline number is a herb equivalent, e.g. "5000mg from 500mg 10:1 extract" ->
   amount_per_serving 500 as extract, plus herb_equivalent 5000), "herb_equivalent",
   and the standardised constituent by name (e.g. "withanolides" with unit percent).
   Copy numbers exactly.
7. extract_ratio: e.g. "10:1" if stated. branded_extract: KSM-66, Sensoril, Shoden,
   Creapure, Magtein, Suntheanine, etc. if stated.
8. other_actives: every other active ingredient named (vitamin B6, black pepper,
   copper, vitamin K2 ...) that is not one of the candidates. Exclude excipients
   (cellulose, magnesium stearate, rice flour, capsule shell, silica).
9. tested_claims: copy testing/certification claims verbatim ("Informed Sport",
   "third-party tested"). Do not infer.
10. evidence: for every numeric field you fill, add an entry whose `field` is the
    field name (for a component, the component's name) and whose `quote` is the exact
    substring of the listing it came from, copied character for character. A number
    without evidence will be discarded.
11. confidence: 0-1 for the whole extraction. Below 0.7 means a human should look.
12. review_reasons: short phrases for anything odd (conflicting numbers, serving size
    missing, "buffered" chelate, marketing claims that contradict the label).
"""


def find_candidates(registry: Registry, title: str, description: str = "") -> list[Compound]:
    """Compounds whose name or an alias appears in the listing, earliest mention first,
    at most MAX_CANDIDATES (brief §21.2)."""
    text = f"{title}\n{description}".lower()
    found = []
    for compound in registry.compounds:
        positions = [
            pos
            for term in [compound.name, *compound.aliases]
            if (pos := find_term(term, text)) is not None
        ]
        if positions:
            found.append((min(positions), compound))
    return [compound for _pos, compound in sorted(found, key=lambda f: f[0])][:MAX_CANDIDATES]


def trim_description(description: str, max_chars: int) -> str:
    """Brief Appendix C: cap the description, keeping the nutrition/ingredients part."""
    if len(description) <= max_chars:
        return description
    lowered = description.lower()
    starts = [i for keyword in SECTION_KEYWORDS if (i := lowered.find(keyword)) >= 0]
    if not starts:
        return description[:max_chars]
    start = max(0, min(min(starts), len(description) - max_chars))
    return description[start : start + max_chars]


def build_user_message(
    candidates: list[Compound], title: str, description: str, max_chars: int
) -> str:
    lines = ["CANDIDATES:"]
    for compound in candidates:
        lines.append(f"- compound_id: {compound.id} ({compound.name})")
        for form in compound.forms:
            lines.append(f"    form_id: {form.id} - {', '.join(form.names)}")
    lines += ["", "TITLE:", title, "", "DESCRIPTION:", trim_description(description, max_chars)]
    return "\n".join(lines)
