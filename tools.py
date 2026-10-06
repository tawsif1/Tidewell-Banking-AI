"""Banking tools for the Tidewell Bank support agent.

Each tool is a plain Python function. Claude can only *ask* for a tool;
run_tool() decides what actually happens. Who the customer is always comes
from the session, never from Claude's input.
"""

from datetime import date, timedelta
from pydantic import BaseModel, Field
from bank_data import ACCOUNTS, CUSTOMERS, TRANSACTIONS, CARDS, DISPUTES, FEE_REVERSALS, ESCALATIONS 
from models import Session
from typing import Literal
from datetime import datetime

MAX_TRANSACTIONS = 15  # keeps tool results short, which saves tokens

# Display names for account types; anything not listed is shown with .title()
ACCOUNT_TYPE_LABELS = {"checking": "Checking", "savings": "Savings", "tfsa": "TFSA"}
VERIFY_IDENTITY_MAX_ATTEMPTS = 3  # after this many failed attempts, the session is locked
DISPUTE_WINDOW_DAYS = 60   # put this with your other constants at the top

REVERSIBLE_FEE_TYPES = {"overdraft", "nsf"}
FEE_REVERSAL_WINDOW_DAYS = 90         # only recent fees can be reversed
COURTESY_REVERSAL_PERIOD_DAYS = 365   # one courtesy reversal per customer per year

