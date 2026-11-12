"""Banking tools for the Tidewell Bank support agent.

Each tool is a plain Python function. Claude can only *ask* for a tool;
run_tool() decides what actually happens. Who the customer is always comes
from the session, never from Claude's input.
"""

from datetime import date, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field
from requests import session
from models import Session
from rag import search as rag_search
from db import pool


# ---------------------------------------------------------------------------
# Constants: bank policy and limits, kept in one place
# ---------------------------------------------------------------------------

MAX_TRANSACTIONS = 15                 # keeps tool results short, which saves tokens

# Display names for account types; anything not listed is shown with .title()
ACCOUNT_TYPE_LABELS = {"checking": "Checking", "savings": "Savings", "tfsa": "TFSA"}

VERIFY_IDENTITY_MAX_ATTEMPTS = 3      # after this many failed attempts, verification is locked
DISPUTE_WINDOW_DAYS = 60              # charges older than this can't be disputed

REVERSIBLE_FEE_TYPES = {"overdraft", "nsf"}
FEE_REVERSAL_WINDOW_DAYS = 90         # only recent fees can be reversed
COURTESY_REVERSAL_PERIOD_DAYS = 365   # one courtesy reversal per customer per year

MIN_SEARCH_SCORE = 0.45               # only show help center sections at least this relevant
SEARCH_TOP_K = 5                      # how many help center sections to return, at most

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


def format_account(account_id: int, account_type: str) -> str:
    """101 + 'checking' -> 'Checking (101)'"""
    label = ACCOUNT_TYPE_LABELS.get(account_type, account_type.title())
    return f"{label} ({account_id})"



def format_handoff(ticket_id: str, t: dict) -> str:
    """The specialist's view of an escalation ticket."""
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

def format_transaction(tx: dict) -> str:
    """One transaction as a line, plus its dispute or reversal if it has one."""
    line = (f"{tx['date']} | #{tx['id']} | {format_account(tx['account_id'], tx['account_type'])} | "
            f"{tx['description']} | {format_amount(tx['amount'])} | {tx['status']}")
    if tx["dispute_id"]:
        line += f" | disputed ({tx['dispute_id']})"
    if tx["reversal_id"]:
        line += f" | reversed ({tx['reversal_id']})"
    return line\

def next_step_for(verified: bool, priority: str) -> str:
    """What happens after an escalation, in one place, so both branches say the same thing."""
    if verified:
        return f"A specialist will call the customer at the number on file {CALLBACK_TIMES[priority]}."
    return ("The customer isn't verified, so no one will call them. Ask them to call Tidewell Bank "
            "support at 1-800-555-0199 and quote this reference.")


# ---------------------------------------------------------------------------
# Tool functions
# ---------------------------------------------------------------------------

def verify_identity(session: Session, full_name: str, date_of_birth: str, card_last4: str) -> str:

    if session.failed_attempts >= VERIFY_IDENTITY_MAX_ATTEMPTS:
        return ("Verification is locked after too many failed attempts. Do not try to verify again. "
                "Tell the customer to call Tidewell Bank support at 1-800-555-0199.")

    name = full_name.strip().lower()
    dob = date_of_birth
    card = card_last4.strip()

    with pool.connection() as conn:
        customer = conn.execute(
            "SELECT id FROM customers WHERE lower(full_name) = %s AND date_of_birth = %s AND card_last4 = %s ORDER BY id",
            (name, dob, card),
        ).fetchone()

        if customer:
            session.verified = True
            session.customer_id = customer["id"]
            return "Identity verified successfully."

    # Same message whichever detail was wrong, so someone guessing learns nothing.
    session.failed_attempts += 1
    if session.failed_attempts >= VERIFY_IDENTITY_MAX_ATTEMPTS:
        return ("Verification is now locked after too many failed attempts. "
                "Tell the customer to call Tidewell Bank support at 1-800-555-0199.")
    return "The details provided don't match our records."


