from resume_agent.tools.usage_log import append_usage_log


def test_append_usage_log_migrates_a_header_from_before_a_column_was_added(
    tmp_path, monkeypatch
):
    from resume_agent.config import settings

    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    log_path = tmp_path / "usage_log.csv"
    log_path.write_text(
        "date,company,role,verdict,screening_fit_score,final_fit_score,"
        "ats_keywords_found,ats_keywords_total,remaining_gaps,low_relevance_bullets\n"
        "2026-01-01,Acme,Engineer,APPLY,0.5,0.6,1,2,0,0\n"
    )

    append_usage_log(
        {
            "date": "2026-01-02",
            "company": "Other Co",
            "role": "Scientist",
            "verdict": "APPLY",
            "screening_fit_score": 0.7,
            "final_fit_score": 0.8,
            "ats_keywords_found": 2,
            "ats_keywords_total": 2,
            "remaining_gaps": 0,
            "low_relevance_bullets": 0,
            "refine_rounds": 1,
        }
    )

    rows = log_path.read_text().splitlines()
    assert rows[0].endswith(",refine_rounds")
    assert rows[1].startswith("2026-01-01,Acme,Engineer,APPLY,0.5,0.6,1,2,0,0,")
    assert rows[1].endswith(",")  # old row backfilled with a blank, not dropped
    assert rows[2].endswith(",1")  # new row's actual refine_rounds value


def test_append_usage_log_writes_header_once_on_a_fresh_file(tmp_path, monkeypatch):
    from resume_agent.config import settings

    monkeypatch.setattr(settings, "data_dir", str(tmp_path))

    append_usage_log(
        {
            "date": "2026-01-01",
            "company": "Acme",
            "role": "Engineer",
            "verdict": "PASS",
            "screening_fit_score": 0.1,
            "final_fit_score": "",
            "ats_keywords_found": "",
            "ats_keywords_total": "",
            "remaining_gaps": "",
            "low_relevance_bullets": "",
            "refine_rounds": "",
        }
    )
    append_usage_log(
        {
            "date": "2026-01-02",
            "company": "Other Co",
            "role": "Scientist",
            "verdict": "APPLY",
            "screening_fit_score": 0.7,
            "final_fit_score": 0.8,
            "ats_keywords_found": 2,
            "ats_keywords_total": 2,
            "remaining_gaps": 0,
            "low_relevance_bullets": 0,
            "refine_rounds": 1,
        }
    )

    rows = (tmp_path / "usage_log.csv").read_text().splitlines()
    assert len(rows) == 3  # one header + two data rows, header not repeated
    assert rows[0].startswith("date,company,role,verdict")
