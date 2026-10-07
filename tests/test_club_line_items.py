import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.services.club_assignment import parse_club_line_items
from backend.app.services.validation import ValidationError


def test_parse_club_line_items():
    text = (
        "Chargeback Dispute Process Testing | "
        "Chargeback Response Letter Template QA | "
        "Merchant Onboarding Workflow Testing"
    )
    items = parse_club_line_items(text)
    assert items == [
        "Chargeback Dispute Process Testing",
        "Chargeback Response Letter Template QA",
        "Merchant Onboarding Workflow Testing",
    ]


def test_parse_rejects_wrong_count():
    try:
        parse_club_line_items("Only one | Two")
        assert False, "expected ValidationError"
    except ValidationError as e:
        assert "exactly 3 items" in str(e)


if __name__ == "__main__":
    test_parse_club_line_items()
    test_parse_rejects_wrong_count()
    print("Club line-item parse tests passed.")
