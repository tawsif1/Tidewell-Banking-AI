from uuid import uuid4
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from llm import get_reply

app = FastAPI()
  # Replace with your actual OpenAI API key

class Session(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    verified: bool = False
    customer_id: int | None = None
    messages: list[dict] = Field(default_factory=list)

class ChatRequest(BaseModel):
    session_id: str | None = None   # None means "start a new conversation"
    message: str

class ChatResponse(BaseModel):
    session_id: str
    reply: str
    verified: bool

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
    reply = get_reply(session.messages)  # call the LLM to get a reply
    session.messages.append({"role": "assistant", "content": reply})

    return ChatResponse(session_id=session.id, reply=reply, verified=session.verified)