"""Opt-in multi-perspective critique of an already-tailored resume — five
independent persona reviews (see `prompts/critique.py`) run concurrently against
`output/<slug>.md`, aggregated into `output/<slug>.critique.md`.

Distinct from `review_output.py` (tailor step 5, one holistic pass that runs
automatically on every `tailor` invocation): this is a separate `critique`
command you run only when you want the extra scrutiny, since five persona
calls per job is a meaningfully bigger LLM bill than the rest of the pipeline
combined, and the output is advisory — nothing here is ever written back into
the resume itself.

Runs on `settings.eval_model` rather than `settings.claude_model` — using a
different model than the one that wrote the tailored resume avoids the
evaluator sharing the generator's own blind spots.
"""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import anthropic
import pydantic
from rich import print as rprint
from slugify import slugify

from resume_agent.config import settings
from resume_agent.errors import InvalidSlugError, MarkdownFileNotFoundError
from resume_agent.models.critique import CritiqueResult
from resume_agent.pipelines.setup import _parse_base_md, _render_originals_only_md
from resume_agent.prompts.critique import PERSONAS, build
from resume_agent.tools.llm import call_llm_json


def run_critique(slug: str) -> Path:
    """
    Run all five critique personas against an already-tailored resume.
    Reads output/<slug>.md, data/jobs/<slug>.md, and the base resume; writes
    output/<slug>.critique.md. Returns the path to the written report.
    """
    if slug != slugify(slug):
        raise InvalidSlugError(
            f"{slug!r} doesn't look like a job slug produced by `tailor` (expected only "
            f"lowercase letters, numbers, and hyphens, e.g. {slugify(slug)!r}). Pass the "
            "<slug> from an existing output/<slug>.md, not a URL or a path."
        )

    output_dir = Path(settings.output_dir)
    tailored_path = output_dir / f"{slug}.md"
    if not tailored_path.is_file():
        raise MarkdownFileNotFoundError(
            f"No tailored resume found at {tailored_path} — run `tailor` for this job first."
        )
    jd_path = Path(settings.data_dir) / "jobs" / f"{slug}.md"
    if not jd_path.is_file():
        raise MarkdownFileNotFoundError(f"No job description found at {jd_path}")

    tailored_md = tailored_path.read_text()
    jd_md = jd_path.read_text()
    base_originals_only_md = _render_originals_only_md(
        _parse_base_md(Path(settings.base_resume_path).read_text())
    )

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    rprint(f"[bold]Running {len(PERSONAS)} critique personas on {settings.eval_model}...[/bold]")
    results = _run_personas_concurrently(client, tailored_md, jd_md, base_originals_only_md)

    report_path = output_dir / f"{slug}.critique.md"
    report_path.write_text(_render_critique_md(results))
    return report_path


def _run_one_persona(
    client: anthropic.Anthropic,
    persona_key: str,
    tailored_md: str,
    jd_md: str,
    base_originals_only_md: str,
) -> dict[str, Any]:
    persona = PERSONAS[persona_key]
    prompt = build(
        persona_key,
        tailored_md=tailored_md,
        jd_md=jd_md if persona.needs_jd else None,
        base_originals_only_md=base_originals_only_md if persona.needs_base_resume else None,
    )
    try:
        data = call_llm_json(
            client,
            system=persona.system,
            prompt=prompt,
            max_tokens=1536,
            model=settings.eval_model,
        )
        # Validate against the schema every persona is instructed to return
        # (`_SCHEMA_INSTRUCTIONS` in prompts/critique.py is only a request in
        # the prompt text, not an enforced contract) — a malformed response
        # becomes a caught, per-persona failure here instead of a bare
        # KeyError deep inside _render_critique_md once every persona's
        # results have already been gathered.
        result = CritiqueResult.model_validate(data)
        return {"persona": persona_key, "ok": True, **result.model_dump()}
    except pydantic.ValidationError as e:
        return {
            "persona": persona_key,
            "ok": False,
            "error": f"Response didn't match the expected schema: {e}",
        }
    except Exception as e:  # noqa: BLE001 - one persona's API/parsing failure
        # must not take down the other four; degrade to a reported failure.
        return {"persona": persona_key, "ok": False, "error": str(e)}


def _run_personas_concurrently(
    client: anthropic.Anthropic,
    tailored_md: str,
    jd_md: str,
    base_originals_only_md: str,
) -> list[dict[str, Any]]:
    """Run every persona in its own thread — each is a blocking HTTP call, and
    running five of them sequentially would take five times as long for no
    benefit, since the personas are fully independent of each other."""
    order = list(PERSONAS)
    with ThreadPoolExecutor(max_workers=len(order)) as pool:
        futures = [
            pool.submit(
                _run_one_persona, client, key, tailored_md, jd_md, base_originals_only_md
            )
            for key in order
        ]
        results = [f.result() for f in futures]
    return results


def _render_critique_md(results: list[dict[str, Any]]) -> str:
    lines = ["# Multi-Perspective Critique", ""]

    for r in results:
        persona = PERSONAS[r["persona"]]
        lines.append(f"## {persona.name}")
        if not r["ok"]:
            lines += [f"_Persona failed: {r['error']}_", ""]
            continue
        lines.append(f"Verdict: **{r.get('verdict', 'unknown')}**")
        lines.append("")
        findings = r.get("findings", [])
        if not findings:
            lines += ["No findings.", ""]
            continue
        for f in findings:
            lines.append(f"- [{f['severity']}] {f['location']}: {f['note']}")
        lines.append("")

    # A finding at the same location flagged by more than one persona is a
    # stronger signal than any single persona's opinion — surface it, but
    # don't try to auto-resolve conflicting opinions between personas.
    location_hits: dict[str, list[str]] = {}
    for r in results:
        if not r["ok"]:
            continue
        for f in r.get("findings", []):
            location_hits.setdefault(f["location"], []).append(r["persona"])
    agreements = {loc: keys for loc, keys in location_hits.items() if len(keys) > 1}
    if agreements:
        lines.append("## Cross-Persona Agreement")
        for loc, keys in agreements.items():
            names = ", ".join(PERSONAS[k].name for k in keys)
            lines.append(f"- {loc} — flagged by: {names}")
        lines.append("")

    return "\n".join(lines)
