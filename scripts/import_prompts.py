"""Import persona skills from the awesome-chatgpt-prompts dataset (CC0).

Source: https://github.com/f/awesome-chatgpt-prompts (prompts.csv, columns
"act","prompt"[, "for_devs"]). Each row becomes one toggleable skill:
name = act, prompt_snippet = the persona prompt, category = 'persona'.

Usage (from the directory ABOVE aipa/, with aipa/.env configured):

    python -m aipa.scripts.import_prompts --dry-run           # preview, no DB writes
    python -m aipa.scripts.import_prompts                     # download + insert + embed
    python -m aipa.scripts.import_prompts --file prompts.csv  # use a local CSV instead
    python -m aipa.scripts.import_prompts --skip-embeddings

Re-running is safe: slugs are deduped with ON CONFLICT DO NOTHING and the
embedding backfill only touches rows where embedding IS NULL.
"""

import argparse
import asyncio
import csv
import io
import re
import sys

import httpx

from aipa.db.client import create_pool
from aipa.scripts.generate_skills import _backfill_embeddings, _insert_skills

CSV_URL = "https://raw.githubusercontent.com/f/awesome-chatgpt-prompts/main/prompts.csv"

# Personas that make no sense as a business assistant skill (games, terminals,
# roleplay novelty). Matched case-insensitively against the act name.
_EXCLUDE_PATTERNS = re.compile(
    r"terminal|console|interpreter|tic-tac-toe|gomoku|chess|drunk|lunatic|"
    r"gaslight|unconstrained|DAN\b|jailbreak|emoji translator|morse",
    re.IGNORECASE,
)

_MAX_SNIPPET = 1200  # keep prompt injection lean; personas can ramble


def _slugify(act: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", act.lower()).strip("-")
    return f"persona-{slug[:60]}"


def _clean_snippet(prompt: str) -> str:
    text = " ".join(prompt.split())
    # Drop the trailing "My first request is ..." example that most rows carry —
    # it's a usage example for humans, not an instruction for the agent.
    text = re.sub(
        r"\s*(?:My first (?:request|sentence|command|question|task|suggestion|topic)\b.*)$",
        "",
        text,
        flags=re.IGNORECASE,
    )
    if len(text) > _MAX_SNIPPET:
        text = text[:_MAX_SNIPPET].rsplit(" ", 1)[0] + "…"
    return text


def _to_skill(act: str, prompt: str) -> dict | None:
    act, prompt = act.strip().strip('"'), prompt.strip()
    if not act or not prompt or _EXCLUDE_PATTERNS.search(act):
        return None
    # Junk filters: names must start with a letter; skip template/JSON-blob
    # prompts (image generators, trading-signal templates, etc.)
    if not re.match(r"^[A-Za-z]", act):
        return None
    if prompt.lstrip().startswith("{") or "{{" in prompt:
        return None
    # The dataset drifted to include image-generation prompts and one-off
    # tasks; real personas open with an instruction ("I want you to act as…").
    if not re.match(
        r"^(i want you to (act|be|serve)|act as|you are|imagine you are|as an? )",
        prompt.strip(),
        re.IGNORECASE,
    ):
        return None
    snippet = _clean_snippet(prompt)
    if len(snippet) < 40:
        return None
    description = snippet if len(snippet) <= 140 else snippet[:137].rsplit(" ", 1)[0] + "..."
    return {
        "slug": _slugify(act),
        "name": act[:80],
        "description": description,
        "prompt_snippet": snippet,
        "category": "persona",
        "industry": "generic",
    }


def _parse_csv(raw_text: str) -> list[dict]:
    # Some prompts in the dataset exceed the default 128 KB field limit
    csv.field_size_limit(10_000_000)
    reader = csv.DictReader(io.StringIO(raw_text))
    if reader.fieldnames is None or "act" not in [f.lower() for f in reader.fieldnames]:
        sys.exit(f"Unexpected CSV header: {reader.fieldnames}")

    skills, seen = [], set()
    for row in reader:
        row = {k.lower(): (v or "") for k, v in row.items()}
        skill = _to_skill(row.get("act", ""), row.get("prompt", ""))
        if skill and skill["slug"] not in seen:
            seen.add(skill["slug"])
            skills.append(skill)
    return skills


async def main() -> None:
    parser = argparse.ArgumentParser(description="Import awesome-chatgpt-prompts personas")
    parser.add_argument("--file", help="local prompts.csv instead of downloading")
    parser.add_argument("--dry-run", action="store_true", help="print skills, no DB writes")
    parser.add_argument("--skip-embeddings", action="store_true")
    args = parser.parse_args()

    if args.file:
        with open(args.file, encoding="utf-8") as fh:
            raw = fh.read()
    else:
        print(f"Downloading {CSV_URL} ...")
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(CSV_URL)
            resp.raise_for_status()
            raw = resp.text

    skills = _parse_csv(raw)
    print(f"Parsed {len(skills)} usable persona skills.")

    if args.dry_run:
        for s in skills[:10]:
            print(f"  {s['slug']:50s} {s['name']}")
        print(f"  ... and {max(0, len(skills) - 10)} more")
        return

    pool = await create_pool()
    try:
        await _insert_skills(pool, skills, verified=False)
        print(f"Upserted {len(skills)} persona skills (existing slugs skipped).")
        if not args.skip_embeddings:
            embedded = await _backfill_embeddings(pool)
            print(f"Embedded {embedded} skills.")
        async with pool.acquire() as conn:
            total = await conn.fetchval("SELECT COUNT(*) FROM skills WHERE category = 'persona'")
        print(f"Done. Catalog now holds {total} persona skills.")
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