def get_accounts(session: Session) -> str:
    if not session.verified:
        return "Identity not verified. Cannot retrieve account information."

    with pool.connection() as conn:
        accounts = conn.execute(
            "SELECT id, type, balance FROM accounts WHERE customer_id = %s ORDER BY id",
            (session.customer_id,),
        ).fetchall()

    if not accounts:
        return "No accounts found for this customer."

    return "\n".join(
        f"{format_account(acc['id'], acc['type'])}: ${acc['balance']:,.2f}"
        for acc in accounts
    )

def get_recent_transactions(session: Session, account_id: int | None = None, days: int = 30) -> str:
    if not session.verified:
        return "Identity not verified. Cannot retrieve transactions."

    cutoff = date.today() - timedelta(days=days)

    with pool.connection() as conn:
        sql = """
            SELECT t.id, t.date, t.description, t.amount, t.status, t.account_id,
            a.type AS account_type, d.id AS dispute_id, fr.id AS reversal_id
            FROM transactions t
            JOIN accounts a ON a.id = t.account_id
            LEFT JOIN disputes d       ON d.transaction_id = t.id
            LEFT JOIN fee_reversals fr ON fr.transaction_id = t.id
            WHERE a.customer_id = %s AND t.date >= %s
        """
        params = [session.customer_id, cutoff]

        if account_id is not None:
            # Same answer whether the account doesn't exist or belongs to someone else.
            owned = conn.execute(
                "SELECT 1 FROM accounts WHERE id = %s AND customer_id = %s",
                (account_id, session.customer_id),
            ).fetchone()
            if owned is None:
                return "Account not found."
            sql += " AND t.account_id = %s"
            params.append(account_id)

        sql += " ORDER BY t.date DESC, t.id DESC LIMIT %s"
        params.append(MAX_TRANSACTIONS)
        transactions = conn.execute(sql, params).fetchall()

    if not transactions:
        return f"No transactions found between {cutoff} and {date.today()}."

    header = f"Transactions from {cutoff} to {date.today()}, newest first:"
    return header + "\n" + "\n".join(format_transaction(tx) for tx in transactions)

def freeze_card(
    session: Session,
    card_last4: str,
    reason: Literal["lost", "stolen", "suspicious_activity", "other"],
) -> str:
    if not session.verified:
        return "Identity not verified. Cannot freeze card."

    with pool.connection() as conn:
        card = conn.execute(
            "SELECT id, status FROM cards WHERE customer_id = %s AND last4 = %s ORDER BY id",
            (session.customer_id, card_last4),
        ).fetchone()

        if card is None:
            # Card not found: list the customer's own cards so Claude can ask which one they meant.
            customer_cards = conn.execute(
                "SELECT last4, type FROM cards WHERE customer_id = %s ORDER BY id",
                (session.customer_id,),
            ).fetchall()
            if not customer_cards:
                return "This customer has no cards on file."
            card_list = ", ".join(f"{c['last4']} ({c['type']})" for c in customer_cards)
            return f"Card not found. This customer's cards end in: {card_list}."

        if card["status"] == "frozen":
            return (f"Card ending in {card_last4} is already frozen. Cards can't be unfrozen or replaced "
                    "in chat; the customer can call Tidewell Bank support at 1-800-555-0199, "
                    "Monday to Friday, 8am to 8pm.")
        if card["status"] == "cancelled":
            return (f"Card ending in {card_last4} has been cancelled and cannot be frozen. A cancelled card "
                    "can't be used, so nothing more is needed for it. To order a replacement card, the "
                    "customer can call Tidewell Bank support at 1-800-555-0199, Monday to Friday, 8am to 8pm.")
        conn.execute(
            "UPDATE cards SET status = 'frozen', freeze_reason = %s WHERE id = %s",
            (reason, card["id"]),
        )
        
        other_cards = conn.execute(
        "SELECT last4, type FROM cards WHERE customer_id = %s AND status = 'active' AND id <> %s ORDER BY id",
        (session.customer_id, card["id"]),
        ).fetchall()
    # ↑ Everything that uses conn is above this line. The block has ended, so the UPDATE is saved.

    if other_cards:
       others = "Other active cards: " + ", ".join(f"{c['last4']} ({c['type']})" for c in other_cards) + "."
    else:
       others = "This customer has no other active cards."

    session.actions_taken.append(f"Froze card ending {card_last4} (reason: {reason})")
    return (f"Card ending in {card_last4} is now frozen (reason: {reason.replace('_', ' ')}). "
           "New purchases on this card will be declined. Freezing doesn't cancel or replace the card, "
           "and the customer's accounts and money aren't affected. Cards can't be unfrozen in chat; "
           "to unfreeze or replace it, the customer can call Tidewell Bank support at 1-800-555-0199. "
           f"{others}")


