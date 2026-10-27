"""
Declarative field schemas for each draft template.

Why schema-driven? The schema is the single source of truth for:
  * the frontend form (React renders whatever fields it receives, so adding a
    template needs zero frontend code),
  * server-side validation (required fields, types, list sizes), and
  * defaults and help text.
A hand-coded form per template would drift out of sync with the templates.

Field types understood by the frontend and engine:
  text, textarea, date, number, money, select, checkbox,
  list    -> repeatable list of strings (facts, prayers, grounds)
  parties -> repeatable list of party objects (PARTY_FIELDS)
"""

from __future__ import annotations

import datetime as dt
from typing import Any

PARTY_FIELDS = [
    {"name": "name", "label": "Name", "type": "text", "required": True},
    {"name": "parentage", "label": "Parentage", "type": "text",
     "help": "e.g. S/o Ram Kumar, D/o..., W/o...; leave blank for companies"},
    {"name": "age", "label": "Age", "type": "number"},
    {"name": "description", "label": "Description", "type": "text",
     "help": "e.g. 'a banking company through its Branch Manager'"},
    {"name": "address", "label": "Address", "type": "textarea", "required": True},
]

ADVOCATE_FIELDS = [
    {"name": "advocate_name", "label": "Advocate name", "type": "text", "required": True},
    {"name": "advocate_enrolment", "label": "Enrolment no.", "type": "text", "help": "e.g. D/1234/2015"},
    {"name": "advocate_address", "label": "Chamber / address", "type": "textarea"},
    {"name": "advocate_contact", "label": "Phone / email", "type": "text"},
]

PLACE_DATE = [
    {"name": "place", "label": "Place", "type": "text", "required": True, "default": "New Delhi"},
    {"name": "date", "label": "Date", "type": "date", "required": True, "default": "today"},
]