ESCALATION_QUEUES = {
    "fraud": "Fraud", "disputes": "Disputes", "fees": "Billing", "cards": "Cards",
    "account_access": "Account Access", "complaint": "Customer Relations", "other": "General Support",
}
CALLBACK_TIMES = {
    "urgent": "within 1 hour",
    "high": "within 4 business hours",
    "normal": "within 1 business day",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def format_amount(amount: float) -> str:
    """-86.42 -> '-$86.42', 2100 -> '+$2,100.00'"""
    sign = "-" if amount < 0 else "+"
    return f"{sign}${abs(amount):,.2f}"


def format_account(account_id: int, account: dict) -> str:
    """101 + checking -> 'Checking (101)'"""
    label = ACCOUNT_TYPE_LABELS.get(account["type"], account["type"].title())
    return f"{label} ({account_id})"


def customer_accounts(customer_id: int) -> dict:
    """All accounts owned by one customer, keyed by account number."""
    return {acc_id: acc for acc_id, acc in ACCOUNTS.items() if acc["customer_id"] == customer_id}

def format_handoff(ticket_id: str, t: dict) -> str:
    customer = f"{t['customer_name']} (#{t['customer_id']})" if t["verified"] else "Not verified"
    actions = "; ".join(t["actions_taken"]) or "None"
    return (
        f"\n===== HANDOFF {ticket_id} | {t['priority'].upper()} | Queue: {t['queue']} =====\n"
        f"Customer:     {customer}\n"
        f"Issue:        {t['summary']}\n"
        f"Already done: {actions}\n"
        f"Still needed: {t['still_needed']}\n"
        f"Sentiment:    {t['customer_sentiment']}"
        f"{'  (customer asked for a person)' if t['requested_by_customer'] else ''}\n"
    )


# ---------------------------------------------------------------------------
# Tool functions
# ---------------------------------------------------------------------------

def verify_identity(session: Session, full_name: str, date_of_birth: str, card_last4: str) -> str:
    if session.failed_attempts >= VERIFY_IDENTITY_MAX_ATTEMPTS:
                return ("Verification is locked after too many failed attempts. Do not try to verify again. "
                "Tell the customer to call Tidewell Bank support at 1-800-555-0199.")
    name = full_name.strip().lower()
    dob = date_of_birth.strip()
    card = card_last4.strip()

    for customer_id, customer in CUSTOMERS.items():
        if (
            customer["full_name"].lower() == name
            and customer["date_of_birth"] == dob
            and customer["card_last4"] == card
        ):
            session.verified = True
            session.customer_id = customer_id
            return "Identity verified successfully."

    # Same message whichever detail was wrong, so someone guessing learns nothing.
    session.failed_attempts += 1
    if session.failed_attempts >= VERIFY_IDENTITY_MAX_ATTEMPTS:
        return ("Verification is now locked after too many failed attempts. ""Tell the customer to call Tidewell Bank support at 1-800-555-0199.")
    return "The details provided don't match our records."


def get_accounts(session: Session) -> str:
    if not session.verified:
        return "Identity not verified. Cannot retrieve account information."

    accounts = customer_accounts(session.customer_id)
    if not accounts:
        return "No accounts found for this customer."

    return "\n".join(
        f"{format_account(acc_id, acc)}: ${acc['balance']:,.2f}"
        for acc_id, acc in accounts.items()
    )


def get_recent_transactions(session: Session, account_id: int | None = None, days: int = 30) -> str:
    if not session.verified:
        return "Identity not verified. Cannot retrieve transactions."

    accounts = customer_accounts(session.customer_id)

    # Same answer whether the account doesn't exist or belongs to someone else.
    if account_id is not None and account_id not in accounts:
        return "Account not found."

    cutoff = date.today() - timedelta(days=days)
    matches = []
    for tx_id, tx in TRANSACTIONS.items():
        if tx["account_id"] not in accounts:
            continue  # not this customer's account
        if account_id is not None and tx["account_id"] != account_id:
            continue  # customer asked about a different account
        if tx["date"] < cutoff:
            continue  # too old
        matches.append((tx_id, tx))

    if not matches:
        return "No transactions found for the specified criteria."

    matches.sort(key=lambda pair: pair[1]["date"], reverse=True)  # newest first

    lines = []
    for tx_id, tx in matches[:MAX_TRANSACTIONS]:
        account_label = format_account(tx["account_id"], accounts[tx["account_id"]])
        lines.append(
            f"{tx['date']} | #{tx_id} | {account_label} | {tx['description']} | "
            f"{format_amount(tx['amount'])} | {tx['status']}"
        )
    return "\n".join(lines)

def freeze_card(session: Session, card_last4: str, reason: Literal["lost", "stolen", "suspicious_activity", "other"]) -> str:
    if not session.verified:
        return "Identity not verified. Cannot freeze card."

    customer_id = session.customer_id
    for card_id, card in CARDS.items():
        if card["customer_id"] == customer_id and card["last4"] == card_last4:
            if card["status"] == "frozen":
                return f"Card ending in {card_last4} is already frozen."
            elif card["status"] == "cancelled":
                return f"Card ending in {card_last4} has been cancelled and cannot be frozen."
            else:
                card["status"] = "frozen"
                card["freeze_reason"] = reason
                session.actions_taken.append(f"Froze card ending {card_last4} (reason: {reason})")
                return f"Card ending in {card_last4} is now frozen (reason: {reason.replace('_', ' ')}). New purchases on this card will be declined."
    
    customer_cards = [
        f"{c['last4']} ({c['type']})"
        for c in CARDS.values()
        if c["customer_id"] == session.customer_id
    ]
    if not customer_cards:
        return "This customer has no cards on file."
    
    return f"Card not found. This customer's cards end in: {', '.join(customer_cards)}."

def dispute_transaction(session: Session, transaction_id: int, reason: Literal["unauthorized", "not_received", "duplicate_charge", "incorrect_amount", "other"], details: str) -> str:
    if not session.verified:    
        return "Identity not verified. Cannot dispute transaction."

    

    tx = TRANSACTIONS.get(transaction_id)

    if not tx or tx["account_id"] not in customer_accounts(session.customer_id):
            return "Transaction not found for this customer."

    for dispute_id, dispute in DISPUTES.items():
        if dispute["transaction_id"] == transaction_id:
            return (f"Transaction #{transaction_id} already has a dispute: "
                    f"{dispute_id} (status: {dispute['status']}).")
    
    

    if tx["status"] == "pending":
        return (f"Transaction #{transaction_id} is still pending and can't be disputed until it posts, "
                "usually within a few business days.")
    if tx["type"] == "fee":
        return (f"Transaction #{transaction_id} is a fee. Fees can't be disputed; "
                "they're handled through a fee reversal request instead.")
    if tx["amount"] >= 0:
        return f"Transaction #{transaction_id} is money coming into the account, so there's nothing to dispute."
    if tx["date"] < date.today() - timedelta(days=DISPUTE_WINDOW_DAYS):
        return (f"Transaction #{transaction_id} is more than {DISPUTE_WINDOW_DAYS} days old, outside the dispute "
                "window. Tell the customer to call Tidewell Bank support at 1-800-555-0199.")    

    # Here we would normally record the dispute in a database or system.
    dispute_id = f"DSP-{1001 + len(DISPUTES)}"
    DISPUTES[dispute_id] = {
        "transaction_id": transaction_id,
        "customer_id": session.customer_id,
        "reason": reason,
        "details": details,
        "status": "open",
        "filed_on": date.today(),
    }

    message = (f"Dispute {dispute_id} filed for transaction #{transaction_id} "
               f"({tx['description']}, {format_amount(tx['amount'])}). Status: open. "
               "A specialist will review it and contact the customer within 10 business days.")
    if reason == "unauthorized":
        message += " If the card used for this charge isn't frozen yet, offer to freeze it."
    session.actions_taken.append(f"Filed dispute {dispute_id} for transaction #{transaction_id} ({format_amount(tx['amount'])})")
    return message

def request_fee_reversal(session: Session, transaction_id: int, reason: str) -> str:
    # 1. Verified?
    if not session.verified:
        return "Identity not verified. Cannot reverse fees."

    # 2. Exists AND belongs to this customer?
    tx = TRANSACTIONS.get(transaction_id)
    if not tx or tx["account_id"] not in customer_accounts(session.customer_id):
        return "Transaction not found for this customer."

    # 3. Is it a fee?
    if tx["type"] != "fee":
        return (f"Transaction #{transaction_id} is not a fee. If the customer believes a charge "
                "is wrong, use dispute_transaction instead.")

    # 4. Already reversed? This check is what prevents paying out twice.
    for reversal_id, fr in FEE_REVERSALS.items():
        if fr["transaction_id"] == transaction_id:
            return f"Fee #{transaction_id} was already reversed ({reversal_id}) on {fr['reversed_on']}."

    # 5. Policy rules
    if tx.get("fee_type") not in REVERSIBLE_FEE_TYPES:
        return (f"Transaction #{transaction_id} isn't eligible for a courtesy reversal. Only "
                f"{' and '.join(sorted(REVERSIBLE_FEE_TYPES))} fees qualify. If the customer believes it was "
                "charged in error, they can call Tidewell Bank support at 1-800-555-0199.")
    if tx["date"] < date.today() - timedelta(days=FEE_REVERSAL_WINDOW_DAYS):
        return (f"Transaction #{transaction_id} is more than {FEE_REVERSAL_WINDOW_DAYS} days old, "
                "outside the reversal window.")
    period_start = date.today() - timedelta(days=COURTESY_REVERSAL_PERIOD_DAYS)
    for fr in FEE_REVERSALS.values():
        if fr["customer_id"] == session.customer_id and fr["reversed_on"] >= period_start:
            next_eligible = fr["reversed_on"] + timedelta(days=COURTESY_REVERSAL_PERIOD_DAYS)
            return (f"This customer already received a courtesy reversal on {fr['reversed_on']}. "
                    f"They'll be eligible again on {next_eligible}.")

    # 6. Reverse it: record, refund, and a credit transaction
    credit = abs(tx["amount"])
    account = ACCOUNTS[tx["account_id"]]

    reversal_id = f"FR-{2001 + len(FEE_REVERSALS)}"
    FEE_REVERSALS[reversal_id] = {
        "transaction_id": transaction_id,
        "customer_id": session.customer_id,
        "amount": credit,
        "reason": reason,
        "reversed_on": date.today(),
    }
    account["balance"] += credit
    TRANSACTIONS[max(TRANSACTIONS) + 1] = {
        "account_id": tx["account_id"],
        "date": date.today(),
        "description": f"{tx['description']} Reversal",
        "amount": credit,
        "type": "fee_reversal",
        "status": "posted",
    }
    session.actions_taken.append(f"Reversed fee #{transaction_id} as {reversal_id} ({format_amount(credit)})")

    return (f"Fee reversal {reversal_id} complete: {format_amount(credit)} credited to "
            f"{format_account(tx['account_id'], account)}. New balance: ${account['balance']:,.2f}.")


def escalate_to_human(session: Session, category: Literal["fraud", "disputes", "fees", "cards", "account_access", "complaint", "other"], priority: Literal["urgent", "high", "normal"], summary: str, still_needed: str, customer_sentiment: Literal["calm", "confused", "frustrated", "angry", "worried", "distressed"], requested_by_customer: bool) -> str:
    # 1. Already escalated in this session? Return the existing ticket, no duplicates.
    if session.escalation_id is not None:
        existing = ESCALATIONS[session.escalation_id]
        return (f"This conversation was already escalated as {session.escalation_id} "
                f"to the {existing['queue']} team.")

    # 2. Policy in code: suspected fraud is always urgent.
    if category == "fraud":
        priority = "urgent"

    # 3. Build the ticket: facts from the session, judgment from Claude.
    ticket_id = f"ESC-{3001 + len(ESCALATIONS)}"
    ticket = {
        # From the session (reliable)
        "session_id": session.id,
        "customer_id": session.customer_id,
        "verified": session.verified,
        "customer_name": CUSTOMERS[session.customer_id]["full_name"] if session.verified else None,
        "actions_taken": list(session.actions_taken),
        # From Claude (judgment)
        "category": category,
        "priority": priority,
        "summary": summary,
        "still_needed": still_needed,
        "customer_sentiment": customer_sentiment,
        "requested_by_customer": requested_by_customer,
        # Routing and status
        "queue": ESCALATION_QUEUES[category],
        "status": "open",
        "created_at": datetime.now(),
    }

    # 4. Save it and link it to the session.
    ESCALATIONS[ticket_id] = ticket
    session.escalation_id = ticket_id

    # 5. Show the specialist's view in the terminal.
    print(format_handoff(ticket_id, ticket))

    # 6. Tell Claude exactly what happens next.
    if session.verified:
        next_step = f"A specialist will call the customer at the number on file {CALLBACK_TIMES[priority]}."
    else:
        next_step = ("The customer isn't verified, so ask them to call Tidewell Bank support at "
                     "1-800-555-0199 and quote this reference.")
    return (f"Escalation {ticket_id} sent to the {ticket['queue']} team with a full summary, so the customer "
            f"won't need to repeat themselves. {next_step} Give the customer the reference {ticket_id}.")
# ---------------------------------------------------------------------------
# Tool input schemas: exactly what Claude is allowed to provide
# ---------------------------------------------------------------------------

class VerifyIdentityInput(BaseModel):
    full_name: str = Field(description="Customer's full name")
    date_of_birth: str = Field(description="Date of birth in YYYY-MM-DD format")
    card_last4: str = Field(description="Last 4 digits of the customer's card")


class GetAccountsInput(BaseModel):
    pass  # no inputs: whose accounts comes from the session


class GetRecentTransactionsInput(BaseModel):
    account_id: int | None = Field(
        default=None,
        description="Account number to show. Leave empty for all of the customer's accounts.",
    )
    days: int = Field(
        default=30, ge=1, le=90,
        description="How many days back to look, from 1 to 90.",
    )

class FreezeCardInput(BaseModel):
    card_last4: str = Field(description="Last 4 digits of the card to freeze, as confirmed by the customer")
    reason: Literal["lost", "stolen", "suspicious_activity", "other"] = Field(
        description="Why the card is being frozen"
    )

class DisputeTransactionInput(BaseModel):
    transaction_id: int = Field(description="ID of the transaction to dispute, from get_recent_transactions (e.g. 5006)")
    reason: Literal["unauthorized", "not_received", "duplicate_charge", "incorrect_amount", "other"] = Field(
        description="Why the customer is disputing the charge"
    )
    details: str = Field(max_length=500, description="Short summary of the problem in the customer's own words")

class RequestFeeReversalInput(BaseModel):
    transaction_id: int = Field(description="ID of the fee transaction to reverse, from get_recent_transactions")
    reason: str = Field(max_length=300, description="Short summary of why the customer is asking")

class EscalateToHumanInput(BaseModel):
    category: Literal["fraud", "disputes", "fees", "cards", "account_access", "complaint", "other"] = Field(
        description="The main topic, used to route the ticket to the right team"
    )
    priority: Literal["urgent", "high", "normal"] = Field(
        description="urgent: suspected fraud or money at immediate risk; high: very upset or vulnerable customer, "
                    "or a blocked account; normal: everything else"
    )
    summary: str = Field(max_length=400, description="Two or three sentences on what the customer needs, written for a human specialist")
    still_needed: str = Field(max_length=300, description="What the specialist needs to do next")
    customer_sentiment: Literal["calm", "confused", "frustrated", "angry", "worried", "distressed"]
    requested_by_customer: bool = Field(description="True if the customer asked to speak to a person")

# ---------------------------------------------------------------------------
# Tool registry: the menu of tools Claude sees
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "verify_identity",
        "description": (
            "Verify the customer's identity. Must succeed before sharing "
            "or changing any account information."
        ),
        "input_schema": VerifyIdentityInput.model_json_schema(),
    },
    {
        "name": "get_accounts",
        "description": (
            "List the verified customer's accounts with their types and balances. "
            "Identity must be verified first."
        ),
        "input_schema": GetAccountsInput.model_json_schema(),
    },
    {
        "name": "get_recent_transactions",
        "description": (
            "List the verified customer's recent transactions, newest first, with "
            "transaction IDs. Use when the customer asks about spending, deposits, "
            "or a charge they don't recognize. Leave account_id empty to show all "
            "their accounts."
        ),
        "input_schema": GetRecentTransactionsInput.model_json_schema(),
    },
    {
    "name": "freeze_card",
    "description": (
        "Freeze one of the verified customer's cards so new purchases are declined. "
        "Use when the customer reports a card lost, stolen, or used without their permission. "
        "Confirm which card (by its last 4 digits) with the customer before calling."
    ),
    "input_schema": FreezeCardInput.model_json_schema(),
    },
    {
    "name": "dispute_transaction",
    "description": (
        "File a dispute for a posted charge on the verified customer's account. Use when the "
        "customer says they didn't make a charge, didn't receive what they paid for, or were "
        "charged the wrong amount. Get the transaction ID from get_recent_transactions and "
        "confirm the charge with the customer before calling."
    ),
    "input_schema": DisputeTransactionInput.model_json_schema(),
    },
    {
    "name": "request_fee_reversal",
    "description": (
        "Reverse an eligible fee on the verified customer's account and credit the amount back immediately. "
        f"Policy: customers can get one courtesy reversal every {COURTESY_REVERSAL_PERIOD_DAYS} days, for "
        f"{' or '.join(sorted(REVERSIBLE_FEE_TYPES))} fees charged within the last {FEE_REVERSAL_WINDOW_DAYS} days. "
        "Other fees, such as wire transfer or monthly account fees, aren't eligible. "
        "Explain this policy before asking the customer which fee to reverse. Get the fee's transaction ID "
        "from get_recent_transactions and confirm it with the customer before calling. "
        "The tool checks eligibility itself and explains any refusal."
    ),
    "input_schema": RequestFeeReversalInput.model_json_schema(),
},
    {
    "name": "escalate_to_human",
    "description": (
        "Hand the conversation to a human specialist by creating a support ticket. Use when the customer asks "
        "for a person, the request is outside what your other tools can do, you suspect fraud beyond a single "
        "dispute, the customer is very upset or seems vulnerable, or identity verification is locked. It can be "
        "used without verification, but never include account details for an unverified customer. Don't escalate "
        "issues already resolved with other tools. This is not a live transfer: tell the customer exactly what "
        "the tool result says will happen next."
    ),
    "input_schema": EscalateToHumanInput.model_json_schema(),
}
]


