"""Seed the skills catalog: 100 industries x 20 functions = 2000 generated
skills plus the hand-curated generic pack.

Usage (from the aipa/ directory, with .env configured):

    python -m aipa.scripts.generate_skills --dry-run          # preview, no DB writes
    python -m aipa.scripts.generate_skills                    # full run
    python -m aipa.scripts.generate_skills --limit-industries 5   # small test batch
    python -m aipa.scripts.generate_skills --skip-embeddings  # generation only

Environment (in addition to aipa/.env):
    SEED_API_KEY   - LLM key used to GENERATE skill text (required unless --dry-run)
    SEED_MODEL     - generation model (default: openai/gpt-4o-mini)

Embeddings use EMBEDDING_MODEL / EMBEDDING_API_KEY from settings; skills are
inserted without embeddings when no key is set, and the runtime falls back to
non-vector selection. Re-running the script is safe: existing slugs are
skipped and missing embeddings are backfilled.
"""

import argparse
import asyncio
import json
import os
import re
import sys

import litellm

from aipa.config import get_settings
from aipa.db.client import create_pool
from aipa.scripts.taxonomy import FUNCTIONS, GENERIC_SKILLS, INDUSTRIES

SEED_MODEL = os.environ.get("SEED_MODEL", "openai/gpt-4o-mini")
SEED_API_KEY = os.environ.get("SEED_API_KEY", "")

FUNCTION_CATEGORY = {
    "booking": "booking",
    "cancellation": "booking",
    "lead-capture": "sales",
    "pricing": "sales",
    "upsell": "sales",
    "payments": "sales",
    "product-info": "sales",
    "faq": "support",
    "availability": "support",
    "location": "support",
    "complaints": "support",
    "order-status": "support",
    "emergency": "support",
    "eligibility": "support",
    "aftercare": "support",
    "handoff": "support",
    "follow-up": "growth",
    "new-customer": "growth",
    "loyalty": "growth",
    "feedback": "growth",
}

_GENERATION_PROMPT = """You are writing system-prompt skill modules for an AI customer-service \
assistant that small businesses run on Telegram.

Business type: {industry_label}

For EACH function below, write one skill tailored to this business type:
{function_list}

Return ONLY a JSON array of {n} objects, one per function, in the same order:
{{"function": "<function slug>", "name": "<skill name, max 6 words, specific to this business type>", \
"description": "<one sentence shown to the business owner next to a toggle, max 140 chars>", \
"prompt_snippet": "<2-4 sentence instruction injected into the assistant's system prompt. \
Written as direct instructions ('When a customer...'). Concrete to this business type: mention its \
typical services, vocabulary, and situations. Must tell the assistant to rely on the business \
knowledge base for facts like prices and hours rather than inventing them.>"}}

No markdown fences, no commentary — just the JSON array."""


def _build_prompt(industry_label: str) -> str:
    function_list = "\n".join(
        f"- {slug}: {label} — {brief}" for slug, label, brief in FUNCTIONS
    )
    return _GENERATION_PROMPT.format(
        industry_label=industry_label, function_list=function_list, n=len(FUNCTIONS)
    )


def _parse_json_array(raw: str) -> list[dict]:
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        raise ValueError("no JSON array in response")
    return json.loads(text[start : end + 1])


def _validate_skill(item: dict, valid_functions: set[str]) -> str | None:
    """Returns an error string, or None when the item is usable."""
    for key in ("function", "name", "description", "prompt_snippet"):
        if not isinstance(item.get(key), str) or not item[key].strip():
            return f"missing field {key}"
    if item["function"] not in valid_functions:
        return f"unknown function {item['function']!r}"
    if not 40 <= len(item["prompt_snippet"]) <= 900:
        return "prompt_snippet length out of range"
    if "{" in item["prompt_snippet"] or "TODO" in item["prompt_snippet"]:
        return "prompt_snippet contains placeholder text"
    return None


