"""Deterministic post-rules (brief §9.5): Extraction -> NormalisedProduct.

Runs per active and dispatches on the compound's `normalisation_type` (§6.5); compound
specifics come from compounds.yml, never from special-case code here. Anything the label
leaves ambiguous becomes `needs_review` and is never ranked (CLAUDE.md rule 3).
"""

import re
from dataclasses import dataclass, field

from pipeline.compounds import Compound, Form, Registry
from pipeline.normalise.schema import ActiveExtraction, Extraction
from pipeline.price import calc

MCG_PER = {"mcg": 1.0, "mg": 1_000.0, "g": 1_000_000.0}
COUNTABLE_UNITS = {"capsule", "tablet", "softgel", "gummy", "sachet"}
SERVINGS_CONFLICT_TOLERANCE = 0.05
UNCLEAR_CONFIDENCE_CAP = 0.8
STATED_TOTAL_PENALTY = 0.2
ASSUMED_SERVING_PENALTY = 0.1
CONFIDENCE_FLOOR = 0.6
UNKNOWN = "unknown"


@dataclass
class ResolvedActive:
    """One row of product_actives (§5.2)."""

    compound_id: str
    form_id: str
    form_class: str
    amount_per_serving: float | None
    amount_unit: str
    amount_basis: str
    standard_dose: float
    is_primary: bool = False
    rank_eligible: bool = False
    review_reasons: list[str] = field(default_factory=list)


@dataclass
class NormalisedProduct:
    pack_units: int | None
    pack_unit_type: str | None
    units_per_serving: float | None
    multipack_count: int
    servings: float | None
    tested_flag: str | None
    multi_ingredient: bool
    other_actives: list[str]
    needs_review: bool
    review_reasons: list[str]
    confidence: float
    actives: list[ResolvedActive]

    @property
    def primary(self) -> ResolvedActive | None:
        return next((a for a in self.actives if a.is_primary), None)


# --- helpers ---------------------------------------------------------------------------


def convert_amount(amount: float, from_unit: str, compound: Compound) -> float | None:
    """Step 1: convert to the compound's own base unit. None if there is no valid route."""
    if from_unit == compound.unit:
        return amount
    iu_per_mcg = compound.unit_conversions.get("mcg_to_IU")
    if from_unit in MCG_PER:
        mcg = amount * MCG_PER[from_unit]
    elif from_unit == "IU" and iu_per_mcg:
        mcg = amount / iu_per_mcg
    else:
        return None
    if compound.unit in MCG_PER:
        return mcg / MCG_PER[compound.unit]
    return mcg * iu_per_mcg if iu_per_mcg else None


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _evidenced(evidence: dict[str, str], key: str, label_text: str | None) -> bool:
    """§9.3: a number without an evidence quote is discarded. If we have the label text,
    the quote must really occur in it."""
    quote = evidence.get(key)
    if not quote:
        return False
    return label_text is None or _squash(quote) in _squash(label_text)


def find_term(term: str, text: str) -> int | None:
    """Position of `term` in `text` as a whole word/phrase, else None."""
    match = re.search(rf"(?<![a-z0-9]){re.escape(term.lower())}(?![a-z0-9])", text.lower())
    return match.start() if match else None


@dataclass
class _Amount:
    value: float | None = None
    basis: str = "stated_elemental"
    reasons: list[str] = field(default_factory=list)
    confidence_cap: float = 1.0
    confidence_penalty: float = 0.0


def _stated_basis(compound: Compound) -> str:
    return (
        "stated_compound" if compound.label_convention == "compound_default" else "stated_elemental"
    )


def _component(active: ActiveExtraction, name: str, compound: Compound, label_text: str | None):
    """A named sub-amount in the compound's unit, if stated with evidence."""
    for comp in active.components:
        if comp.name.lower() == name.lower() and comp.unit != "percent":
            if _evidenced(active.evidence, comp.name, label_text):
                return convert_amount(comp.amount, comp.unit, compound)
    return None


# --- one resolver per normalisation type (§6.5) -------------------------------------------


