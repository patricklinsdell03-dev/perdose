"""Brief §20.3: the grade is computed by rules, not by the AI. Readings here are invented."""

from pipeline.content.config import load_content_config
from pipeline.content.grade import GRADES, Reading, describe, grade, weighting_note

RULES = load_content_config().grading


def review(finding="favours_supplement", participants=None):
    return Reading(is_review=True, participants=participants, finding=finding)


def trial(finding="favours_supplement", participants=None):
    return Reading(is_review=False, participants=participants, finding=finding)


def test_one_trial_is_insufficient():
    assert grade([trial(participants=100)], RULES).grade == "Insufficient"
    assert grade([], RULES).grade == "Insufficient"


def test_unclear_findings_are_left_out():
    result = grade([review("unclear", 5000), trial(participants=50)], RULES)
    assert result.grade == "Insufficient" and result.reviews == 0


def test_disagreeing_reviews_are_mixed():
    result = grade([review(participants=2000), review("no_clear_difference", 3000)], RULES)
    assert result.grade == "Mixed"


def test_large_consistent_reviews_are_strong():
    readings = [review(participants=1500), review(participants=800), trial("mixed", 40)]
    result = grade(readings, RULES)
    # weights: 3 + 3 favour, 1 mixed -> 6/7 = 0.857 >= 0.8
    assert result.grade == "Strong" and result.leading_finding == "favours_supplement"
    assert result.participants == 1500 and result.reviews == 2 and result.trials == 1


def test_strong_evidence_of_no_difference_is_still_strong():
    readings = [review("no_clear_difference", 5000), review("no_clear_difference", 2000)]
    result = grade(readings, RULES)
    assert result.grade == "Strong" and result.leading_finding == "no_clear_difference"


def test_moderate_by_one_review_or_three_trials():
    assert grade([review(participants=400)], RULES).grade == "Moderate"
    trials = [trial(participants=150), trial(participants=150), trial(participants=100)]
    assert grade(trials, RULES).grade == "Moderate"


def test_small_consistent_evidence_is_limited():
    assert grade([trial(participants=30), trial(participants=30)], RULES).grade == "Limited"
    assert grade([review(participants=None)], RULES).grade == "Limited"  # size unknown


def test_two_thirds_agreement_is_the_line_for_mixed():
    agree = [trial(participants=200), trial(participants=200), trial("no_clear_difference", 200)]
    result = grade(agree, RULES)
    assert result.agree_share == 0.667 and result.grade == "Moderate"  # two of three agree
    split = [trial(participants=200), trial("no_clear_difference", 200)]
    assert grade(split, RULES).grade == "Mixed"


def test_every_grade_has_a_plain_english_rule():
    text = describe(RULES)
    assert list(text) == list(GRADES)
    assert "1,000 participants" in text["Strong"] and "80 %" in text["Strong"]
    assert "two-thirds" in text["Moderate"]
    assert "No meta-analysis or systematic review" in text["Insufficient"]
    assert "counts as 3 trials" in weighting_note(RULES)
