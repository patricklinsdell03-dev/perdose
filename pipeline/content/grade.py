"""The evidence grade on a learn-page research card (brief §20.3): decided here, never by the AI.

The AI reads each study (is it a review or a trial, how many took part, what it found); these
rules turn the readings for one topic into Strong / Moderate / Limited / Mixed / Insufficient.
The numbers live in config/content.yml and the same wording is shown on the methodology page.

A grade says how settled the finding is, whichever way it points: consistent large reviews
finding no clear difference grade Strong, and the card says "no clear difference".
"""

from dataclasses import dataclass

from pipeline.content.config import GradingConfig

GRADES = ("Strong", "Moderate", "Limited", "Mixed", "Insufficient")
# What a study found, relative to what it compared against (placebo, no supplement).
DIRECTIONS = ("favours_supplement", "no_clear_difference", "favours_control")
FINDINGS = (*DIRECTIONS, "mixed", "unclear")


@dataclass(frozen=True)
class Reading:
    """One relevant study, as the rubric sees it."""

    is_review: bool  # meta-analysis or systematic review
    participants: int | None
    finding: str  # one of FINDINGS


@dataclass(frozen=True)
class Grade:
    grade: str
    leading_finding: str | None  # the direction most of the weight points, if any
    agree_share: float  # that direction's share of the weight
    reviews: int
    trials: int
    participants: int | None  # the largest review, or all trials added up, if stated


def grade(readings: list[Reading], rules: GradingConfig) -> Grade:
    counted = [r for r in readings if r.finding != "unclear"]
    reviews = sum(1 for r in counted if r.is_review)
    trials = len(counted) - reviews
    in_reviews = [r.participants for r in counted if r.is_review and r.participants]
    in_trials = [r.participants for r in counted if not r.is_review and r.participants]
    sizes = [max(in_reviews, default=0), sum(in_trials)]
    participants = max(sizes) if any(sizes) else None

    weights = dict.fromkeys(DIRECTIONS, 0.0)
    total = 0.0
    for reading in counted:
        weight = rules.review_weight if reading.is_review else rules.trial_weight
        total += weight
        if reading.finding in weights:
            weights[reading.finding] += weight
    leading = max(DIRECTIONS, key=lambda d: weights[d]) if total else None
    share = weights[leading] / total if leading and weights[leading] else 0.0

    def result(name: str) -> Grade:
        direction = leading if share else None
        return Grade(name, direction, round(share, 3), reviews, trials, participants)

    low = rules.insufficient_below
    if reviews < low.reviews and trials < low.trials:
        return result("Insufficient")
    if share < rules.agree_share:
        return result("Mixed")
    size = participants or 0
    strong, moderate = rules.strong, rules.moderate
    if reviews >= strong.reviews and size >= strong.participants and share >= strong.agree_share:
        return result("Strong")
    if (reviews >= moderate.reviews or trials >= moderate.trials_instead) and (
        size >= moderate.participants
    ):
        return result("Moderate")
    return result("Limited")


def _pct(share: float) -> str:
    return "two-thirds" if abs(share - 2 / 3) < 0.01 else f"{round(share * 100)} %"


def describe(rules: GradingConfig) -> dict[str, str]:
    """Plain-English rule for each grade, from the configured numbers (methodology page)."""
    s, m, low = rules.strong, rules.moderate, rules.insufficient_below
    too_few_reviews = (
        "No meta-analysis or systematic review"
        if low.reviews == 1
        else f"Fewer than {low.reviews} meta-analyses or systematic reviews"
    )
    return {
        "Strong": (
            f"At least {s.reviews} meta-analyses or systematic reviews, the largest (or all the "
            f"trials together) covering at least {s.participants:,} participants, and at least "
            f"{_pct(s.agree_share)} of the evidence pointing the same way."
        ),
        "Moderate": (
            f"At least {m.reviews} meta-analysis or systematic review, or at least "
            f"{m.trials_instead} randomised trials, covering at least {m.participants:,} "
            f"participants, with at least {_pct(rules.agree_share)} of the evidence pointing "
            "the same way."
        ),
        "Limited": (
            f"At least {_pct(rules.agree_share)} of the evidence points the same way, but there "
            "are too few or too small studies for Moderate."
        ),
        "Mixed": (
            f"The studies point different ways: no finding carries {_pct(rules.agree_share)} "
            "of the evidence."
        ),
        "Insufficient": (
            f"{too_few_reviews} and fewer than {low.trials} randomised trials, or the studies "
            "do not say clearly what they found."
        ),
    }


WEIGHTING = (
    "Each meta-analysis or systematic review counts as {review} trials when we weigh which way "
    "the evidence points. Studies whose abstract does not say clearly what they found are left "
    "out. A grade says how settled a finding is, whichever way it points: consistent reviews "
    "that found no clear difference can grade Strong."
)


def weighting_note(rules: GradingConfig) -> str:
    review = rules.review_weight / rules.trial_weight
    return WEIGHTING.format(review=f"{review:g}")


CONFIDENCE = {
    "Strong": "Several reviews of trials, covering many people, broadly agree.",
    "Moderate": "A reasonable body of trial evidence, mostly pointing the same way.",
    "Limited": "Mostly pointing one way, but from few or small studies.",
    "Mixed": "The studies disagree, so no firm conclusion can be drawn.",
    "Insufficient": "Too few clear studies to draw any conclusion.",
}
