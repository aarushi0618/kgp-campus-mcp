"""Configuration for all Gymkhana data sources."""

GYMKHANA_BASE = "https://gymkhana.iitkgp.ac.in"

# ---- LLM-based sources (HTML pages needing Gemini) ----
GYMKHANA_LLM_SECTIONS = {
    "awards": {
        "url": f"{GYMKHANA_BASE}/awards",
        "entity_type": "notice",
        "schema_description": (
            "Extract every award recipient or inducted person. For each: "
            "name, achievement/award name, year (if shown), category."
        ),
        "example_json": (
            '{"name": "Pravalika Das", "achievement": "Institute Blue", '
            '"year": "2025", "category": "awards"}'
        ),
        "ttl": 2592000,  # 30 days
    },
    "gc_results": {
        "url": f"{GYMKHANA_BASE}/results/gc",
        "entity_type": "notice",
        "schema_description": (
            "Extract GC (General Championship) results. For each: "
            "hall/team name, event/sport, position/rank, year if shown."
        ),
        "example_json": (
            '{"hall": "Nehru Hall", "event": "Cricket", "position": "1st"}'
        ),
        "ttl": 2592000,
    },
    "interiit_results": {
        "url": f"{GYMKHANA_BASE}/results/interiit",
        "entity_type": "notice",
        "schema_description": (
            "Extract Inter-IIT results. For each: sport/event, IIT name, "
            "medal/position, year if shown."
        ),
        "example_json": (
            '{"sport": "Basketball", "iit": "IIT Kharagpur", "position": "Gold"}'
        ),
        "ttl": 2592000,
    },
    "societies": {
        "url": f"{GYMKHANA_BASE}/societies",
        "entity_type": "location",
        "schema_description": (
            "Extract every student society. For each: name, category "
            "(Technology / Social & Cultural / Sports / Welfare / Independent / Cell), "
            "and one-line description if available."
        ),
        "example_json": (
            '{"name": "Kharagpur Open Source Society (KOSS)", '
            '"category": "Independent", "description": "Open-source community"}'
        ),
        "ttl": 604800,  # 7 days
    },
    "committee_tech": {
        "url": f"{GYMKHANA_BASE}/committees/tech",
        "entity_type": "location",
        "schema_description": (
            "Extract every society under the Technology Committee: name, description."
        ),
        "example_json": '{"name": "KOSS", "description": "Open source community"}',
        "ttl": 604800,
    },
    "committee_socult": {
        "url": f"{GYMKHANA_BASE}/committees/socult",
        "entity_type": "location",
        "schema_description": "Extract every society under the Social & Cultural Committee.",
        "example_json": '{"name": "Encore", "description": "Dramatics society"}',
        "ttl": 604800,
    },
    "committee_sports": {
        "url": f"{GYMKHANA_BASE}/committees/sports",
        "entity_type": "location",
        "schema_description": "Extract every society under the Sports Committee.",
        "example_json": '{"name": "Cricket Team", "description": "Inter-hall cricket"}',
        "ttl": 604800,
    },
    "committee_welfare": {
        "url": f"{GYMKHANA_BASE}/committees/welfare",
        "entity_type": "location",
        "schema_description": "Extract every society under the Students' Welfare Committee.",
        "example_json": '{"name": "SWG", "description": "Student Welfare Group"}',
        "ttl": 604800,
    },
    "elections": {
        "url": f"{GYMKHANA_BASE}/elections",
        "entity_type": "notice",
        "schema_description": (
            "Extract all election content: title, description, dates, PDF links."
        ),
        "example_json": (
            '{"title": "Election Date", "description": "5th April 2026", '
            '"pdf_link": "https://..."}'
        ),
        "ttl": 3600,
    },
    "nominations": {
        "url": f"{GYMKHANA_BASE}/nominations",
        "entity_type": "notice",
        "schema_description": (
            "Extract every nominated office bearer: name, position, society/hall."
        ),
        "example_json": (
            '{"name": "Rahul Kumar", "position": "President", "society": "TSG"}'
        ),
        "ttl": 604800,
    },
}