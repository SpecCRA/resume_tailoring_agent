"""Hand-built resume/JD fixtures for critique-persona evals — deliberately
self-contained rather than reusing the user's real (gitignored) `data/`, so
the eval suite is reproducible for anyone regardless of whose resume is on
disk. Each constant is documented with which persona it's for and exactly
what's been planted in it.
"""

JOB_DESCRIPTION = """# Data Engineer — Example Co

## Required Skills
- Python
- SQL
- Distributed data processing (Spark)

## Responsibilities
- Build and maintain batch data pipelines
- Improve reliability and runtime of existing data jobs
"""

# --- Integrity auditor fixtures --------------------------------------------

BASE_RESUME_ORIGINALS_ONLY = """# Alex Rivera

## Summary
Data engineer with 3 years of experience building automated data pipelines.

## Skills
Python, SQL, Docker, PostgreSQL

## Experience
### Data Engineer | Example Corp
*Jan 2021 - Present*

- Built automated ETL pipelines to process daily transaction data
- Reduced nightly batch processing time from 30 minutes to 2 minutes by
  rewriting a slow PostgreSQL query as a set-based operation
"""

CLEAN_TAILORED_RESUME = """# Alex Rivera

## Summary
Data engineer with 3 years of experience building automated data pipelines.

## Skills
Python, SQL, Docker, PostgreSQL

## Experience
### Data Engineer | Example Corp
*Jan 2021 - Present*

- Built automated ETL pipelines to process daily transaction data
- Reduced nightly batch processing time from 30 minutes to 2 minutes by
  rewriting a slow PostgreSQL query as a set-based operation
"""

# Two distinct planted fabrications versus BASE_RESUME_ORIGINALS_ONLY: a tool
# never mentioned in the base resume (Kubernetes), and an inflated, unsupported
# version of the one real metric the base resume gives (30 min -> 2 min becomes
# a fabricated "95% across 50 microservices" claim).
FABRICATED_TAILORED_RESUME = """# Alex Rivera

## Summary
Data engineer with 3 years of experience building automated, containerized
data pipelines on Kubernetes.

## Skills
Python, SQL, Docker, Kubernetes, PostgreSQL

## Experience
### Data Engineer | Example Corp
*Jan 2021 - Present*

- Built automated ETL pipelines on Kubernetes to process daily transaction data
- Reduced batch processing time by 95% across 50 microservices
"""

# A legitimate rewording per tailor_resume.py rule 4: the JD says "batch"
# processing, and this is genuinely the same work the base resume already
# describes as "automated ETL pipelines" — not a new claim. The auditor must
# NOT flag this.
LEGITIMATE_RELABEL_TAILORED_RESUME = """# Alex Rivera

## Summary
Data engineer with 3 years of experience building automated batch data
pipelines.

## Skills
Python, SQL, Docker, PostgreSQL

## Experience
### Data Engineer | Example Corp
*Jan 2021 - Present*

- Built automated batch data pipelines to process daily transaction data
- Reduced nightly batch processing time from 30 minutes to 2 minutes by
  rewriting a slow PostgreSQL query as a set-based operation
"""

# --- ATS parser fixtures ----------------------------------------------------

# Two planted structural hazards versus CLEAN_TAILORED_RESUME: a non-standard
# section header ("My Journey" instead of "Experience") and an ambiguous date
# ("Q3 2022" instead of a parseable Month Year format).
ATS_HAZARD_TAILORED_RESUME = """# Alex Rivera

## Summary
Data engineer with 3 years of experience building automated data pipelines.

## Skills
Python, SQL, Docker, PostgreSQL

## My Journey
### Data Engineer | Example Corp
*Q3 2022 - Present*

- Built automated ETL pipelines to process daily transaction data
- Reduced nightly batch processing time from 30 minutes to 2 minutes by
  rewriting a slow PostgreSQL query as a set-based operation
"""

# --- Recruiter fixtures -----------------------------------------------------

# Same two bullets, same role, differing only in which one leads. The Spark
# bullet is the one that matches JOB_DESCRIPTION's named required skill.
RECRUITER_STRONG_BULLET_FIRST = """# Alex Rivera

## Experience
### Data Engineer | Example Corp
*Jan 2021 - Present*

- Migrated batch jobs to Spark, cutting a nightly pipeline's runtime from 45
  minutes to 6 minutes
- Wrote internal documentation for the team's on-call runbook
"""

RECRUITER_STRONG_BULLET_LAST = """# Alex Rivera

## Experience
### Data Engineer | Example Corp
*Jan 2021 - Present*

- Wrote internal documentation for the team's on-call runbook
- Migrated batch jobs to Spark, cutting a nightly pipeline's runtime from 45
  minutes to 6 minutes
"""

# --- Hiring manager fixtures -------------------------------------------------

# One vague, buzzword-only bullet planted alongside one specific, quantified
# bullet — the persona should flag the former and not the latter.
VAGUE_BULLET_TAILORED_RESUME = """# Alex Rivera

## Experience
### Data Engineer | Example Corp
*Jan 2021 - Present*

- Helped improve team processes and collaborated closely with stakeholders
- Reduced data pipeline runtime from 45 minutes to 6 minutes by migrating
  batch jobs to Spark
"""

# --- Narrative coherence fixtures -------------------------------------------

# A tailored resume that validly drops one of three original projects (per
# tailor_resume.py rule 1's "select at most 2 projects" — an expected,
# legitimate omission), leaving two projects and a continuous, gap-free
# employment history. The persona should judge only what's in front of it and
# not invent a complaint about content it has no way of knowing existed.
NARRATIVE_RESUME_WITH_VALID_OMISSION = """# Alex Rivera

## Summary
Data engineer with 3 years of experience building automated data pipelines.

## Experience
### Data Engineer | Example Corp
*Jan 2021 - Present*

- Built automated ETL pipelines to process daily transaction data

### Data Analyst | Prior Co
*Jun 2019 - Dec 2020*

- Automated a weekly reporting process, cutting turnaround from two days to
  two hours

## Projects
### Pipeline Health Dashboard
- Built an internal dashboard tracking daily pipeline job success/failure rates

### Query Performance Audit
- Audited the team's slowest recurring queries and proposed indexing fixes
"""
