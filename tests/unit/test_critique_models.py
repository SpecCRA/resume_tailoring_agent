import pydantic
import pytest

from resume_agent.models.critique import CritiqueResult, Finding


def test_critique_result_accepts_a_well_formed_response():
    result = CritiqueResult.model_validate(
        {
            "verdict": "flag",
            "findings": [{"severity": "high", "location": "Skills line", "note": "too dense"}],
        }
    )
    assert result.verdict == "flag"
    assert result.findings == [Finding(severity="high", location="Skills line", note="too dense")]


def test_critique_result_defaults_findings_to_empty_list():
    result = CritiqueResult.model_validate({"verdict": "pass"})
    assert result.findings == []


@pytest.mark.parametrize(
    "payload",
    [
        {"findings": []},  # missing verdict
        {"verdict": "maybe"},  # verdict outside the allowed literal values
        # finding missing "note"
        {"verdict": "flag", "findings": [{"severity": "high", "location": "x"}]},
        # severity outside the allowed literal values
        {"verdict": "flag", "findings": [{"severity": "critical", "location": "x", "note": "y"}]},
        {"verdict": "flag", "findings": "none"},  # findings not a list
    ],
)
def test_critique_result_rejects_malformed_responses(payload):
    with pytest.raises(pydantic.ValidationError):
        CritiqueResult.model_validate(payload)
