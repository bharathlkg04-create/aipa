from dataclasses import dataclass, field


@dataclass
class AgentContext:
    knowledge_base: list
    skills: list
    recent_messages: list
    boss_config: dict | None
    decrypted_api_key: str
