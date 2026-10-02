from models import Session
from tools import verify_identity

s = Session()
print(verify_identity(s, "maria chen ", "1988-04-12", "4821"), s.verified, s.customer_id)

s2 = Session()
print(verify_identity(s2, "Maria Chen", "1990-01-01", "4821"), s2.verified, s2.customer_id)