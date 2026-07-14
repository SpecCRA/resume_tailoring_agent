resume-agent/
│
├── .python-version              # uv python pin 3.12
├── .env                         # gitignored — API keys
├── .env.example                 # committed — documents required vars
├── .gitignore
├── README.md
├── pyproject.toml
├── uv.lock
│
├── src/
│   └── resume_agent/
│       ├── __init__.py
│       ├── main.py              # CLI entrypoint (typer)
│       ├── config.py            # Settings (Pydantic)
│       │
│       ├── models/              # Pydantic data contracts
│       │   ├── __init__.py
│       │   ├── resume.py        # Resume, BulletPoint, ExperienceEntry
│       │   └── job.py           # JobDescription
│       │
│       ├── tools/               # Stateless, single-responsibility functions
│       │   ├── __init__.py
│       │   ├── pdf_reader.py        # PDF → raw text
│       │   ├── web_scraper.py       # URL → clean HTML text
│       │   ├── pdf_exporter.py      # Markdown → PDF via weasyprint
│       │   └── page_validator.py    # Count PDF pages
│       │
│       ├── prompts/             # LLM prompt builders
│       │   ├── __init__.py
│       │   ├── parse_resume.py
│       │   ├── rewrite_bullets.py
│       │   ├── extract_jd.py
│       │   ├── match_resume.py
│       │   └── tailor_resume.py
│       │
│       └── pipelines/           # Orchestration logic
│           ├── __init__.py
│           ├── setup.py         # One-time: PDF → base resume
│           └── tailor.py        # Per-job: URL + base → tailored PDF
│
├── data/
│   ├── input/                   # Drop source PDFs here
│   │   └── resume.pdf
│   ├── base/                    # Generated once by setup pipeline
│   │   └── resume_base.md
│   └── jobs/                    # One file per job application
│       └── discord-data-engineer-2024.md
│
├── output/                      # Tailored resumes (md + pdf)
│   ├── discord-data-engineer.md
│   └── discord-data-engineer.pdf
│
├── tests/
│   ├── conftest.py
│   ├── unit/
│   │   ├── test_pdf_reader.py
│   │   ├── test_web_scraper.py
│   │   ├── test_page_validator.py
│   │   └── test_prompts.py
│   └── integration/
│       └── test_pipelines.py
│
└── docs/
    ├── workflow.md
    └── prompt_design.md