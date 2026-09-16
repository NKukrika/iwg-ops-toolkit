"""Mandatory-detail check: does a ticket carry what the desk needs to work it?

Owner rule, 16 Sep 2026. Requirements depend on the kind of issue:

    Bookings         Company, Centre, Booking reference
    Payments         Company, Centre, card first 6 + last 4,
                     and an invoice number IF they are paying an invoice
    Invoices         Company, Centre, Invoice number
    Internal/Staff   Email of the affected user

A ticket missing any of these is TAGGED `MissingInformation`. It is NOT
cancelled: the owner reviews the tagged set first, and cancellation follows only
once they have checked it. This module reports the gap and drafts the comment to
post when that decision is made; it never cancels or posts anything itself.

Categories outside those four kinds carry no mandatory-detail requirement and
are never flagged. SOA was dropped from the invoice kind on 16 Sep.

    from completeness import check, comment_for
    miss = check(short_desc, description, category)
    if miss:
        text = comment_for(miss)
"""
import re


def _c(p):
    return re.compile(p, re.I)


# ---------------------------------------------------------------- kinds
BOOKING_CATS = ("Bookings (Products)", "Bookings (Products) - Short Stay")
PAYMENT_CATS = ("Payments Registration", "Payments - Credit Card",
                "Payments - Direct Debit")
# SOA dropped by owner ruling 16 Sep -- statement/balance reconciliation does
# not always cite an invoice, so it carries no mandatory-detail requirement.
INVOICE_CATS = ("Invoicing",)
# Staff-facing work. "Internal/Staff" is about who is affected rather than the
# category, so the category list is the reliable part and INTERNAL_SIGNAL widens
# it to tickets raised by a centre team about their own access.
STAFF_CATS = ("Staff - Attendance and Timeoff", "Roles and Permissions")
INTERNAL_SIGNAL = [
    _c(r"@(?:iwgplc|regus|spaces)\.com"),
    _c(r"\b(?:centre|center)\s+team\s+member\b"),
    _c(r"\bstaff\s+(?:member|mode\s+user)\b"),
    _c(r"\bactive\s+users?\b"),
]

# ---------------------------------------------------------------- detectors
COMPANY = [
    _c(r"\b(?:company|account|customer|client)\s*(?:name|id|number|no|ref|#)\s*[:\-#]"),
    _c(r"\bcompany\s*[:\-]"),
    _c(r"\baccount\s*[:\-]\s*\w"),
    _c(r"\btitan\s*(?:id|ref(?:erence)?)\s*[:\-#]?\s*\d{5,}"),
    _c(r"\b\d{7,9}\s*[-–—]\s*[A-Za-z]"),
    _c(r"\bac\s*[-–—:]\s*\d{6,}"),
    _c(r"\(\s*\d{7,9}\s*\)"),
    _c(r"\baccount\s+\d{6,}"),
    _c(r"\b\d{6,9}\s*[,:]\s*[A-Z]"),
    _c(r"\bfor\s+(?:the\s+)?(?:client|customer|company)\s+[A-Z]"),
]

CENTRE = [
    _c(r"\bcent(?:re|er)\s*(?:name|number|no|#)?\s*[:\-#/]\s*\S"),
    _c(r"\bcent(?:re|er)\s+\d{3,5}\b"),
    _c(r"\bcentre?\s*(?:nr|num)\.?\s*\d+"),
    _c(r"\b(?:regus|spaces|hq|signature)\s+[\w'’\-]+"),
    _c(r"\bcent(?:re|er)\s*#\s*\d+"),
    _c(r"[\w'’\-]+\s+cent(?:re|er)\b"),
    _c(r"\bat\s+the\s+[\w\s\-]{3,30}\s+cent(?:re|er)\b"),
]