def _mineral_elemental(active, amount, compound: Compound, form: Form | None, label_text):
    out = _Amount()
    if amount is None:
        return out

    def estimate():
        if form is None or form.elemental_factor is None:
            out.reasons.append("no_elemental_factor")
        else:
            out.value, out.basis = amount * form.elemental_factor, "estimated_from_compound"

    refers_to = active.amount_refers_to
    if refers_to == "elemental":
        out.value = amount
    elif refers_to == "compound":
        estimate()
    elif refers_to in ("unclear", None):
        if compound.label_convention == "elemental_default":
            out.value, out.confidence_cap = amount, UNCLEAR_CONFIDENCE_CAP
        elif compound.label_convention == "compound_default":
            estimate()
        else:
            rule = compound.heuristics.unclear_amount if compound.heuristics else None
            if (
                rule
                and form
                and form.id in rule.compound_forms
                and rule.compound_if_at_least is not None
                and amount >= rule.compound_if_at_least
            ):
                estimate()
            elif (
                rule
                and rule.elemental_if_at_most is not None
                and amount <= rule.elemental_if_at_most
            ):
                out.value = amount
            else:
                out.reasons.append("ambiguous_basis")
    else:
        out.reasons.append("ambiguous_basis")
    return out


def _stated_amount(active, amount, compound: Compound, form, label_text):
    """vitamin_unit and simple_mass: the stated amount of the active, already unit-converted."""
    out = _Amount(basis=_stated_basis(compound))
    if amount is None:
        return out
    out.value = amount
    if compound.label_convention == "compound_default":
        # "creatine 4.4 g (from 5 g monohydrate)": the compound mass is the convention.
        compound_mass = _component(active, "compound_mass", compound, label_text)
        if compound_mass is not None:
            out.value = compound_mass
    elif active.amount_refers_to in ("unclear", None):
        out.confidence_cap = UNCLEAR_CONFIDENCE_CAP
    return out


def _oil_components(active, amount, compound: Compound, form, label_text):
    out = _Amount(basis="stated_component_sum")
    parts = [_component(active, name, compound, label_text) for name in compound.components_sum]
    stated = [p for p in parts if p is not None]
    if stated:
        out.value = sum(stated)
        return out
    for name in ("total_omega_3", "omega_3_total", "total"):
        total = _component(active, name, compound, label_text)
        if total is not None:
            out.value, out.basis = total, "stated_total"
            out.confidence_penalty = STATED_TOTAL_PENALTY
            return out
    out.reasons.append("no_" + "_".join(n.lower() for n in compound.components_sum))
    return out


def _extract_standardised(active, amount, compound: Compound, form, label_text):
    out = _Amount(basis="stated_extract")
    # "5000 mg (from 500 mg 10:1 extract)": the extract mass wins over the herb equivalent.
    extract_mass = _component(active, "extract_mass", compound, label_text)
    if extract_mass is not None:
        out.value = extract_mass
    elif amount is not None and active.amount_refers_to in ("extract", "compound"):
        out.value = amount
    elif amount is not None:
        out.reasons.append("extract_basis_unclear")
    return out


RESOLVERS = {
    "mineral_elemental": _mineral_elemental,
    "vitamin_unit": _stated_amount,
    "simple_mass": _stated_amount,
    "oil_components": _oil_components,
    "extract_standardised": _extract_standardised,
}


# --- the pipeline -----------------------------------------------------------------------


def _resolve_form(active: ActiveExtraction, compound: Compound) -> Form | None:
    # A branded extract decides the class (KSM-66, Sensoril…), then the mapped id, then the words.
    return (
        compound.form_by_name(active.branded_extract)
        or compound.form(active.form_id)
        or compound.form_by_name(active.form_raw)
    )


def _resolve_active(active: ActiveExtraction, compound: Compound, label_text: str | None):
    form = _resolve_form(active, compound)
    reasons: list[str] = []
    if form is None:
        reasons.append("form_unknown")

    amount = None
    if active.amount_per_serving is not None and active.amount_unit:
        if _evidenced(active.evidence, "amount_per_serving", label_text):
            amount = convert_amount(active.amount_per_serving, active.amount_unit, compound)
            if amount is None:
                reasons.append("unit_not_convertible")

    result = RESOLVERS[compound.normalisation_type](active, amount, compound, form, label_text)
    reasons += result.reasons
    if result.value is None and not reasons:
        reasons.append("amount_missing")

    resolved = ResolvedActive(
        compound_id=compound.id,
        form_id=form.id if form else UNKNOWN,
        form_class=form.form_class if form else UNKNOWN,
        amount_per_serving=result.value,
        amount_unit=compound.unit,
        amount_basis=result.basis,
        standard_dose=compound.standard_dose_for(form),
        review_reasons=reasons,
    )
    return resolved, result


