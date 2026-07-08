from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from aipa.agent.schemas import AgentContext

_DEFAULT_SYSTEM_PROMPT = (
    "You are a helpful AI assistant for a business. "
    "Be concise, friendly, and professional."
)


def build_system_prompt(context: AgentContext, customer_name: str | None = None) -> str:
    sections: list[str] = []

    base = (
        context.boss_config.get("system_prompt_override")
        if context.boss_config
        else None
    ) or _DEFAULT_SYSTEM_PROMPT
    sections.append(base)

    tz_name = (context.boss_config or {}).get("timezone")
    now = datetime.now(timezone.utc)
    tz_label = "UTC"
    if tz_name:
        try:
            now = now.astimezone(ZoneInfo(tz_name))
            tz_label = tz_name
        except (KeyError, ValueError):
            pass
    sections.append(
        f"## Current Date & Time\n"
        f"It is {now.strftime('%A, %B %d, %Y at %H:%M')} ({tz_label}). "
        "Use this for any date or time reasoning; never guess dates from memory."
    )

    if customer_name:
        sections.append(
            f"## Customer\nYou are talking to {customer_name}. "
            "Address them by name when it feels natural — do not overuse it."
        )

    if context.knowledge_base:
        sections.append("## Business Knowledge Base")
        for entry in context.knowledge_base:
            sections.append(f"### {entry['title']}\n{entry['content']}")

    if context.skills:
        sections.append("## Your Active Capabilities")
        for skill in context.skills:
            sections.append(f"**{skill['name']}**: {skill['prompt_snippet']}")

    return "\n\n".join(sections)


def build_llm_messages(
    system_prompt: str,
    recent_messages: list,
    current_user_text: str,
) -> list[dict]:
    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    for msg in recent_messages:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": current_user_text})
    return messages
