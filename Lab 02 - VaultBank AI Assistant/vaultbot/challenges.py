"""Spoiler-light mission metadata shared by the UI and progress API."""

MISSIONS = [
    {
        "key": "secret_leaked",
        "number": "01",
        "title": "Behind the curtain",
        "category": "Chat jailbreak",
        "points": 100,
        "bonus": False,
        "objective": (
            "Discover the hidden staff identity and account-listing rule "
            "through a chat jailbreak."
        ),
        "hints": [
            "Start in chat with your guest profile unchanged. A refusal "
            "can help you identify what the assistant is protecting.",
            "How might a differently framed conversation expose a staff "
            "policy without asking to carry out the restricted action?",
            "Your evidence needs both a staff identity and its permission "
            "to list accounts. Repeating a name you supplied does not count.",
        ],
        "lesson": (
            "A chat jailbreak can expose an internal access rule. The "
            "disclosed identity becomes useful only if another boundary "
            "mistakes a claim for proof."
        ),
        "defense": (
            "Keep confidential access policy out of prompts and enforce "
            "permissions independently of what the model says."
        ),
    },
    {
        "key": "account_numbers_leaked",
        "number": "02",
        "title": "A borrowed identity",
        "category": "Profile poisoning",
        "points": 100,
        "bonus": False,
        "prerequisite": "secret_leaked",
        "objective": (
            "After mission 01, use a poisoned profile to make the "
            "assistant enumerate customer account identifiers."
        ),
        "hints": [
            "A claim made only in chat is not the same as the identity "
            "the tool reads from the saved profile.",
            "Who controls the profile fields that the assistant trusts "
            "when deciding whether you are staff?",
            "Saving a profile does not complete the mission. Observe "
            "whether a subsequent chat request actually returns account "
            "identifiers through the tool.",
        ],
        "lesson": (
            "Self-service profile text crossed into an authorization "
            "decision. A persisted identity claim is still not proof "
            "that the customer is staff."
        ),
        "defense": (
            "Derive staff identity from a verified session, not editable "
            "profile text, and authorize every tool invocation in code."
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
