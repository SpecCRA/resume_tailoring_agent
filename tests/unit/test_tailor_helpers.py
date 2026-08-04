from resume_agent.pipelines.tailor import _ats_keyword_coverage, _keyword_alternatives


def test_ats_keyword_coverage_case_insensitive_substring_match():
    tailored_md = (
        "## Skills\nPython, kubernetes, AWS\n\n## Experience\n- Built pipelines on Databricks\n"
    )

    found, missing = _ats_keyword_coverage(tailored_md, ["Kubernetes", "AWS", "Airflow"])

    assert found == ["Kubernetes", "AWS"]
    assert missing == ["Airflow"]


def test_ats_keyword_coverage_preserves_input_order_and_handles_empty_list():
    found, missing = _ats_keyword_coverage("some resume text", [])

    assert found == []
    assert missing == []


def test_ats_keyword_coverage_matches_either_side_of_slash_alternation():
    tailored_md = "## Experience\n- Built ETL pipelines in Python\n"

    found, missing = _ats_keyword_coverage(tailored_md, ["ETL/ELT", "CI/CD"])

    assert found == ["ETL/ELT"]
    assert missing == ["CI/CD"]


def test_ats_keyword_coverage_matches_either_side_of_or_alternation():
    tailored_md = "## Skills\nApache Spark\n"

    found, missing = _ats_keyword_coverage(tailored_md, ["Spark or Flink"])

    assert found == ["Spark or Flink"]


def test_keyword_alternatives_splits_slash_and_or_joined_terms():
    assert _keyword_alternatives("ETL/ELT") == ["ETL", "ELT"]
    assert _keyword_alternatives("AWS/GCP/Azure") == ["AWS", "GCP", "Azure"]
    assert _keyword_alternatives("Spark or Flink") == ["Spark", "Flink"]


def test_keyword_alternatives_does_not_split_degenerate_short_pieces():
    # "A/B testing" would otherwise split into a bare, trivially-matching "A"
    assert _keyword_alternatives("A/B testing") == ["A/B testing"]


def test_keyword_alternatives_returns_unchanged_for_plain_keyword():
    assert _keyword_alternatives("Databricks") == ["Databricks"]
