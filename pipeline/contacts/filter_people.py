"""Keep only people shown in a contact role (family support, director, founder, coordinator ...).

Board members and advisors without a contact role are dropped from data/derived/contacts/people.json.
Run after pipeline/contacts/people.py:  python3 pipeline/contacts/filter_people.py
"""

import json
import pathlib
import re

PEOPLE = pathlib.Path(__file__).resolve().parents[2] / "data" / "derived" / "contacts" / "people.json"
CONTACT_ROLE = re.compile(
    r"family|support|liaison|outreach|contact|coordinator|director|executive|founder|president|chair|ceo|"
    r"manager|officer|programs?|patient|parent|navigator|helpline|secretary|administrator|community",
    re.I,
)
BOARD_ONLY = re.compile(
    r"^\s*(board member|member of the board|trustee|director of the board|board of directors|advisor|adviser)\s*$", re.I
)


def is_contact(person):
    role = person.get("role") or ""
    return bool(CONTACT_ROLE.search(role)) and not BOARD_ONLY.match(role)


def main():
    data = json.loads(PEOPLE.read_text())
    people = data.get("people", data) if isinstance(data, dict) and "people" in data else data
    kept = dropped = 0
    for org in list(people):
        contacts = [p for p in people[org] if is_contact(p)]
        dropped += len(people[org]) - len(contacts)
        kept += len(contacts)
        if contacts:
            people[org] = contacts
        else:
            del people[org]
    PEOPLE.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    print(f"kept {kept} contact people at {len(people)} orgs; dropped {dropped}")


if __name__ == "__main__":
    main()