TEMPLATES: dict[str, dict[str, Any]] = {
    # ------------------------------------------------------------------
    "legal_notice": {
        "title": "Legal Notice (Demand / Recovery)",
        "description": "Pre-litigation notice from an advocate on behalf of a client, demanding payment or performance.",
        "sections": [
            {"title": "Parties", "fields": [
                {"name": "senders", "label": "Client(s) / Sender(s)", "type": "parties", "required": True, "min_items": 1},
                {"name": "recipients", "label": "Addressee(s) / Noticee(s)", "type": "parties", "required": True, "min_items": 1},
            ]},
            {"title": "Notice", "fields": [
                {"name": "subject", "label": "Subject", "type": "text", "required": True,
                 "default": "Legal notice for recovery of outstanding dues"},
                {"name": "dispatch_mode", "label": "Mode of dispatch", "type": "select",
                 "options": ["Registered Post A.D.", "Speed Post", "Courier", "Email", "Hand Delivery"],
                 "default": "Registered Post A.D."},
                {"name": "facts", "label": "Facts (one per paragraph)", "type": "list", "required": True, "min_items": 1},
                {"name": "amount", "label": "Amount demanded (₹)", "type": "money",
                 "help": "Optional: leave blank for a non-monetary demand"},
                {"name": "interest_rate", "label": "Interest claimed (% p.a.)", "type": "number"},
                {"name": "demands", "label": "Demands (one per item)", "type": "list", "required": True, "min_items": 1},
                {"name": "compliance_days", "label": "Days to comply", "type": "number", "required": True, "default": 15},
                {"name": "notice_cost", "label": "Cost of notice (₹)", "type": "money", "default": 5500},
            ]},
            {"title": "Advocate", "fields": ADVOCATE_FIELDS},
            {"title": "Place & date", "fields": PLACE_DATE},
        ],
    },
    # ------------------------------------------------------------------
    "money_recovery_suit": {
        "title": "Plaint - Suit for Recovery of Money",
        "description": "Civil/commercial suit under Order VII Rule 1 CPC for recovery of a liquidated sum with interest.",
        "sections": [
            {"title": "Court", "fields": [
                {"name": "court_name", "label": "Court", "type": "text", "required": True,
                 "default": "District Judge (Commercial Court)"},
                {"name": "court_location", "label": "Court location", "type": "text", "required": True,
                 "default": "South District, Saket Courts, New Delhi"},
                {"name": "is_commercial", "label": "Commercial dispute (Commercial Courts Act, 2015)", "type": "checkbox",
                 "default": True},
                {"name": "suit_number", "label": "Suit no. (if known)", "type": "text", "default": "______ of 20__"},
            ]},
            {"title": "Parties", "fields": [
                {"name": "plaintiffs", "label": "Plaintiff(s)", "type": "parties", "required": True, "min_items": 1},
                {"name": "defendants", "label": "Defendant(s)", "type": "parties", "required": True, "min_items": 1},
            ]},
            {"title": "Claim", "fields": [
                {"name": "facts", "label": "Facts (one per paragraph)", "type": "list", "required": True, "min_items": 1},
                {"name": "principal_amount", "label": "Principal amount due (₹)", "type": "money", "required": True},
                {"name": "interest_rate", "label": "Interest rate (% p.a.)", "type": "number", "default": 12},
                {"name": "interest_from", "label": "Interest calculated from", "type": "date", "required": True},
                {"name": "pendente_lite_rate", "label": "Pendente lite & future interest (% p.a.)", "type": "number", "default": 12},
                {"name": "cause_of_action_date", "label": "Cause of action first arose on", "type": "date", "required": True},
                {"name": "jurisdiction_facts", "label": "Territorial jurisdiction basis", "type": "textarea", "required": True,
                 "default": "the Defendant resides and carries on business, and the transaction was entered into, within the territorial jurisdiction of this Hon'ble Court"},
                {"name": "mediation_done", "label": "Pre-institution mediation under Sec. 12A concluded / not applicable", "type": "select",
                 "options": ["Mediation failed (non-starter report attached)", "Urgent interim relief sought - Sec. 12A not applicable"],
                 "default": "Mediation failed (non-starter report attached)"},
                {"name": "additional_prayers", "label": "Additional prayers", "type": "list"},
            ]},
            {"title": "Advocate", "fields": ADVOCATE_FIELDS},
            {"title": "Place & date", "fields": PLACE_DATE},
        ],
    },
    # ------------------------------------------------------------------
    "bail_application": {
        "title": "Bail Application",
        "description": "Regular / anticipatory bail application under the BNSS, 2023 (CrPC equivalents cited).",
        "sections": [
            {"title": "Court & provision", "fields": [
                {"name": "court_name", "label": "Court", "type": "text", "required": True,
                 "default": "Court of Sessions Judge"},
                {"name": "court_location", "label": "Court location", "type": "text", "required": True,
                 "default": "Saket Courts, New Delhi"},
                {"name": "bail_type", "label": "Type of bail", "type": "select", "required": True,
                 "options": ["Regular bail - Section 483 BNSS (Sessions / High Court)",
                             "Regular bail - Section 480 BNSS (Magistrate)",
                             "Anticipatory bail - Section 482 BNSS"],
                 "default": "Regular bail - Section 483 BNSS (Sessions / High Court)"},
            ]},
            {"title": "Case", "fields": [
                {"name": "fir_number", "label": "FIR no.", "type": "text", "required": True},
                {"name": "fir_date", "label": "FIR date", "type": "date"},
                {"name": "police_station", "label": "Police station", "type": "text", "required": True},
                {"name": "sections", "label": "Offence sections", "type": "text", "required": True,
                 "help": "e.g. Sections 318(4), 316(2) BNS"},
                {"name": "custody_since", "label": "In custody since (regular bail)", "type": "date"},
                {"name": "chargesheet_filed", "label": "Charge-sheet filed?", "type": "checkbox", "default": False},
                {"name": "previous_applications", "label": "Previous bail applications (details, or blank for none)", "type": "textarea"},
            ]},
            {"title": "Parties", "fields": [
                {"name": "applicants", "label": "Applicant / Accused", "type": "parties", "required": True, "min_items": 1},
                {"name": "state_name", "label": "Respondent (State)", "type": "text", "required": True,
                 "default": "State (Govt. of NCT of Delhi)"},
            ]},
            {"title": "Grounds", "fields": [
                {"name": "facts", "label": "Brief facts / prosecution case", "type": "list", "required": True, "min_items": 1},
                {"name": "grounds", "label": "Grounds for bail", "type": "list", "required": True, "min_items": 1,
                 "help": "Leave the defaults or add case-specific grounds"},
                {"name": "surety_offer", "label": "Surety offered", "type": "text",
                 "default": "a personal bond with one surety of like amount to the satisfaction of this Hon'ble Court"},
            ]},
            {"title": "Advocate", "fields": ADVOCATE_FIELDS},
            {"title": "Place & date", "fields": PLACE_DATE},
        ],
    },
    # ------------------------------------------------------------------
    "affidavit": {
        "title": "Affidavit (General / Supporting)",
        "description": "Sworn affidavit of a deponent, standalone or in support of a pleading/application.",
        "sections": [
            {"title": "Matter (optional)", "fields": [
                {"name": "court_name", "label": "Court (if filed in a case)", "type": "text"},
                {"name": "case_title", "label": "Case title", "type": "text", "help": "e.g. Punjab National Bank vs Sunil Kumar"},
                {"name": "case_number", "label": "Case no.", "type": "text", "help": "e.g. CS (COMM) 233/2024"},
                {"name": "in_support_of", "label": "In support of", "type": "text", "help": "e.g. the accompanying plaint"},
            ]},
            {"title": "Deponent", "fields": [
                {"name": "deponents", "label": "Deponent", "type": "parties", "required": True, "min_items": 1, "max_items": 1},
                {"name": "deponent_capacity", "label": "Capacity", "type": "text",
                 "help": "e.g. 'the Plaintiff in the above suit' or 'Authorised Representative of ...'"},
            ]},
            {"title": "Statements", "fields": [
                {"name": "statements", "label": "Statements (one per paragraph)", "type": "list", "required": True, "min_items": 1},
            ]},
            {"title": "Place & date", "fields": PLACE_DATE},
        ],
    },
}


