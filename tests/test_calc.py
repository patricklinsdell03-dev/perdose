"""Every formula in brief §10, with hand-checked numbers."""

import pytest

from pipeline.price import calc


def test_servings():
    assert calc.servings(180, 1, 2) == 90
    assert calc.servings(90, 3, 1) == 270  # multipack
    assert calc.servings(200, 1, 4) == 50  # 200 g powder, 4 g serving


def test_total_quantity():
    assert calc.total_quantity(90, 200) == 18_000


def test_price_per_unit():
    assert calc.price_per_unit(14.99, 18_000) == pytest.approx(0.000832778, rel=1e-5)


def test_price_per_std_dose():
    assert calc.price_per_std_dose(0.000832778, 100) == pytest.approx(0.0832778, rel=1e-5)


def test_cost_per_month():
    assert calc.cost_per_month(0.0832778) == pytest.approx(2.498333, rel=1e-5)


def test_days_supply():
    assert calc.days_supply(18_000, 100) == 180


def test_worked_example_from_brief():
    # Magnesium bisglycinate, £14.99, 180 capsules, 2 per serving, 200 mg magnesium per serving.
    n = calc.servings(180, 1, 2)
    result = calc.price_offer(14.99, n, 200, standard_dose=100)
    assert n == 90
    assert result.price_per_unit == pytest.approx(0.000833, abs=5e-7)
    assert result.price_per_std_dose == pytest.approx(0.0833, abs=5e-5)
    assert round(result.cost_per_month, 2) == 2.50
    assert result.days_supply == 180


def test_iu_compound():
    # Vitamin D3 4000 IU x 365 softgels at £9.99, standard dose 1000 IU.
    result = calc.price_offer(9.99, 365, 4000, standard_dose=1000)
    assert result.price_per_std_dose == pytest.approx(9.99 / 1460, rel=1e-9)
    assert result.days_supply == 1460


def test_mcg_compound_with_class_dose_override():
    # K2 MK-4 5 mg = 5000 mcg x 60 capsules at £12.00, class dose 5000 mcg.
    result = calc.price_offer(12.00, 60, 5000, standard_dose=5000)
    assert result.price_per_std_dose == pytest.approx(0.20)
    assert result.cost_per_month == pytest.approx(6.00)


def test_creatine_per_5g_is_price_per_kg_times_five():
    # 1 kg tub, 3 g scoop: the scoop size must not change the per-5 g price.
    result = calc.price_offer(20.00, calc.servings(1000, 1, 3), 3000, standard_dose=5000)
    assert result.price_per_std_dose == pytest.approx(20.00 / 1000 * 5)


@pytest.mark.parametrize(
    "args",
    [(0, 90, 200, 100), (14.99, 0, 200, 100), (14.99, 90, 0, 100), (14.99, 90, 200, 0)],
)
def test_non_positive_inputs_raise(args):
    with pytest.raises(ValueError):
        calc.price_offer(*args)


def test_servings_rejects_zero_units_per_serving():
    with pytest.raises(ValueError):
        calc.servings(180, 1, 0)