def dispute_transaction(
    session: Session,
    transaction_id: int,
    reason: Literal["unauthorized", "not_received", "duplicate_charge", "incorrect_amount", "other"],
    details: str,
) -> str:
    # 1. Verified?
    if not session.verified:
        return "Identity not verified. Cannot dispute transaction."

    # 2. Exists AND belongs to this customer? Nothing about the transaction is revealed before this.
    
    if transaction_id is not None:
        
        with pool.connection() as conn:
                
            sql = """
                SELECT t.id, t.date, t.description, t.amount, t.status, t.account_id, t.type,
                    a.type AS account_type
                FROM transactions t
                JOIN accounts a ON a.id = t.account_id
                WHERE t.id = %s and a.customer_id = %s
            """
            params = [transaction_id, session.customer_id]
            transaction = conn.execute(sql, params).fetchone()

            if transaction is None:
                return f"Transaction not found for this customer."


                
                        
            dispute = conn.execute(
                "SELECT id, status FROM disputes WHERE transaction_id = %s",
                (transaction["id"],)
            ).fetchone()
    
            if dispute is not None:
                return (f"Transaction #{transaction_id} already has a dispute: "
                        f"{dispute['id']} (status: {dispute['status']}).")


            if transaction["status"] == "pending":
                    return (f"Transaction #{transaction_id} is still pending and can't be disputed until it posts, "
                            "usually within a few business days.")
            if transaction["type"] == "fee":
                    return (f"Transaction #{transaction_id} is a fee. Fees can't be disputed; "
                            "they're handled through a fee reversal request instead.")
            if transaction["amount"] >= 0:
                    return f"Transaction #{transaction_id} is money coming into the account, so there's nothing to dispute."
            if transaction["date"] < date.today() - timedelta(days=DISPUTE_WINDOW_DAYS):
                    return (f"Transaction #{transaction_id} is more than {DISPUTE_WINDOW_DAYS} days old, outside the dispute "
                            "window. Tell the customer to call Tidewell Bank support at 1-800-555-0199.")
            
# 5. File the dispute
            row = conn.execute(
            "INSERT INTO disputes (transaction_id, customer_id, reason, details) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (transaction_id, session.customer_id, reason, details),
            ).fetchone()
            dispute_id = row["id"]          # e.g. "DSP-1002"

            message = (f"Dispute {dispute_id} filed for transaction #{transaction_id} "
                        f"({transaction['description']}, {format_amount(transaction['amount'])}). Status: open. "
                        "A specialist will review it and contact the customer within 10 business days.")
            if reason == "unauthorized":
                message += " If the card used for this charge isn't frozen yet, offer to freeze it."
            session.actions_taken.append(
                f"Filed dispute {dispute_id} for transaction #{transaction_id} ({format_amount(transaction['amount'])})"
            )
            return message


