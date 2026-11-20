from uuid import uuid4
import os
import time
from collections import defaultdict, deque
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from llm import run_agent
from models import Session
import traceback
import anthropic
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from session_store import load_session, save_session

app = FastAPI()

# Comma-separated list of browser origins allowed to call the API (set on Render to the UI's URL).
ALLOWED_ORIGINS = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "http://localhost:5173").split(",") if o.strip()]

# Every chat message costs Anthropic and Voyage credits, so a public demo needs limits.
# In memory, so they reset when the server restarts and apply per server process.
PER_IP_LIMIT = int(os.environ.get("RATE_LIMIT_PER_IP_PER_HOUR", "40"))
DAILY_LIMIT = int(os.environ.get("RATE_LIMIT_PER_DAY", "400"))
_ip_hits: dict[str, deque] = defaultdict(deque)
_day_hits: deque = deque()


def check_rate_limit(request: Request) -> None:
    now = time.time()
    forwarded = request.headers.get("x-forwarded-for")          # Render puts the real client first
    ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")
    hits = _ip_hits[ip]
    while hits and hits[0] < now - 3600:
        hits.popleft()
    while _day_hits and _day_hits[0] < now - 86400:
        _day_hits.popleft()
    if len(hits) >= PER_IP_LIMIT:
        raise HTTPException(status_code=429, detail="You've reached the hourly message limit for this demo. Please try again later.")
    if len(_day_hits) >= DAILY_LIMIT:
        raise HTTPException(status_code=429, detail="This demo has reached its daily message limit. Please try again tomorrow.")
    hits.append(now)
    _day_hits.append(now)
  # Replace with your actual OpenAI API key

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
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

@app.post("/chat", response_model=ChatResponse)
def post_chat(request: ChatRequest, http_request: Request):
    check_rate_limit(http_request)
    if request.session_id is None:
        session = Session()
    else:
        session = load_session(request.session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")

    session.messages.append({"role": "user", "content": request.message})
    try:
        reply, events = run_agent(session)
    except anthropic.APIError:
        traceback.print_exc()
        raise HTTPException(status_code=503, detail="The assistant is temporarily unavailable. Please try again.")

    save_session(session)   # only after a successful turn
    return ChatResponse(session_id=session.id, reply=reply, verified=session.verified,
                        escalation_id=session.escalation_id, tool_events=events)