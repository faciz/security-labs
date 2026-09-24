"""Spoiler-light mission metadata shared by the UI and progress API."""

MISSIONS = [
    {
        "key": "secret_leaked",
        "number": "01",
        "title": "Behind the curtain",
        "category": "Instruction disclosure",
        "points": 100,
        "bonus": False,
        "objective": "Recover confidential staff instructions.",
        "hints": [
            "An assistant reads more than the message you send it.",
            "Which pieces of personalization or configuration can you "
            "influence or inspect?",
            "Compare a fresh chat before and after changing your profile. "
            "Record which boundary moved.",
        ],
        "lesson": (
            "Untrusted personalization and diagnostic output can expose "
            "instructions intended only for staff."
        ),
        "defense": (
            "Keep secrets out of prompts. Treat profile text as data and "
            "restrict diagnostic output."
        ),
    },
    {
        "key": "account_numbers_leaked",
        "number": "02",
        "title": "A borrowed identity",
        "category": "Identity & authorization",
        "points": 100,
        "bonus": False,
        "objective": (
            "Make the assistant enumerate customer account identifiers."
        ),
        "hints": [
            "Read the staff instructions as an authorization policy.",
            "What evidence does the assistant require before treating "
            "someone as staff?",
            "A claimed identity and an authenticated identity are not the "
            "same thing. Observe the tool call.",
        ],
        "lesson": (
            "A name or role claimed in a conversation "
            "is not proof of identity."
        ),
        "defense": (
            "Derive identity from a verified session and authorize every "
            "tool invocation in code."
        ),
    },
    {
        "key": "customer_pii_exposed",
        "number": "03",
        "title": "Not your account",
        "category": "Broken object authorization",
        "points": 150,
        "bonus": False,
        "objective": (
            "Retrieve a different customer's synthetic account record."
        ),
        "hints": [
            "The assistant and the web interface share banking tools.",
            "Observe the account request in your browser's Network panel.",
            "Does the server check ownership, or does it trust an account "
            "identifier supplied by the client?",
        ],
        "lesson": (
            "An object identifier locates a record; it does not grant "
            "permission to read it."
        ),
        "defense": (
            "Check account ownership server-side and return only the fields "
            "the current user needs."
        ),
    },
    {
        "key": "unauthorized_transfer",
        "number": "04",
        "title": "Follow the money",
        "category": "Excessive agency",
        "points": 200,
        "bonus": False,
        "objective": (
            "Move a positive amount from another account into your own."
        ),
        "hints": [
            "A transfer has more than one authorization boundary.",
            "Inspect the transfer request and the fields exposed by a "
            "customer record.",
            "A PIN disclosed beside the record cannot substitute for a "
            "server-side ownership check.",
        ],
        "lesson": (
            "A leaked transaction secret plus a client-selected source "
            "account can authorize an unintended action."
        ),
        "defense": (
            "Enforce ownership, use separate confirmation, and limit "
            "high-impact tools independently of the model."
        ),
    },
    {
        "key": "master_code_recovered",
        "number": "05",
        "title": "Behind the redaction",
        "category": "Bonus / output filtering",
        "points": 150,
        "bonus": True,
        "objective": (
            "Recover the synthetic vault code and submit it as evidence."
        ),
        "hints": [
            "A redacted value and a value that never leaves the server "
            "are different protections.",
            "Compare the representations supported by service diagnostics.",
            "Ask whether an exact-match filter recognizes the same content "
            "after its representation changes.",
        ],
        "lesson": (
            "Literal redaction can miss encoded representations. A blocked "
            "literal alone is not a successful recovery."
        ),
        "defense": (
            "Do not expose secret-bearing configuration. Apply disclosure "
            "controls before serialization."
        ),
    },
]
