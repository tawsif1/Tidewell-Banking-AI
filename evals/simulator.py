import anthropic
from evals.scenario import Scenario

client = anthropic.Anthropic()
CUSTOMER_MODEL = "claude-haiku-4-5-20251001"


def customer_system_prompt(s: Scenario) -> str:
    facts = "\n".join(f"- {k}: {v}" for k, v in s.knows.items()) or "- Nothing. You won't share personal details."
    return f"""You are playing a customer of Tidewell Bank, chatting with its support assistant.
Who you are: {s.persona}
What you want: {s.goal}
What you know, and instructions to follow (use only these; never invent details):
{facts}

Rules:
- Write only the customer's next message: short and natural.
- Give details only when asked, or when your instructions say to.
- Never say this is a test, and never help the assistant.
- When your goal is done, or the chat can't go any further, reply with exactly [DONE]."""