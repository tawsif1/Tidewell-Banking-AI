from models import Session
from tools import run_tool

def verify(session, card):
    details = {"full_name": "  MARIA chen ", "date_of_birth": "1988-04-12", "card_last4": card}
    return run_tool("verify_identity", details, session)

s = Session()
print(verify(s, "4821"), "|", s.verified, s.customer_id)

print()
s = Session()
for card in ["0000", "1111", "2222", "4821"]:
    print(verify(s, card))
print(s.verified, s.customer_id)

print()
s = Session()
details = {"full_name": "Maria Chen", "date_of_birth": "1988-02-30", "card_last4": "4821"}
try:
    print(run_tool("verify_identity", details, s))
except Exception as e:
    print(type(e).__name__, "| attempts used:", s.failed_attempts)