# Fake data only - never use real people's details

CUSTOMERS = {
    1: {"full_name": "Maria Chen", "date_of_birth": "1988-04-12", "card_last4": "4821"},
    2: {"full_name": "James Okafor", "date_of_birth": "1975-11-03", "card_last4": "9034"},
    3: {"full_name": "Priya Sharma", "date_of_birth": "1992-07-25", "card_last4": "1167"},
    4: {"full_name": "Liam Tremblay", "date_of_birth": "2001-01-30", "card_last4": "5580"},
    5: {"full_name": "Sofia Rossi", "date_of_birth": "1964-09-18", "card_last4": "7702"},
}

ACCOUNTS = {
    101: {"customer_id": 1, "type": "checking", "balance": 2450.75},
    102: {"customer_id": 1, "type": "savings", "balance": 10200.00},
    201: {"customer_id": 2, "type": "checking", "balance": 830.10},
    301: {"customer_id": 3, "type": "checking", "balance": 5120.40},
    302: {"customer_id": 3, "type": "savings", "balance": 25000.00},
    303: {"customer_id": 3, "type": "tfsa", "balance": 14750.25},
    401: {"customer_id": 4, "type": "checking", "balance": 12.60},
}

from datetime import date, timedelta

today = date.today()

TRANSACTIONS = {
    5001: {"account_id": 101, "date": today - timedelta(days=2),  "description": "Grocery Mart",           "amount": -86.42,   "type": "purchase", "status": "posted"},
    5002: {"account_id": 101, "date": today - timedelta(days=5),  "description": "Streamly Subscription",  "amount": -15.99,   "type": "purchase", "status": "posted"},
    5003: {"account_id": 101, "date": today - timedelta(days=1),  "description": "Coffee Corner",          "amount": -4.75,    "type": "purchase", "status": "pending"},
    5004: {"account_id": 101, "date": today - timedelta(days=12), "description": "Payroll Deposit",        "amount": 2100.00,  "type": "deposit",  "status": "posted"},
    5005: {"account_id": 102, "date": today - timedelta(days=20), "description": "Transfer from Checking", "amount": 500.00,   "type": "transfer", "status": "posted"},
    5006: {"account_id": 201, "date": today - timedelta(days=3),  "description": "ElectroWorld Online",    "amount": -649.99,  "type": "purchase", "status": "posted"},
    5007: {"account_id": 201, "date": today - timedelta(days=75), "description": "Gas Station 24",         "amount": -52.30,   "type": "purchase", "status": "posted"},
    5008: {"account_id": 301, "date": today - timedelta(days=7),  "description": "Airline Tickets",        "amount": -1210.00, "type": "purchase", "status": "posted"},
    5009: {"account_id": 401, "date": today - timedelta(days=4),  "description": "Food Delivery",          "amount": -38.50,   "type": "purchase", "status": "posted"},
    5010: {"account_id": 401, "date": today - timedelta(days=4),  "description": "Overdraft Fee",          "amount": -45.00,   "type": "fee",      "status": "posted"},
    5011: {"account_id": 401, "date": today - timedelta(days=40), "description": "Overdraft Fee",          "amount": -45.00,   "type": "fee",      "status": "posted"},
}

CARDS = {
    9001: {"customer_id": 1, "last4": "4821", "type": "debit",  "status": "active"},
    9002: {"customer_id": 1, "last4": "7310", "type": "credit", "status": "active"},
    9003: {"customer_id": 2, "last4": "9034", "type": "debit",  "status": "active"},
    9004: {"customer_id": 3, "last4": "1167", "type": "debit",  "status": "active"},
    9005: {"customer_id": 3, "last4": "2290", "type": "credit", "status": "frozen"},
    9006: {"customer_id": 4, "last4": "5580", "type": "debit",  "status": "active"},
    9007: {"customer_id": 5, "last4": "7702", "type": "credit", "status": "cancelled"},
}

DISPUTES = {
    "DSP-1001": {
        "transaction_id": 5002,
        "customer_id": 1,
        "reason": "incorrect_amount",
        "details": "Charged $15.99 but my plan is $9.99",
        "status": "open",
        "filed_on": today - timedelta(days=3),
    },
}