from dotenv import load_dotenv
from anthropic import Anthropic
import os

load_dotenv()          # loads .env into environment variables
client = Anthropic(
    default_headers={"anthropic-workspace-id": os.environ["ANTHROPIC_WORKSPACE_ID"]}
)  # finds ANTHROPIC_API_KEY automatically

MODEL = "claude-haiku-4-5-20251001"   # fast and cheap for development
SYSTEM_PROMPT = "You are Tidewell Bank's customer support assistant. Be concise and friendly."

def get_reply(messages: list[dict]) -> str:
    # TODO 1: call client.messages.create with the model, max_tokens,
    #         the system prompt, and the session's messages
    # TODO 2: return the text from the response
    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=messages
    )
    return "".join(block.text for block in response.content if block.type == "text")