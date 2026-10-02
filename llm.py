from dotenv import load_dotenv
from anthropic import Anthropic
import os
from models import Session
from tools import TOOLS, run_tool
import traceback
from pydantic import ValidationError

load_dotenv()          # loads .env into environment variables
client = Anthropic(
    default_headers={"anthropic-workspace-id": os.environ["ANTHROPIC_WORKSPACE_ID"]}
)  # finds ANTHROPIC_API_KEY automatically

MODEL = "claude-haiku-4-5-20251001"   # fast and cheap for development
SYSTEM_PROMPT = (
    "You are Tidewell Bank's customer support assistant. Be concise and friendly. "
    "Before sharing or changing any account information, verify the customer's identity "
    "with the verify_identity tool, using their full name, date of birth, and the last "
    "4 digits of their card. "
    "Only say you've completed an action if a tool result confirms it. "
    "Tidewell Bank support can be reached at 1-800-555-0199, Monday to Friday, 8am to 8pm. "
    "Never invent phone numbers, websites, addresses, or other contact details; "
    "only share contact information given in these instructions."
)
TOOL_NAMES = {tool["name"] for tool in TOOLS}  # set of all tool names, for validation

def safe_run_tool(name: str, tool_input: dict, session: Session) -> tuple[str, bool]:
    if name not in TOOL_NAMES:
        return f"Unknown tool: {name}. Available tools: {', '.join(TOOL_NAMES)}", True
    try:
        return run_tool(name, tool_input, session), False
    except ValidationError as e:
        return f"Input validation error for tool {name}: {e}", True
    except Exception:
        traceback.print_exc()
        return ("This tool failed unexpectedly. Apologize to the customer and "
                "suggest they call Tidewell Bank support at 1-800-555-0199."), True
    

MAX_STEPS = 5

def run_agent(session: Session) -> str:
    for step in range(MAX_STEPS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=session.messages,
        )
        session.messages.append({"role": "assistant", "content": response.content})
        
        if response.stop_reason != "tool_use":
            return "".join(block.text for block in response.content if block.type == "text")
        
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                print("Tool call:", block.name, block.input)
                result, is_error = safe_run_tool(block.name, block.input, session)
                print("Tool result:", "ERROR" if is_error else "OK", "|", result)  
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                    "is_error": is_error,
                })
        session.messages.append({"role": "user", "content": tool_results})
        
    fallback = (
        "Sorry, I'm having trouble completing that request right now. "
        "Please try again in a moment, or call Tidewell Bank support at 1-800-555-0199."
    )
    print("Max steps reached for session", session.id)
    session.messages.append({"role": "assistant", "content": fallback})
    return fallback