# Sensible starter content so the form is never blank. It doubles as a working
# demo that matches the assignment's example case.
SAMPLES: dict[str, dict[str, Any]] = {
    "legal_notice": {
        "senders": [{"name": "Punjab National Bank", "description": "a body corporate constituted under the Banking Companies (Acquisition and Transfer of Undertakings) Act, 1970, through its Branch Manager",
                     "address": "Branch Office, Saket, New Delhi - 110017"}],
        "recipients": [{"name": "Sunil Kumar", "parentage": "S/o Ram Kumar", "age": 42, "address": "H. No. 12, Malviya Nagar, New Delhi - 110017"}],
        "facts": [
            "That you, the Addressee, approached my client for a business loan and were sanctioned a term loan of ₹10,00,000 vide sanction letter dated 15.03.2022.",
            "That you executed the loan agreement, hypothecation deed and other security documents in favour of my client, undertaking to repay the loan in 36 equated monthly instalments.",
            "That you defaulted in repayment from 01.06.2023 despite repeated reminders, and the account was classified as a Non-Performing Asset.",
        ],
        "amount": 1250000, "interest_rate": 12,
        "demands": [
            "Pay the outstanding sum together with interest as stated above within the stipulated period.",
            "Pay the cost of this notice.",
        ],
    },
    "money_recovery_suit": {
        "plaintiffs": [{"name": "Punjab National Bank", "description": "a body corporate constituted under the Banking Companies (Acquisition and Transfer of Undertakings) Act, 1970, through its Branch Manager / Authorised Officer",
                        "address": "Branch Office, Saket, New Delhi - 110017"}],
        "defendants": [{"name": "Sunil Kumar", "parentage": "S/o Ram Kumar", "age": 42, "address": "H. No. 12, Malviya Nagar, New Delhi - 110017"}],
        "facts": [
            "The Defendant approached the Plaintiff bank for a business loan, and a term loan of ₹10,00,000 was sanctioned vide sanction letter dated 15.03.2022.",
            "The Defendant executed the loan agreement, hypothecation deed and other security documents in favour of the Plaintiff on 18.03.2022.",
            "The Defendant failed to repay the instalments from 01.06.2023 onwards, and the account was classified as a Non-Performing Asset on 30.09.2023.",
            "The Plaintiff issued a legal notice dated 10.01.2024 calling upon the Defendant to pay the outstanding dues, but the Defendant failed to pay or reply.",
        ],
        "principal_amount": 1000000, "interest_from": "2023-06-01", "cause_of_action_date": "2023-06-01",
    },
    "bail_application": {
        "applicants": [{"name": "Rahul Sharma", "parentage": "S/o Mahesh Sharma", "age": 29, "address": "B-45, Sheikh Sarai Phase I, New Delhi - 110017"}],
        "fir_number": "245/2026", "fir_date": "2026-08-14", "police_station": "Malviya Nagar", "sections": "Sections 318(4) and 316(2) BNS",
        "custody_since": "2026-08-20",
        "facts": [
            "As per the prosecution, the complainant alleges that the Applicant received ₹3,50,000 towards supply of goods which were not delivered.",
            "The Applicant was arrested on the date mentioned above and has been in judicial custody since then.",
        ],
        "grounds": [
            "The Applicant is innocent and has been falsely implicated; the dispute is essentially civil in nature.",
            "The investigation is complete as far as the Applicant is concerned, and no recovery is to be effected from him.",
            "The Applicant is a permanent resident of Delhi with deep roots in society, and there is no likelihood of him fleeing from justice.",
            "The Applicant has no previous criminal antecedents.",
            "The offences alleged are punishable with imprisonment of less than seven years, and the trial is likely to take considerable time.",
            "The Applicant undertakes not to tamper with evidence or influence any witness and to abide by all conditions imposed by this Hon'ble Court.",
        ],
    },
    "affidavit": {
        "case_title": "Punjab National Bank vs Sunil Kumar", "case_number": "CS (COMM) 233/2024",
        "court_name": "District Judge (Commercial Court), South District, Saket Courts, New Delhi",
        "in_support_of": "the accompanying plaint",
        "deponents": [{"name": "Amit Verma", "parentage": "S/o Late Suresh Verma", "age": 45,
                       "description": "Branch Manager, Punjab National Bank", "address": "Branch Office, Saket, New Delhi - 110017"}],
        "deponent_capacity": "the Branch Manager and Authorised Representative of the Plaintiff bank, and conversant with the facts of the case",
        "statements": [
            "That the accompanying plaint has been drafted by my counsel under my instructions and its contents have been read over and explained to me in vernacular.",
            "That the contents of the accompanying plaint are true and correct to my knowledge, based on the records maintained by the Plaintiff in the ordinary course of business.",
            "That the documents filed along with the plaint are true copies of their originals.",
        ],
    },
}

COMMON_SAMPLE = {
    "advocate_name": "Adv. Priya Mehta", "advocate_enrolment": "D/1234/2015",
    "advocate_address": "Chamber No. 512, Saket Courts, New Delhi - 110017",
    "advocate_contact": "+91 98100 00000",
}


def defaults_for(template_id: str) -> dict[str, Any]:
    """Schema defaults + sample content, resolved ('today' -> ISO date)."""
    out: dict[str, Any] = {}
    for section in TEMPLATES[template_id]["sections"]:
        for f in section["fields"]:
            if "default" in f:
                out[f["name"]] = dt.date.today().isoformat() if f["default"] == "today" else f["default"]
    out.update(COMMON_SAMPLE)
    out.update(SAMPLES.get(template_id, {}))
    return out


def public_schema() -> list[dict[str, Any]]:
    return [
        {"id": tid, "title": t["title"], "description": t["description"], "sections": t["sections"],
         "party_fields": PARTY_FIELDS, "sample": defaults_for(tid)}
        for tid, t in TEMPLATES.items()
    ]