def request_fee_reversal(session: Session, transaction_id: int, reason: str, confirmed: bool = False) -> str:
    # 1. Verified?
    if not session.verified:
        return "Identity not verified. Cannot reverse fees."

    with pool.connection() as conn:
        # Lock this customer's row until the block ends, so two reversal requests
        # for the same customer can't both pass the once-a-year check at the same time.
        conn.execute("SELECT id FROM customers WHERE id = %s FOR UPDATE", (session.customer_id,))

        # 2. Exists AND belongs to this customer?
        fee = conn.execute(
            """
            SELECT t.date, t.description, t.amount, t.type, t.fee_type, t.account_id,
                   a.type AS account_type
            FROM transactions t
            JOIN accounts a ON a.id = t.account_id
            WHERE t.id = %s AND a.customer_id = %s
            """,
            (transaction_id, session.customer_id),
        ).fetchone()
        if fee is None:
            return "Transaction not found for this customer."

        # 3. Is it a fee?
        if fee["type"] != "fee":
            return (f"Transaction #{transaction_id} is not a fee. If the customer believes a charge "
                    "is wrong, use dispute_transaction instead.")

        # 4. Already reversed? This check is what prevents paying out twice.
        existing = conn.execute(
            "SELECT id, reversed_on FROM fee_reversals WHERE transaction_id = %s",
            (transaction_id,),
        ).fetchone()
        if existing is not None:
            return f"Fee #{transaction_id} was already reversed ({existing['id']}) on {existing['reversed_on']}."

        # 5. Policy rules
        if fee["fee_type"] not in REVERSIBLE_FEE_TYPES:
            return (f"Transaction #{transaction_id} isn't eligible for a courtesy reversal. Only "
                    f"{' and '.join(sorted(REVERSIBLE_FEE_TYPES))} fees qualify. If the customer believes it was "
                    "charged in error, they can call Tidewell Bank support at 1-800-555-0199.")
        if fee["date"] < date.today() - timedelta(days=FEE_REVERSAL_WINDOW_DAYS):
            return (f"Transaction #{transaction_id} is more than {FEE_REVERSAL_WINDOW_DAYS} days old, "
                    "outside the reversal window.")
        recent = conn.execute(
            """
            SELECT reversed_on FROM fee_reversals
            WHERE customer_id = %s AND reversed_on >= %s
            ORDER BY reversed_on DESC
            LIMIT 1
            """,
            (session.customer_id, date.today() - timedelta(days=COURTESY_REVERSAL_PERIOD_DAYS)),
        ).fetchone()
        if recent is not None:
            next_eligible = recent["reversed_on"] + timedelta(days=COURTESY_REVERSAL_PERIOD_DAYS)
            return (f"This customer already received a courtesy reversal on {recent['reversed_on']}. "
                    f"They'll be eligible again on {next_eligible}.")

                # 6. Only checking? Report what would happen, and change nothing.
        if not confirmed:
            return (f"Fee #{transaction_id} ({fee['description']}, {format_amount(fee['amount'])}) qualifies for a "
                    f"courtesy reversal: {format_amount(-fee['amount'])} would go back to "
                    f"{format_account(fee['account_id'], fee['account_type'])}. Using it means no other courtesy "
                    "reversal for 12 months. Nothing has been changed yet. Tell the customer, and once they "
                    "agree, call this tool again with confirmed=true.")

        # 7. Reverse it: three changes, saved together when the block ends, or not at all.

        # 6. Reverse it: three changes, saved together when the block ends, or not at all.
        credit = -fee["amount"]  # the fee is stored as a negative amount
        reversal = conn.execute(
            "INSERT INTO fee_reversals (transaction_id, customer_id, amount, reason) "
            "VALUES (%s, %s, %s, %s) RETURNING id, reversed_on",
            (transaction_id, session.customer_id, credit, reason),
        ).fetchone()
        reversal_id = reversal["id"]
        # Same date the once-a-year check reads later, so both messages always agree.
        next_eligible = reversal["reversed_on"] + timedelta(days=COURTESY_REVERSAL_PERIOD_DAYS)
        new_balance = conn.execute(
            "UPDATE accounts SET balance = balance + %s WHERE id = %s RETURNING balance",
            (credit, fee["account_id"]),
        ).fetchone()["balance"]
        conn.execute(
            "INSERT INTO transactions (account_id, date, description, amount, type, status) "
            "VALUES (%s, CURRENT_DATE, %s, %s, 'fee_reversal', 'posted')",
            (fee["account_id"], f"{fee['description']} Reversal", credit),
        )
    # The with block has ended, so all three changes are saved.

    session.actions_taken.append(f"Reversed fee #{transaction_id} as {reversal_id} ({format_amount(credit)})")
    return (f"Fee reversal {reversal_id} complete: {format_amount(credit)} credited to "
            f"{format_account(fee['account_id'], fee['account_type'])}. New balance: ${new_balance:,.2f}. "
            f"This was the customer's courtesy reversal for the next 12 months; they'll be eligible "
            f"again on {next_eligible}. Any other fee they ask about before then won't qualify, but "
            f"still call this tool for it.")