async def _generate_industry(
    industry_slug: str,
    industry_label: str,
    existing_slugs: set[str],
    semaphore: asyncio.Semaphore,
) -> list[dict]:
    wanted = {
        f"{industry_slug}-{fslug}": fslug
        for fslug, _, _ in FUNCTIONS
        if f"{industry_slug}-{fslug}" not in existing_slugs
    }
    if not wanted:
        return []

    valid_functions = set(wanted.values())
    async with semaphore:
        for attempt in (1, 2):
            try:
                response = await litellm.acompletion(
                    model=SEED_MODEL,
                    messages=[{"role": "user", "content": _build_prompt(industry_label)}],
                    api_key=SEED_API_KEY,
                    temperature=0.8,
                    timeout=120,
                )
                items = _parse_json_array(response.choices[0].message.content)
                break
            except Exception as exc:
                if attempt == 2:
                    print(f"  !! {industry_slug}: generation failed twice ({exc})")
                    return []

    skills: list[dict] = []
    for item in items:
        error = _validate_skill(item, valid_functions)
        if error:
            print(f"  !! {industry_slug}: skipped one skill ({error})")
            continue
        fslug = item["function"]
        slug = f"{industry_slug}-{fslug}"
        if slug not in wanted:
            continue
        skills.append(
            {
                "slug": slug,
                "name": item["name"].strip()[:80],
                "description": item["description"].strip()[:200],
                "prompt_snippet": item["prompt_snippet"].strip(),
                "category": FUNCTION_CATEGORY.get(fslug, "general"),
                "industry": industry_slug,
            }
        )
    print(f"  ok {industry_slug}: {len(skills)}/{len(wanted)} skills")
    return skills


async def _insert_skills(pool, skills: list[dict], verified: bool) -> int:
    if not skills:
        return 0
    async with pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO skills (slug, name, description, prompt_snippet,
                                category, industry, is_verified)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (slug) DO NOTHING
            """,
            [
                (
                    s["slug"],
                    s["name"],
                    s["description"],
                    s["prompt_snippet"],
                    s["category"],
                    s.get("industry", "generic"),
                    verified,
                )
                for s in skills
            ],
        )
    return len(skills)


async def _backfill_embeddings(pool, batch_size: int = 100) -> int:
    settings = get_settings()
    if not settings.EMBEDDING_API_KEY:
        print("No EMBEDDING_API_KEY set — skipping embeddings (runtime will use fallback selection).")
        return 0

    total = 0
    while True:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, name, description, prompt_snippet
                FROM skills WHERE embedding IS NULL
                LIMIT $1
                """,
                batch_size,
            )
        if not rows:
            break

        inputs = [
            f"{r['name']}. {r['description'] or ''} {r['prompt_snippet'] or ''}".strip()
            for r in rows
        ]
        response = await litellm.aembedding(
            model=settings.EMBEDDING_MODEL,
            input=inputs,
            api_key=settings.EMBEDDING_API_KEY,
            timeout=60,
        )
        vectors = [
            "[" + ",".join(f"{v:.8f}" for v in item["embedding"]) + "]"
            for item in response.data
        ]
        async with pool.acquire() as conn:
            await conn.executemany(
                "UPDATE skills SET embedding = $2::vector WHERE id = $1",
                list(zip([r["id"] for r in rows], vectors)),
            )
        total += len(rows)
        print(f"  embedded {total} skills...")
    return total


async def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the AI'PA skills catalog")
    parser.add_argument("--dry-run", action="store_true", help="generate one industry, print, no DB writes")
    parser.add_argument("--limit-industries", type=int, default=None)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--skip-embeddings", action="store_true")
    args = parser.parse_args()

    if not SEED_API_KEY and not args.dry_run:
        sys.exit("SEED_API_KEY env var is required (the LLM key used to generate skill text).")

    industries = INDUSTRIES[: args.limit_industries] if args.limit_industries else INDUSTRIES

    if args.dry_run:
        if not SEED_API_KEY:
            sys.exit("SEED_API_KEY is required for --dry-run too (it makes one real LLM call).")
        skills = await _generate_industry(
            industries[0][0], industries[0][1], set(), asyncio.Semaphore(1)
        )
        print(json.dumps(skills, indent=2))
        return

    pool = await create_pool()
    try:
        inserted_generic = await _insert_skills(pool, GENERIC_SKILLS, verified=True)
        print(f"Generic pack: {inserted_generic} skills upserted.")

        async with pool.acquire() as conn:
            existing = {
                r["slug"] for r in await conn.fetch("SELECT slug FROM skills WHERE slug IS NOT NULL")
            }
        print(f"Existing catalog: {len(existing)} skills. Generating for {len(industries)} industries...")

        semaphore = asyncio.Semaphore(args.concurrency)
        results = await asyncio.gather(
            *[
                _generate_industry(slug, label, existing, semaphore)
                for slug, label in industries
            ]
        )
        generated = [skill for batch in results for skill in batch]
        await _insert_skills(pool, generated, verified=False)
        print(f"Inserted {len(generated)} generated skills.")

        if not args.skip_embeddings:
            embedded = await _backfill_embeddings(pool)
            print(f"Embedded {embedded} skills.")

        async with pool.acquire() as conn:
            total = await conn.fetchval("SELECT COUNT(*) FROM skills")
        print(f"Done. Catalog now holds {total} skills.")
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
