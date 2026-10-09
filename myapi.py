from uuid import uuid4
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from llm import run_agent
from models import Session
import traceback
import anthropic
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
  # Replace with your actual OpenAI API key

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    session_id: str | None = None   # None means "start a new conversation"
    message: str

class ToolEvent(BaseModel):
    name: str
    input: dict
    result: str
    is_error: bool

class ChatResponse(BaseModel):
    session_id: str
    reply: str
    verified: bool
    escalation_id: str | None = None
    tool_events: list[ToolEvent] = []

sessions: dict[str, Session] = {}   # server-side store; moves to Postgres later

@app.post("/chat", response_model=ChatResponse)
def post_chat(request: ChatRequest):
    # 1. Find or create the session
    if request.session_id is None:
        session = Session()
        sessions[session.id] = session
    elif request.session_id in sessions:
        session = sessions[request.session_id]
    else:
        raise HTTPException(status_code=404, detail="Session not found")

    # 2. Record the customer's message
    session.messages.append({"role": "user", "content": request.message})

    # 3. Placeholder until the agent is connected
    try:
        reply, events = run_agent(session)
    except anthropic.APIError:
        traceback.print_exc()
        raise HTTPException(status_code=503, detail="The assistant is temporarily unavailable. Please try again.")  # call the LLM to get a reply

    return ChatResponse(
    session_id=session.id,
    reply=reply,
    verified=session.verified,
    escalation_id=session.escalation_id,
    tool_events=events,
)