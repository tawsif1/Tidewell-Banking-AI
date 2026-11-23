import anthropic
from evals.scenario import Scenario
import anthropic
from dotenv import load_dotenv
from evals.scenario import Scenario
from llm import run_agent
from models import Session

load_dotenv()                      # must run before the client is created
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
- When your goal is done, or 
the chat can't go any further, reply with exactly [DONE]."""

def customer_reply(s: Scenario, history: list[tuple[str, str]]) -> str:
    """history: [("customer", text), ("agent", text), ...], starting with the opening message."""
    messages = [{"role": "user", "content": "(The chat has started.)"}]
    for speaker, text in history:
        role = "assistant" if speaker == "customer" else "user"
        messages.append({"role": role, "content": text})

    response = client.messages.create(
        model=CUSTOMER_MODEL,
        max_tokens=300,
        system=customer_system_prompt(s),
        messages=messages,
    )
    return response.content[0].text.strip()




def run_conversation(s: Scenario) -> dict:
    session = Session()
    history = []        # what the customer model sees
    turns = []          # the full record, with tool events
    customer_msg = s.opening

    for _ in range(s.max_turns):
        history.append(("customer", customer_msg))
        session.messages.append({"role": "user", "content": customer_msg})
        reply, events = run_agent(session)

        history.append(("agent", reply or "(no reply)"))
        turns.append({"customer": customer_msg, "agent": reply, "tool_events": events})

        customer_msg = customer_reply(s, history)
        if "[DONE]" in customer_msg:
            break

    return {"scenario": s.id, "turns": turns,
            "verified": session.verified, "escalation_id": session.escalation_id}