BOOKING_REF = [
    _c(r"\bbooking\s*(?:ref(?:erence)?|no|number|id)\s*(?:number)?\s*[:\-#]?\s*\d{6,}"),
    _c(r"\bbooking\s+\d{8,}"),
    _c(r"\bref\s*[:\-#]?\s*\d{9,}"),
]

CARD = [
    _c(r"\b(?:first\s*)?6\s*[-\s]?digits?\s*[:\-]?\s*\d{6}\b"),
    _c(r"\blast\s*4\s*[-\s]?digits?\s*[:\-]?\s*\d{4}\b"),
    _c(r"\b\d{6}\s*\*+\s*\d{4}\b"),
    _c(r"\b\d{4}\s\d{2}\*{3,}\d{4}\b"),
]

INVOICE = [
    _c(r"\b\d{3,5}\s*[/_\-]\s*\d{2,6}(?:\s*[-_/]\s*\d{1,6})?\s*(?:INV|CN|STM|CSTM)?\b"),
    _c(r"\binvoice\s*(?:number|no|ref|#)\s*[:\-]?\s*\S+"),
    _c(r"\b(?:INV|CN|STM)\d{3,}\b"),
]

EMAIL = [_c(r"[\w.\-+]+@[\w\-]+\.[\w.\-]+")]

# "invoice# if they are trying to pay the invoice" -- only then is it mandatory
PAYING_INVOICE = [
    _c(r"\b(?:pay|paying|paid|payment\s+of)\s+(?:the\s+|my\s+|this\s+|an?\s+)?invoice"),
    _c(r"\binvoice\s+payment\b"),
    _c(r"\bunable\s+to\s+pay\b"),
    _c(r"\bcannot\s+pay\b"),
]

LABEL = {
    "company": "the company name or account number",
    "centre": "the centre name or number",
    "booking ref": "the booking reference",
    "card 6+4": "the first 6 and last 4 digits of the card",
    "invoice number": "the invoice number",
    "email": "the email address of the affected user",
}


def kind(short_desc, description, category):
    """Which set of mandatory details applies, or None."""
    text = "%s\n%s" % (short_desc or "", description or "")
    if category in STAFF_CATS or any(p.search(text) for p in INTERNAL_SIGNAL):
        return "internal"
    if category in BOOKING_CATS:
        return "bookings"
    if category in PAYMENT_CATS:
        return "payments"
    if category in INVOICE_CATS:
        return "invoices"
    return None


def check(short_desc, description, category=None):
    """Mandatory details this ticket is missing, as a list. Empty when the
    category carries no requirement."""
    text = "%s\n%s" % (short_desc or "", description or "")
    k = kind(short_desc, description, category)
    if k is None:
        return []

    def has(pats):
        return any(p.search(text) for p in pats)

    missing = []
    if k == "internal":
        if not has(EMAIL):
            missing.append("email")
        return missing

    if not has(COMPANY):
        missing.append("company")
    if not has(CENTRE):
        missing.append("centre")
    if k == "bookings" and not has(BOOKING_REF):
        missing.append("booking ref")
    if k == "payments":
        if not has(CARD):
            missing.append("card 6+4")
        # Only mandatory when the ticket is about paying an invoice.
        if has(PAYING_INVOICE) and not has(INVOICE):
            missing.append("invoice number")
    if k == "invoices" and not has(INVOICE):
        missing.append("invoice number")
    return missing


def comment_for(missing):
    """The comment to post if and when the ticket is cancelled."""
    if not missing:
        return ""
    items = "\n".join("  - %s" % LABEL.get(m, m) for m in missing)
    return (
        "Hello,\n\n"
        "Thank you for raising this ticket. We are unable to investigate it as it "
        "stands, because the following mandatory details are missing from the "
        "description:\n\n"
        "%s\n\n"
        "Without these we cannot identify the account or trace the transaction, so "
        "this incident is being cancelled.\n\n"
        "Please raise a new ticket including the details above and we will pick it "
        "up straight away.\n\n"
        "Many thanks" % items
    )
