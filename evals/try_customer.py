from evals.scenario import load_scenarios
from evals.simulator import customer_reply
from evals.scenario import load_scenarios
from evals.simulator import run_conversation

s = load_scenarios()[0]   # s01, Maria
history = [
    ("customer", s.opening),
    ("agent", "I can help with that. Could you give me your full name, date of birth and the last 4 digits of your card?"),
]
print(customer_reply(s, history))


result = run_conversation(load_scenarios()[0])   # s01, Maria
for t in result["turns"]:
    print("CUSTOMER:", t["customer"])
    print("AGENT:   ", t["agent"])
    print("TOOLS:   ", [e["name"] for e in t["tool_events"]])
    print()
print("verified:", result["verified"])