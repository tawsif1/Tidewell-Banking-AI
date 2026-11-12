from models import Session
from session_store import load_session, save_session

s = Session()
s.messages.append({"role": "user", "content": "What are my balances?"})
save_session(s)                       # first save: inserts the row

s.verified, s.customer_id = True, 1
s.actions_taken.append("Froze card ending 7310 (reason: lost)")
s.messages.append({"role": "assistant", "content": [{"type": "text", "text": "Your card is frozen."}]})
save_session(s)                       # second save: updates the same row

loaded = load_session(s.id)
print(loaded.verified, loaded.customer_id, loaded.actions_taken, len(loaded.messages))
print(loaded.messages[1]["content"][0]["text"])
print(load_session("no-such-session"))