def _title_position(compound: Compound, title: str) -> int:
    found = (find_term(term, title) for term in [compound.name, *compound.aliases])
    return min((pos for pos in found if pos is not None), default=len(title) + 1)


def _is_accepted_cofactor(primary: Compound, other_names: list[str]) -> bool:
    return any(
        find_term(cofactor, name) is not None
        for cofactor in primary.accepted_cofactors
        for name in other_names
    )


def _tested_flag(claims: list[str]) -> str | None:
    if any(re.search(r"informed[\s-]?sport", c, re.IGNORECASE) for c in claims):
        return "informed_sport"
    return "third_party" if claims else None


def apply_rules(
    extraction: Extraction,
    registry: Registry,
    title: str = "",
    description: str = "",
    verify_quotes: bool = True,
) -> NormalisedProduct:
    """`verify_quotes` checks every evidence quote really occurs in the title/description."""
    label_text = f"{title}\n{description}" if verify_quotes else None
    reasons: list[str] = []
    confidence = extraction.confidence

    def kept(field_name: str):
        value = getattr(extraction, field_name)
        if value is not None and _evidenced(extraction.evidence, field_name, label_text):
            return value
        return None

    # Step 2: pack and servings.
    pack_units = kept("pack_units")
    multipack_count = kept("multipack_count") or 1
    servings_stated = kept("servings_stated")
    units_per_serving = kept("units_per_serving")
    if units_per_serving is None and extraction.pack_unit_type in COUNTABLE_UNITS:
        units_per_serving = 1.0  # prompt rule 4: assume one unit, with reduced confidence
        confidence -= ASSUMED_SERVING_PENALTY

    servings = None
    if pack_units and units_per_serving:
        servings = calc.servings(pack_units, multipack_count, units_per_serving)
        if servings_stated and abs(servings - servings_stated) / servings_stated > (
            SERVINGS_CONFLICT_TOLERANCE
        ):
            reasons.append("servings_conflict")
    elif servings_stated:
        servings = float(servings_stated)
    else:
        reasons.append("servings_unknown")

    # Steps 1 and 3-8: each active, by normalisation type.
    actives: list[ResolvedActive] = []
    compounds: dict[str, Compound] = {}
    for active in extraction.actives:
        compound = registry.get(active.compound_id)
        if compound is None or compound.id in compounds:
            continue
        compounds[compound.id] = compound
        resolved, result = _resolve_active(active, compound, label_text)
        confidence = min(confidence, result.confidence_cap) - result.confidence_penalty
        actives.append(resolved)

    # Step 9: primary by title order; combination unless the rest are accepted cofactors.
    multi_ingredient = False
    if actives:
        primary = min(actives, key=lambda a: _title_position(compounds[a.compound_id], title))
        primary.is_primary = True
        reasons += primary.review_reasons
        primary_compound = compounds[primary.compound_id]
        others = [
            [compounds[a.compound_id].name, *compounds[a.compound_id].aliases]
            for a in actives
            if a is not primary
        ] + [[name] for name in extraction.other_actives]
        multi_ingredient = any(not _is_accepted_cofactor(primary_compound, o) for o in others)
    else:
        reasons.append("no_active")

    # Step 11: confidence floor.
    confidence = max(confidence, 0.0)
    if confidence < CONFIDENCE_FLOOR:
        reasons.append("low_confidence")

    needs_review = bool(reasons)
    for active in actives:
        active.rank_eligible = (
            not needs_review and not active.review_reasons and active.amount_per_serving is not None
        )

    return NormalisedProduct(
        pack_units=pack_units,
        pack_unit_type=extraction.pack_unit_type,
        units_per_serving=units_per_serving,
        multipack_count=multipack_count,
        servings=servings,
        tested_flag=_tested_flag(extraction.tested_claims),
        multi_ingredient=multi_ingredient,
        other_actives=list(extraction.other_actives),
        needs_review=needs_review,
        review_reasons=list(dict.fromkeys(reasons)),
        confidence=confidence,
        actives=actives,
    )
