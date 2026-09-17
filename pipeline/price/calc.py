"""Price maths (brief §10). Pure functions; every number on a page comes from here.

All amounts are in the compound's base unit (mg, mcg or IU); `standard_dose` must be in the
same unit. Full precision is kept — rounding happens only at display time.
"""

from dataclasses import dataclass

DAYS_PER_MONTH = 30


def servings(pack_units: float, multipack_count: int, units_per_serving: float) -> float:
    if pack_units <= 0 or multipack_count <= 0 or units_per_serving <= 0:
        raise ValueError("pack_units, multipack_count and units_per_serving must be positive")
    return pack_units * multipack_count / units_per_serving


def total_quantity(servings: float, amount_per_serving: float) -> float:
    """Comparison quantity in the whole pack."""
    if servings <= 0 or amount_per_serving <= 0:
        raise ValueError("servings and amount_per_serving must be positive")
    return servings * amount_per_serving


def price_per_unit(price_gbp: float, total_quantity: float) -> float:
    """GBP per 1 mg / mcg / IU of the comparison quantity."""
    if price_gbp <= 0 or total_quantity <= 0:
        raise ValueError("price_gbp and total_quantity must be positive")
    return price_gbp / total_quantity


def price_per_std_dose(price_per_unit: float, standard_dose: float) -> float:
    if standard_dose <= 0:
        raise ValueError("standard_dose must be positive")
    return price_per_unit * standard_dose


def cost_per_month(price_per_std_dose: float) -> float:
    return price_per_std_dose * DAYS_PER_MONTH


def days_supply(total_quantity: float, standard_dose: float) -> float:
    if standard_dose <= 0:
        raise ValueError("standard_dose must be positive")
    return total_quantity / standard_dose


@dataclass(frozen=True)
class OfferPrice:
    """One row of the offer_prices table (§5.2), minus its keys."""

    price_per_unit: float
    price_per_std_dose: float
    cost_per_month: float
    days_supply: float


def price_offer(
    price_gbp: float, servings: float, amount_per_serving: float, standard_dose: float
) -> OfferPrice:
    total = total_quantity(servings, amount_per_serving)
    per_unit = price_per_unit(price_gbp, total)
    per_dose = price_per_std_dose(per_unit, standard_dose)
    return OfferPrice(
        price_per_unit=per_unit,
        price_per_std_dose=per_dose,
        cost_per_month=cost_per_month(per_dose),
        days_supply=days_supply(total, standard_dose),
    )