# ---------------------------------------------------------------------------
# Dispatcher: runs the tool Claude asked for
# ---------------------------------------------------------------------------

def run_tool(name: str, tool_input: dict, session: Session) -> str:
    if name == "verify_identity":
        args = VerifyIdentityInput(**tool_input)  # validate before touching any data
        return verify_identity(session, **args.model_dump())
    
    if name == "get_accounts":
        GetAccountsInput(**tool_input)  # nothing to pass on, but keep the same pattern
        return get_accounts(session)
    
    if name == "get_recent_transactions":
        args = GetRecentTransactionsInput(**tool_input)
        return get_recent_transactions(session, **args.model_dump())
    
    if name == "freeze_card":
        args = FreezeCardInput(**tool_input)
        return freeze_card(session, **args.model_dump())
    
    if name == "dispute_transaction":
        args = DisputeTransactionInput(**tool_input)
        return dispute_transaction(session, **args.model_dump())
    
    if name == "request_fee_reversal":
        args = RequestFeeReversalInput(**tool_input)
        return request_fee_reversal(session, **args.model_dump())

    if name == "escalate_to_human":
        args = EscalateToHumanInput(**tool_input)
        return escalate_to_human(session, **args.model_dump())
    

    raise ValueError(f"No handler in run_tool for tool: {name}")