def escalate_to_human(
    session: Session,
    category: Literal["fraud", "disputes", "fees", "cards", "account_access", "complaint", "other"],
    priority: Literal["urgent", "high", "normal"],
    summary: str,
    still_needed: str,
    customer_sentiment: Literal["calm", "confused", "frustrated", "angry", "worried", "distressed"],
    requested_by_customer: bool,
) -> str:
    # 1. Already escalated in this session? Return the existing ticket, no duplicates.
    if session.escalation_id is not None:
        with pool.connection() as conn:
            existing = conn.execute(
                "SELECT id, queue, priority, verified FROM escalations WHERE id = %s",   # ← two more columns
                (session.escalation_id,),
            ).fetchone()
        if existing is not None:
            return (f"This conversation was already escalated as {existing['id']} "
                    f"to the {existing['queue']} team. "
                    f"{next_step_for(existing['verified'], existing['priority'])}")      # ← the next step

    # 2. Policy in code: suspected fraud is always urgent.
    if category == "fraud":
        priority = "urgent"

    # 3. Build the ticket: facts from the session, judgment from Claude.
    with pool.connection() as conn:
        ticket_id = conn.execute(
            """
            INSERT INTO escalations (
                session_id, customer_id, verified, actions_taken,
                category, priority, summary, still_needed, customer_sentiment, requested_by_customer,
                queue
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                # From the session (reliable)
                session.id, session.customer_id, session.verified, list(session.actions_taken),
                # From Claude (judgment)
                category, priority, summary, still_needed, customer_sentiment, requested_by_customer,
                # Routing
                ESCALATION_QUEUES[category],
            ),
        ).fetchone()["id"]          # e.g. "ESC-3001"

        ticket = conn.execute(
            """
            SELECT e.*, c.full_name AS customer_name
            FROM escalations e
            LEFT JOIN customers c ON c.id = e.customer_id
            WHERE e.id = %s
            """,
            (ticket_id,),
        ).fetchone()

    # 4. Save it and link it to the session.
    session.escalation_id = ticket_id

    # 5. Show the specialist's view in the terminal.
    print(format_handoff(ticket_id, ticket))

    # 6. Tell Claude exactly what happens next.
    next_step = next_step_for(session.verified, priority)                                # ← replaces the if/else
    return (f"Escalation {ticket_id} sent to the {ESCALATION_QUEUES[category]} team with a full summary, so the customer "
            f"won't need to repeat themselves. {next_step} Give the customer the reference {ticket_id}.")

def search_help_center(query: str) -> str:
    """Search the help center and return the relevant sections, labelled for citation."""
    results = rag_search(query, k=SEARCH_TOP_K)
    print("Search scores:", [(r["id"], round(r["score"], 3)) for r in results])  # for calibrating

    relevant = [r for r in results if r["score"] >= MIN_SEARCH_SCORE]
    if not relevant:
        return ("The help center doesn't cover this question. Don't guess or use general knowledge. "
                "Tell the customer you don't have that information, and offer Tidewell Bank support "
                "at 1-800-555-0199 or to connect them with a specialist.")

    sections = [f"Source: {r['text']}" for r in relevant]  # text starts with "Article > Section"
    return ("Answer only from these help center sections. End your answer with the article title "
            "it came from, for example: (Source: Disputing a transaction)\n\n"
            + "\n\n".join(sections))


# ---------------------------------------------------------------------------
# Tool input schemas: exactly what Claude is allowed to provide
# ---------------------------------------------------------------------------

class VerifyIdentityInput(BaseModel):
    full_name: str = Field(description="Customer's full name")
    date_of_birth: date = Field(description="Date of birth in YYYY-MM-DD format")
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
    transaction_id: int = Field(
        description="ID of the transaction to dispute, from get_recent_transactions (e.g. 5006)"
    )
    reason: Literal["unauthorized", "not_received", "duplicate_charge", "incorrect_amount", "other"] = Field(
        description="Why the customer is disputing the charge"
    )
    details: str = Field(max_length=500, description="Short summary of the problem in the customer's own words")


class RequestFeeReversalInput(BaseModel):
    transaction_id: int = Field(description="ID of the fee transaction to reverse, from get_recent_transactions")
    reason: str = Field(max_length=300, description="Short summary of why the customer is asking")
    confirmed: bool = Field(
        default=False,
        description="false: only check whether the fee qualifies; nothing is changed. "
                    "true: reverse it. Use true only after the customer has agreed.",
    )


class EscalateToHumanInput(BaseModel):
    category: Literal["fraud", "disputes", "fees", "cards", "account_access", "complaint", "other"] = Field(
        description="The main topic, used to route the ticket to the right team"
    )
    priority: Literal["urgent", "high", "normal"] = Field(
        description="urgent: suspected fraud or money at immediate risk; high: very upset or vulnerable customer, "
                    "or a blocked account; normal: everything else"
    )
    summary: str = Field(
        max_length=400,
        description="Two or three sentences on what the customer needs, written for a human specialist",
    )
    still_needed: str = Field(max_length=300, description="What the specialist needs to do next")
    customer_sentiment: Literal["calm", "confused", "frustrated", "angry", "worried", "distressed"]
    requested_by_customer: bool = Field(description="True if the customer asked to speak to a person")


class SearchHelpCenterInput(BaseModel):
    query: str = Field(
        min_length=3, max_length=200,
        description=(
            "A short search query written from the customer's question, focused on the topic, "
            "e.g. 'deadline to dispute a card charge' or 'overdraft fee courtesy reversal'"
        ),
    )


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
            "Reverse an overdraft or NSF fee on the verified customer's account and credit the amount back "
            "immediately. The tool applies the courtesy-reversal policy itself: it decides whether the fee "
            "qualifies and, if not, explains why and when the customer will next be eligible. Always call it "
            "to answer whether a fee can be reversed, even if you think it won't qualify, and repeat its dates "
            "exactly; never judge eligibility or work out dates yourself. Get the fee's transaction ID from "
            "get_recent_transactions and confirm it with the customer before calling."
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
    },
        {
        "name": "search_help_center",
        "description": (
            "Search Tidewell Bank's help center for policies, fees, limits, and how-to information, "
            "for example 'how long do I have to dispute a charge?' or 'what is an NSF fee?'. "
            "Use it for any question about bank policies or procedures, even if you think you know "
            "the answer, and before explaining a policy to the customer, such as the fee reversal or "
            "dispute rules. No identity verification is needed. Answer only from the sections it "
            "returns, summarized in your own words, and cite the article title. If nothing relevant "
            "is found, don't guess."
        ),
        "input_schema": SearchHelpCenterInput.model_json_schema(),
    },
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

    if name == "search_help_center":
        args = SearchHelpCenterInput(**tool_input)
        return search_help_center(**args.model_dump())

    raise ValueError(f"No handler in run_tool for tool: {name}")