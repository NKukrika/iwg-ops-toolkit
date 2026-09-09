"""Triage runner for the IWG/Regus ServiceNow batches.

All matching logic lives in reference/classify.py -- this script only assembles
the workbook. The process is documented in README.md and the
`ticket-triage-master` skill; the reasoning behind each rule, and every approach
that was measured and rejected, is in reference/BENCHMARK.md.

    python run_triage.py "path/to/triage export.xlsx" [output.xlsx]
    python measure.py          # ALWAYS run this after changing any reference file

PER-RUN CONFIG is the CLUSTERS and MANUAL_NAME dicts below. Both are
deliberately hand-maintained: a cluster is a claim that several tickets are the
same issue, and a manual name is a judgement about a free-form ticket. Neither
should be generated automatically.
"""
import sys, os, re, glob, datetime
sys.path.insert(0, "reference")
import pandas as pd
import classify as C

SRC = sys.argv[1] if len(sys.argv) > 1 else None
if not SRC:
    sys.exit("usage: python run_triage.py <ticket-export.xlsx> [output.xlsx]\n"
             "       run from the workspace root (the folder holding reference/ and runs/)")
OUT = sys.argv[2] if len(sys.argv) > 2 else \
    f"runs/Triage_{datetime.date.today():%Y-%m-%d}.xlsx"
JIRA_NOTE = "No matching JIRA found"

# Checked against JIRA on 21 Aug via the Atlassian connector. Keyed by ticket.
# NOTE for future runs: the connector's `fields` parameter is NOT honoured, so
# every issue returns its full description. Use searchResultMode="count" first
# and only fetch when the count is small, or the response blows the token limit.
JIRA_FINDINGS = {
    "INC0768814": "TTN-143719 - Fixed, Ready For Release, fix version R26.08.01 (dated 2026-08-13, NOT YET RELEASED). '[ENHANCE-9600] Prevent back-dated charges and double-billing on occupancy step amendments'. Root cause: OccupancyStepId mismatch in MandatoryRecurringServiceHelper.AddMandatoryServices creates a fresh backdated ServiceSale with no billing history, so the customer is back-billed for periods already invoiced. QA passed 17 Aug, UAT passed 20 Aug.",
    "INC0768932": "TTN-143719 symptom 2 (double-billing on occupant change) - same defect, Fixed and awaiting the R26.08.01 release. In scope: Kitchen Amenities, Beverages, Unlimited Coffee. The JIRA states Operations is patching this monthly with manual credit notes, which matches the AHD comment on this ticket that it affects multiple clients.",
    "INC0768827": "PAPI-80621 pattern - '[WITH L2] [OOMA] Customer is requesting the change of DID number', status Pending. That ticket records the portal DID not matching Cerebro because the number was PURGED there, and is explicitly logged 'for track purpose only, not for Proton team'. Consistent with these being data corrections rather than a code defect.",
    "INC0768872": "PAPI-80621 pattern - see INC0768827.",
    "INC0768916": "No matching JIRA found. CEN has two open amend-agreement bugs - CEN-49075 (renewal price incorrect after repeated saves, New) and CEN-46754 (RENEWBOOKING action failed even when renewal succeeds, Blocked) - but neither is the production 'error occurred when trying to submit your request' failure. Nothing is tracking this 9-ticket cluster.",
}

cats, masters, kbas = C.load_reference()
groups, signals = C.load_groups()
rcs = C.load_root_causes()
L = C.load_learned_groups()
priors = C.load_rc_priors()
kidx, midx = C.build_kba_index(kbas), C.build_master_index(masters)
mst = {m["Master Name"]: m.get("MST Tag", "") for m in masters}

src = pd.read_excel(SRC)
gcol = C.find_group_column(src.columns)

# The daily batch export carries Assignment group and Impact. The In Progress /
# backlog export does not, and silently produces a whole run of rule-derived
# groups and blank priorities that look like ordinary output. Say so once, up
# front, because both columns change what the run can be trusted for.
if not gcol:
    print("  ! no assignment-group column in this export.\n"
          "    Routing is RULE-DERIVED for every row -- the 'sheet wins' rule has\n"
          "    nothing to defer to, so treat the group column as a suggestion.")
if "Impact" not in src.columns:
    print("  ! no Impact column in this export.\n"
          "    Priority cannot be gridded; rows fall back to the default. Impact is\n"
          "    a human decision, so do not read these grades as triaged.")


def lvl(v):
    m = re.match(r"\s*(\d)", str(v))
    return int(m.group(1)) if m else None


# Rule 2 has to hold ACROSS runs, not just within one. A carried-over ticket
# keeps the name it was already issued -- redrafting produced "Global Protect VPN
# is not working" on 13 Aug and "...access issue" on 14 Aug for the same ticket.
def prior_names(runs_dir="runs", exclude=(), same_date=None):
    """Names issued by EARLIER runs. Workbooks for the same date as this output
    are skipped: they are superseded drafts of the run being produced now, not
    history. Without this, a name written by a first pass -- including a bad one
    the current pass was fixing -- is carried straight back in, because PRIOR
    outranks the drafted name. INC0770701 kept the title "Error - Something went
    wrong" through two rebuilds for exactly this reason."""
    out = {}
    for f in sorted(glob.glob(os.path.join(runs_dir, "*.xlsx")), key=os.path.getmtime):
        base = os.path.basename(f)
        if base.startswith("~$") or os.path.abspath(f) in exclude:
            continue
        if same_date and same_date in base:
            continue
        try:
            d = pd.read_excel(f, sheet_name="Finished Triage")
        except Exception:
            continue
        col = next((c for c in d.columns if "hort" in c and "escription" in c), None)
        if not col or "TicketID" not in d.columns:
            continue
        for _, r in d.iterrows():
            v = str(r[col]).strip()
            if v and v.lower() != "nan":
                out[r["TicketID"]] = v
    return out


_m = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(OUT))
PRIOR = prior_names(exclude={os.path.abspath(OUT)},
                    same_date=_m.group(1) if _m else None)

# A cluster may ONLY exist for a symptom with no master in the registry. Check
# every unmatched ticket against all 46 masters first -- one run proposed a new
# cluster for six card tickets that already had masters.
CLUSTERS = {
    "[SOA] Invoices paid in D365 still showing unpaid in MyRegus": {
        "cat": "SOA", "ids": [],
        "terms": "mark invoices as paid; showing as unpaid; already allocated in dyn; still shows unpaid after settlement; not reflecting in myregus; already reflected in dyn; payment adjustment",
        "note": "AT 7 AND GROWING. TWO DECISIONS OVERDUE: (1) the name says 'Invoices paid ... showing unpaid' but most members are payments and vouchers that never arrived at all - rename or split; (2) the registry master [SOA] Balance Mismatch competes for these tickets and has NO MST tag - allocate one and fold the cluster in, or scope the master's keywords.",
    },
    "[Renewals] Error submitting renewal team request in TeamHub": {
        "cat": "Renewals", "ids": [],
        "terms": "submit your request; renewal team; send to customer; error occurred when trying to submit; an error occured while trying to submit your request; central renewal support; crt ticket",
        "note": "NOW 10. Owner 8 Sep: the Renewals category is correct and a JIRA ticket already exists for this - the 21 Aug check that found none is superseded (key not supplied). Nine reporters across six batches. The script trips at n > 10.",
    },
    # Sibling of the above but a distinct symptom: the amendment ITSELF errors or
    # freezes, rather than the handoff to the renewals team failing.
    "[Renewals] Error when amending an agreement in TeamHub": {
        "cat": "Renewals",
        "ids": [],
        "terms": "error occured when performing amend agreement; error occurred when performing amend agreement; unable to send renewal osa; teamhub freezes; something went wrong, please log an it ticket via teamhub; move agreement; renew recent termination; error occurred while renewing recent termination",
        "note": "NOW 5. INC0769090 (23 Aug) errors on Company > Amend agreement > Select booking(s) > Renew recent termination - the amendment itself failing, NOT the handoff to the renewals team, so it belongs here and not in the 9-count sibling above. Placing it there would have falsely crossed the 10 threshold. CATEGORY IS STILL AN OPEN QUESTION - bracketed [Renewals] provisionally. A resolved ticket worded 'Not able to amend agreement' is tagged XC (Product and Services), while the 14 Aug review put TeamHub amend/renew errors under Renewals. Also spans renewal amendments (INC0768485, INC0768499) and office/country moves (INC0768359, INC0768524) - may want splitting.",
    },
    # Five tickets asking for a duplicate or invalid posting in MyRegus to be
    # reversed or zeroed out. Distinct from the D365-sync cluster: there the
    # record never arrived, here it arrived twice or wrongly. The registry master
    # [SOA] Balance Mismatch competes for these and still has no MST tag.
    "[SOA] Duplicate or invalid posting in MyRegus needs reversing": {
        "cat": "SOA",
        "ids": ["INC0771866"],
        "terms": "duplicate posting; duplicate payment in myregus; reversing the invalid; invalid refund posting; duplicate refund; zero-out the amount; remove or zero-out; reflecting twice; posted twice",
        "note": "Five across three batches, all finance corrections in MyRegus. Sibling of the D365-sync cluster but the opposite direction - the record arrived twice or wrongly rather than not at all. If you would rather treat these as routine finance requests than defects, they can come off the tally.",
    },
    # Printer OUTPUT faults. The owner confirmed on 17 Aug that a printer which
    # authenticates but does not print is NOT Quick Access - Quick Access covers
    # getting TO the printer. There is still no category for print output, so
    # these carry UNCATEGORISED and cannot be fully tagged.
    "[XC (Product and Services)] Printer accepts the job but nothing prints": {
        "cat": "XC (Product and Services)",
        "ids": [],
        "terms": "nothing prints; never prints; sits on a loading screen; shows the job as completed; print jobs send successfully",
        "note": "Three tickets, no category. INC0767028 classifies as Quick Access only because the reporter mentions refreshing WKP from MyRegus Quick Access as a troubleshooting step - the fault is print output. This is the fourth printer ticket overall and the category decision is still open.",
    },
    # Two tickets both citing TTN-143719, the KA backbill defect.
    "[Invoicing] KA backbill cannot be removed (TTN-143719)": {
        "cat": "Invoicing",
        "ids": [],
        "terms": "backbilled ka; ka backbill; backbilled ka cannot be removed; unnecessary ka fee; ka fee",
        "note": "CONFIRMED IN JIRA: TTN-143719 is Fixed and Ready For Release under R26.08.01, dated 2026-08-13 but NOT YET RELEASED. Both tickets are children of it and the fix is upstream - they should not be worked individually. INC0768932 (19 Aug) is the same defect's second symptom. Expect more until R26.08.01 ships.",
    },
    "[Bookings (Products)] Cannot rollback a booking terminated while provisional": {
        "cat": "Bookings (Products)", "ids": [],
        "terms": "rollback the termination; cannot rollback; unable to rollback; terminated while provisional; terminated while it was still provisional; greyed out; grayed out; edit/roll back option; rollback the renewal; modify booking and edit booking are grayed out",
        "note": "NOW 5. Both 26 Aug tickets cite the SAME booking reference 172355166 - INC0769483 (MTM renewal, needs the missed invoice raised) and INC0769513 (Office 104, different company name). They may be one occurrence reported twice rather than two, which would make the real count 4. Counted as two and flagged: the cluster is far from the threshold, so nothing turns on it yet, but resolve before it approaches 10.",
    },
    "[Bookings (Products) - Short Stay] Meeting room booking does not complete at the payment step": {
        "cat": "Bookings (Products) - Short Stay", "ids": [],
        "terms": "freeze at the payment step; freezes at the payment step; booking could not be finished; unable to complete meeting room booking; reservation does not complete",
        "note": "INC0768123 reports 'a lot of customers and non-customers' affected. INC0768224 may be the same fault one step earlier but presents as a card rejection, so it is not counted here.",
    },
    # Owner ruling, 14 Aug: NOT a child of MST-76060. Being unable to SEE the
    # Preview OSA screen is a different fault from being unable to SEND from it.
    "[Bookings (Products)] Unable to confirm booking in Staff Mode": {
        "cat": "Bookings (Products)", "ids": [],
        "terms": "confirm booking; cannot be confirmed; booking cannot be completed; event space booking; after-hours meeting room; staff mode",
        "note": "INC0768738 is an event space booking failing in Customer Portal Staff Mode - the same flow this cluster tracks.",
    },
    "[Bookings (Products)] Unable to see Preview OSA screen for Move Office": {
        "cat": "Bookings (Products)", "ids": [],
        "terms": "preview osa screen; move office; confirmation screen did not appear; unable to see preview",
        "note": "Owner confirmed this is separate from MST-76060.",
    },
    # RENAMED 17 Aug from [Login]. The reviewer categorised INC0768179 as Quick
    # Access, so the cluster bracket follows -- when a clustered ticket's category
    # disagrees with the cluster name, the cluster name is the likely error.
    "[Quick Access] WorldKey PIN rejected as invalid on HP Cloud Printing portal": {
        "cat": "Quick Access", "ids": [],
        "terms": "world key pin; worldkey pin; wkp; credentials invalid; worldkey pin not working",
        "note": "RENAMED from [Login] on 17 Aug. The 5 earlier tickets were tagged Login and need retagging if you adopt the rename.",
    },
    "[Invoicing] Credit note requested for an incorrectly billed charge": {
        "cat": "Invoicing", "ids": [],
        "terms": "issuance of the corresponding credit note; assistance with a credit note; billed twice; late payment fee; incorrectly generated; authorization from the franchise owner",
        "note": "Both carry franchise-owner authorisation and both correct an incorrect charge rather than report a portal fault. If these are routine finance requests they may not belong on this tally - your call.",
    },
}
CLUSTER_OF = {t: name for name, c in CLUSTERS.items() for t in c["ids"]}

# Free-form tickets pasted from email carry no usable symptom line, so the name
# is written from the body rather than drafted mechanically. UNCATEGORISED marks
# a name that cannot be finalised until the category is decided.
MANUAL_NAME = {
    # 9 Sep batch, written from the bodies.
    "INC0771784": "[Payments - Credit Card] Cannot pay an invoice - the system will not accept a new card",
    "INC0771787": "[Payments Registration] Error adding a card to the account, with no failed transaction recorded",
    "INC0771813": "[Payments - Credit Card] Manual invoice payment fails with an AMEX card",
    "INC0771846": "[SOA] Credit note visible in Dynamics but missing from Titan",
    "INC0771859": "[Memberships] Coworking membership cannot select the SPACES Hakata Ekimae centre in the portal",
    "INC0771887": "[Invoicing] Poland credit notes show as succeeded but the documents are blank",
    "INC0771891": "[Invoicing] India inter-state office booking taxed CGST/SGST instead of IGST",
    "INC0771902": "[Contract API/Agreements] OSA cannot be generated or sent, and no email is received",
    "INC0771906": "[Invoicing] Egypt ETA rejects an invoice - item code not in the referenced document (CV302)",
    # 8 Sep batch, written from the bodies.
    "INC0771413": "[Memberships] Two membership clients charged an unjustified amount on 20 August",
    "INC0771400": "[Invoicing] Billing address in the online account does not match Titan",
    "INC0771511": "[Login] User cannot log in to the printer after a domain change from regus to hq",
    "INC0771480": "[XC (Product and Services)] IT service charges billed against the negotiated terms",
    "INC0771488": "[Renewals] TeamHub not loading for multiple users - blank screen and agreements cannot be sent",
    "INC0771536": "[Invoicing] Charges for 1-7 September still missing after the workaround",
    # 7 Sep batch, written from the bodies.
    "INC0771216": "[Login] TeamHub does not work for four active users",
    "INC0771253": "[Contract API/Agreements] Clients cannot open OSAs due to an error message",
    "INC0771254": "[SOA] Original invoices rejected in Titan, leaving the account unreconciled",
    "INC0771284": "[Login] User cannot access TeamHub or MyRegus after clearing cache and re-signing in",
    "INC0771349": "[Payments - Credit Card] Account shows a negative balance and an unpaid invoice at the same time",
    "INC0771373": "[Payments Registration] Assistance requested registering a customer card",
    "INC0771384": "[Invoicing] Kenya invoice logo overrides the tax details, so the customer will not pay",
    "INC0771387": "[SOA] Titan data access needed for franchise balance reconciliation",
    # 4 Sep batch, written from the bodies.
    "INC0770979": "[Payments Registration] Customer cannot enter any card on the MyRegus portal after four attempts",
    "INC0771148": "[Payments - Credit Card] Registered card details disappeared from MyRegus between 1 and 15 August",
    "INC0771011": "[Invoicing] Spain e-invoicing preparation - VAT number missing for domestic individuals in Titan",
    "INC0771086": "[XC (Product and Services)] KA and PI services cannot be removed, so the customer is still charged",
    "INC0771145": "[Payments - Credit Card] Payment failure notification sent although the client attempted no payment",
    "INC0771149": "[Login] Server error prevents access to the Titan application",
    "INC0771153": "[Payments Registration] Card registration fails for a new customer opportunity",
    "INC0771155": "[Bookings (Products)] Meeting room booked but the card was never charged",
    "INC0771157": "[Invoicing] No invoices found in SSRS or SQL for a transaction reference",
    "INC0771176": "[Payments - Credit Card] Automatic card payment for the office rental has failed for several months",
    # 3 Sep batch, written from the bodies.
    "INC0770694": "[Invoicing] Monthly invoices not issued or visible for customers across all Turkey centres",
    "INC0770735": "[Payments - Credit Card] Account rejects a card for both the wallet and the default payment method",
    "INC0770759": "[Bookings (Products)] Cannot book a day guest membership in TeamHub via OPS-Center",
    "INC0770799": "[Contract API/Agreements] Signed membership agreement not findable in Sales Hub after the customer was charged",
    "INC0770904": "[Retainers] Return of Retainer button missing for multiple eligible customers",
    "INC0770918": "[Payments Registration] Retainer invoice left unpaid while the other invoices auto-paid",
    "INC0770925": "[Payments - Credit Card] Card rejected or not authorised by the provider",
    "INC0770938": "[Payments - Credit Card] Card rejected after six or seven attempts to add it to the account",
    "INC0770939": "[Payments Registration] Cannot add a card to the wallet or set it as the centre default",
    "INC0770949": "[Payments - Credit Card] Cannot replace an expired default card, with no failed attempt recorded in Pazien",
    "INC0770952": "[Payments Registration] Account admin cannot set their credit card as the default payment method",
    # 2 Sep batch, written from the bodies. Seven more tax-authority clearance
    # failures, each named by what the authority actually rejected.
    "INC0770441": "[Bookings (Products) - Short Stay] Community meeting room 749 not published online at the Hyderabad centre",
    "INC0770473": "[SOA] Ukraine account opening balance is in UAH while later entries are in USD",
    "INC0770493": "[Login] Unable to access TeamHub, blocking a customer renewal",
    "INC0770530": "[Invoicing] France rejects 8,972 invoices with no source Location Number",
    "INC0770557": "[Quick Access] Centre team member cannot view the WorldKey PIN in TeamHub",
    "INC0770561": "[SOA] Invoice copy amount differs from what is posted in D365 and MyRegus",
    "INC0770570": "[Invoicing] Portugal rejects a credit note - recipient TIN incorrect and no longer in Edicom",
    "INC0770571": "[Invoicing] Poland KSeF rejects an invoice as a duplicate document",
    "INC0770572": "[Invoicing] Finland invoices stuck In Progress instead of succeeded",
    "INC0770573": "[Invoicing] Malaysia invoices sent in Pagero but still rejected in Titan",
    "INC0770575": "[Invoicing] Egypt ETA rejects an invoice - quantity exceeds the referenced document (DR317)",
    "INC0770576": "[Invoicing] Uganda credit notes approved in EFRIS but not reflecting as succeeded",
    "INC0770580": "[Contract API/Agreements] Signed membership agreement not loaded into Titan",
    "INC0770666": "[Enquiry] LATIN meeting room enquiries routed to New Sales instead of the Meeting Room team",
    # 1 Sep batch, written from the bodies.
    "INC0770021": "[SOA] Payment on the MyRegus SOA is not reflected in Dynamics Finance",
    "INC0770231": "[Payments Registration] Cannot add a replacement card after the previous one was cancelled for fraud",
    "INC0770242": "[SOA] Titan balance requested for the BGR2 accounts as at 31 August",
    "INC0770253": "[SOA] Refund processed in WPAY although the credit note authorisation failed in Titan",
    "INC0770291": "[Payments - Credit Card] Payment attempt fails although the balance reconciles across MyRegus, Dynamics and Titan",
    "INC0770303": "[Contract API/Agreements] Enquiry not loaded into Titan, no profile created and Replay unavailable",
    "INC0770319": "[SOA] Balance mismatch caused by an unposted invoice the hotfix did not cover",
    "INC0770391": "[SOA] Invoice shows outstanding in Dynamics but already paid in MyRegus",
    "INC0770401": "[Payments - Credit Card] Payment shows as declined although the bank receives no authorisation request",
    "INC0770417": "[Memberships] Upfront 15% membership discount unavailable to some staff",
    # 31 Aug batch, written from the bodies.
    "INC0770024": "[Payments - Credit Card] Errors returned when uploading a credit card to the account",
    "INC0770028": "[Payments Registration] Add payment method hangs on loading after the card details are entered",
    "INC0770031": "[Payments - Credit Card] Payment failure notice and late fee raised against a partially paid invoice",
    "INC0770041": "[Payments - Credit Card] Invoices missed by the monthly automatic card lift, causing late payment fees",
    "INC0770045": "[Invoicing] Invoice date and month shown transposed in TeamHub and Titan",
    "INC0770046": "[Contract API/Agreements] Cannot override the OSA after a centre move - no agreement found",
    "INC0770083": "[Invoicing] France DGFiP rejects a credit note - buyer SIREN missing on a B2B note",
    "INC0770111": "[Invoicing] SSRS returns multiple invoices for a single merchant reference",
    "INC0770120": "[XC (Product and Services)] Mail handling service not showing on the customer account",
    "INC0770177": "[CSU] Nayax posts duplicate coffee/tea charges despite an active Unlimited Coffee/Tea service",
    "INC0770199": "[Payments - Credit Card] Card auto-pays at every centre except one, which also refuses manual payment",
    "INC0770216": "[Payments - Credit Card] Cannot pay by card from the wallet and the card is not set as default",
    "INC0770222": "[Payments - Direct Debit] Cannot set direct debit as the default payment method",
    "INC0770223": "[Invoicing] Reissued credit note includes tax although the invoice is zero VAT",
    # 28 Aug batch. Owner ruling: the short description must be a one-line
    # EXPLANATION of the issue. propose_master_name() only trims -- it strips
    # filler, IDs and trailing clauses and then truncates -- so on a free-form
    # ticket or a pasted error dump it returns the opening words, not a summary.
    # These are written from the body.
    "INC0769798": "[Bookings (Products) - Short Stay] Meeting room booking fails with 'something went wrong' on app and website",
    "INC0769801": "[SOA] Payment reversal in Dynamics never integrated to Titan, leaving the balances 582.43 GBP apart",
    "INC0769804": "[SOA] MyRegus front end shows -1 JPY while Dynamics and the downloaded SOA both show zero",
    "INC0769807": "[Payments - Credit Card] Card confirmation email states an amount ten times what was actually deducted",
    "INC0769829": "[Memberships] Membership payments not collected despite a card registered in Titan",
    "INC0769839": "[Invoicing] Invoice creation fails with an error when raising the invoice",
    "INC0769842": "[Invoicing] Egypt ETA rejects invoices - certificate revocation status cannot be checked (4604)",
    "INC0769843": "[Invoicing] Croatia e-invoice upload failed for seven invoices",
    "INC0769844": "[Invoicing] Reissued credit note and replacement invoice both posted, unbalancing the account",
    "INC0769846": "[Invoicing] Romania reissue posted both the credit note and the new invoice, so they need reposting as non-einvoice",
    "INC0769850": "[Invoicing] Greece rejects invoices - stamp duty exceeds the sum of the correlated invoices",
    "INC0769851": "[Invoicing] Panama rejects invoices as duplicate fiscal documents",
    "INC0769853": "[Invoicing] Egypt ETA rejects credit notes - the referenced document is set to be rejected (DR321)",
    "INC0769855": "[Invoicing] Greece late-payment-fee invoices stuck In Progress instead of succeeded",
    "INC0769861": "[Payments - Credit Card] Card payments failed against a set of invoices",
    "INC0769873": "[Invoicing] Romania invoices double-posted after a reissue and need posting as non-einvoice",
    "INC0769877": "[Invoicing] Egypt invoice stuck at Pending To Be Processed instead of succeeded",
    "INC0769879": "[Invoicing] Greece rejects invoices - VAT category missing from the invoice XML",
    "INC0769880": "[Invoicing] Croatia invoices show as succeeded but the customer receives no e-invoice",
    "INC0769883": "[Invoicing] Romania invoices stuck In Progress instead of succeeded",
    "INC0769884": "[Invoicing] Malaysia invoices stuck In Progress instead of succeeded",
    "INC0769888": "[XC (Product and Services)] Mail forwarding screen blocked in MyRegus team setup",
    "INC0769899": "[Accounts and Companies] Identify who reinstated an account that had been closed for non-payment",
    "INC0769966": "[Network devices] 333 incorrectly onboarded network devices cannot be removed from the account",
    "INC0769986": "[Payments Registration] Add payment method page never finishes loading, so no card can be added",
    "INC0770015": "[Payments - Credit Card] Payment failure email sent after the customer had already paid the August invoices",
    "INC0770022": "[Payments - Credit Card] Automatic payment not taken on schedule despite a registered card",
    # 28 Aug backlog pull. "manager of center 7889 are missing" drafted to "manager of are
    # missing" -- LABELLED_ID strips "center <digits>", which is right for a
    # trailing reference and wrong mid-sentence.
    "INC0764296": "[Accounts and Companies] Centre manager contact details missing from Sales Hub",
    # 27 Aug. Free-form email or form-field openers, all of which draft into
    # either a truncated sentence or a string of account numbers.
    "INC0769635": "[XC (Product and Services)] Unable to amend upcoming invoice to end weekly mail forwarding",
    "INC0769638": "[SOA] Regus opening balance does not match D365 and the SOA",
    "INC0769647": "[Payments - Credit Card] Automatic card charging fails while manual portal payment succeeds",
    "INC0769654": "[UNCATEGORISED] Titan requires a CIN for the Not GST Registered fiscal status in India",
    "INC0769659": "[Documents] Unable to upload client files in TeamHub",
    "INC0769701": "[SOA] Account balance shows paid on the invoice but still overdue",
    "INC0769722": "[Staff - Attendance and Timeoff] Proton absence file not produced for PSHR since 13 August",
    "INC0769779": "[Payments - Credit Card] Automatic payment failed and the registered card is no longer shown on MyRegus",
    "INC0769780": "[Invoicing] Rejected invoice needs reflecting on the account",
    "INC0769788": "[Bookings (Products)] Booking fails with a tax ID error although the account has a tax ID",
    # Owner ruling 27 Aug: Quick Access, not Bookings. The authentication code is
    # the WiFi code a customer is issued while a booking is active, so the booking
    # reference is context for the code, not the subject of the fault. Named away
    # from "Booking Reference" so the title stops implying otherwise.
    "INC0769677": "[Quick Access] Authentication code not working for guest access on OTR",
    # 26 Aug. Both arrived as free-form email with no pipe structure, so the
    # drafted name was the opening words truncated mid-sentence. Categories are
    # the owner's ruling of 26 Aug.
    "INC0769440": "[SOA] Titan balance requested for a list of accounts",
    "INC0769568": "[XC (Product and Services)] Recurring charges not appearing on the immediate invoice",
    "INC0769409": "[Payments - Credit Card] Repeated attempts to add a credit card fail on app and website",
    # Owner correction, 26 Aug: NOT a login fault. The reported issue is that
    # invoices issued since 20 Aug were rejected by Edicom, the India e-invoicing
    # platform; "unable to log in" is a second symptom of that same outage, not
    # the fault being reported. The source short description is truncated
    # mid-word ("unable to log "), so the name is written from the body.
    "INC0769416": "[Invoicing] Invoices rejected in Edicom India since 20 Aug",
    # 21 Aug
    "INC0768805": "[Accounts and Companies] France customer data hotfix - phase 2",
    "INC0768846": "[UNCATEGORISED] Test ticket - no issue reported",
    "INC0768929": "[Documents] Customer company security blocks receipt upload to MyRegus",
    "INC0768932": "[Invoicing] Kitchen Amenity charged on a room with no contract",
    "INC0768946": "[Invoicing] Incorrect date format on TeamHub service charges",
    # 20 Aug
    "INC0768632": "[Roles and Permissions] TeamHub access removed - Deputy City Manager needs City Manager permissions",
    "INC0768650": "[Contract API/Agreements] OSA not autoloaded in Titan after acceptance",
    "INC0768680": "[Accounts and Companies] Customer records missing from the ServiceNow client list",
    "INC0768701": "[Memberships] Incorrect membership visit shown in the Regus portal",
    "INC0768764": "[Contract API/Agreements] Unable to upload signed paper agreement in OSA Detail",
    # 13-14 Aug
    "INC0767810": "[UNCATEGORISED] Global Protect VPN is not working",
    "INC0767842": "[UNCATEGORISED] Titan activation fee mismatch between booking and summary",
    "INC0767930": "[UNCATEGORISED] Printer linked to wrong centre and print release tracking check",
    "INC0767965": "[UNCATEGORISED] MyRegus getTranslations availability test failing (automated P1 alert)",
    "INC0767976": "[Memberships] Account not visible after login and unable to book with membership usage",
    "INC0767995": "[XC (Product and Services)] Callstream office number cannot make or receive calls",
    # 17 Aug
    "INC0767111": "[Quick Access] Access Control username displayed in Japanese Kanji instead of English",
    "INC0768070": "[Invoicing] Customer not receiving invoices after additional recipient email added",
    "INC0768105": "[SOA] Duplicate payment posted in MyRegus needs zeroing out",
    "INC0768111": "[Documents] Delete confidential file uploaded to MyRegus account in error",
    "INC0768136": "[Renewals] Renewal reminder email not sent to office client",
    "INC0768143": "[UNCATEGORISED] Printer reports job completed but nothing prints",
    "INC0768150": "[XC (Product and Services)] Incorrect one-off Mail Forwarding charges on active weekly service",
    "INC0768224": "[Payments - Credit Card] Payment portal rejects Mastercard preventing meeting room booking",
    # 18 Aug
    "INC0768242": "[Contract API/Agreements] Tax ID rejected as incorrect when uploading Internal Service Agreement",
    "INC0768253": "[Invoicing] Credit notes tagged as internal need posting",
    "INC0768271": "[UNCATEGORISED] Printer reports job completed but nothing prints",
    "INC0768275": "[Invoicing] Sales invoices not found in Titan",
    "INC0768311": "[SOA] Dynamics voucher not posted to MyRegus SOA causing incorrect balance",
    "INC0768331": "[Invoicing] Remove unnecessary KA one-off fee from customer account",
    "INC0768376": "[Invoicing] Invoices generated but not sent to the client's registered email",
    # 19 Aug
    "INC0768438": "[Payments - Credit Card] Delayed card deduction caused a late payment fee",
    "INC0768469": "[Invoicing] Customer set to e-invoicing only is also receiving invoices by email",
    "INC0768480": "[Invoicing] MyRegus invoice covers five months with no account changes",
    "INC0768486": "[Memberships] Cancel membership button missing in Customer Portal",
    "INC0768500": "[XC (Product and Services)] Cannot enable self-service Premium Call Answering settings on MyRegus",
    "INC0768505": "[Invoicing] Greek e-invoice rejected - invoice ID must match a valid TIN number",
    "INC0768540": "[Bookings (Products) - Short Stay] MyRegus booking not working for customer",
    "INC0768542": "[Invoicing] Customer still billed for a service no longer in recurring sales",
    "INC0768546": "[Login] New client unable to log in - account marked as inactive",
    "INC0768571": "[Login] Staff unable to access MyRegus and TeamHub",
    "INC0768590": "[Login] MyRegus account activation and access not working",
    "INC0768592": "[Payments - Credit Card] AutoPay did not collect the full invoice amount after a credit note was applied",
    "INC0768596": "[Payments - Credit Card] Card payment shows as succeeded in MyRegus but the client disputes it",
}

# Systems that are not IWG customer-facing products at all.
OUT_OF_SCOPE_TERMS = ("global protect", "globalprotect", "vpn", "service now",
                      "servicenow", "snow ticket", "raise it ticket on service now")
# ...but Unclassified does not always mean out of scope. Printers are in scope
# (L2 - Proton owns them) and simply have no category for print OUTPUT faults.
IN_SCOPE_NO_CATEGORY = ("printer", "printing", "print job", "printeron",
                        "print release", "nothing prints")

rows, detail, review, mism = [], [], [], []

for _, s in src.iterrows():
    tid = s["Number"]
    sd, desc = s["Short description"], s.get("Description")
    r = C.triage_row(sd, desc, cats, masters, kbas, kidx, midx)
    cat, master = r["category"], r["master"]

    # A LOW-confidence match is a tie between masters; the rule is do not apply.
    if master and r.get("confidence") == "Low":
        review.append((tid, "Master match too weak to apply",
                       f"Tied between masters at low confidence (best: '{master}'). "
                       f"Not linked and not tagged ChildTicket - pick the parent by hand."))
        master = None
    # A master with no MST tag cannot produce a complete tag set, and the rule is
    # to raise a blocker rather than half-link.
    if master and not mst.get(master, "").strip():
        review.append((tid, "BLOCKER - master has no MST tag",
                       f"Matches '{master}', which carries no MST tag, so a ChildTicket tag "
                       f"would leave the ticket half-linked. Left unlinked. Allocate that "
                       f"master an MST tag, or scope its keywords."))
        master = None
    # Dropping a master drops the category it carried with it.
    if master is None and r.get("master"):
        sym = C.strip_pipe_prefix(sd)
        cat = C.classify_category(sym, cats)[0]
        if cat == "Unclassified":
            cat = C.classify_category(f"{sym} {C.symptom_body(desc)}", cats)[0]

    # gcol is None when the export carries no assignment-group column at all --
    # the In Progress / backlog exports do not. Passing None makes final_group
    # fall through to the routing rule, which is the honest answer: with no
    # sheet value there is nothing authoritative to defer to. Crashing here on
    # s[None] is what it used to do instead.
    g = C.final_group(s[gcol] if gcol else None, cat, sd, desc, L, groups, signals)

    # --- priority: matrix lookup on the SUPPLIED Impact/Urgency
    u, i = lvl(s.get("Urgency")), lvl(s.get("Impact"))
    if u and i:
        pri = C.PRIORITY_MATRIX[u][i]
        psrc = f"matrix U{u} x I{i} (supplied)"
        allowed, why = C.p1_allowed(sd, desc)
        # P1 AND P2 both require outage evidence: across 39 graded tickets the
        # reviewer never chose either, and every matrix P2 was corrected down.
        if pri in ("P1", "P2") and not allowed:
            pri, psrc = "P3", (f"matrix U{u} x I{i} = {C.PRIORITY_MATRIX[u][i]}, "
                               f"capped to P3 (no outage or major-function evidence)")
        # PROVISIONAL, 3 samples: Quick Access graded P4 in 3 of 3 while the sheet
        # gave Impact 2 / Urgency 2. First counter-example should retire this.
        if cat == "Quick Access" and pri != "P4":
            pri, psrc = "P4", (f"matrix U{u} x I{i} = {C.PRIORITY_MATRIX[u][i]}; "
                               f"Quick Access graded P4 in 3 of 3 reviewed cases (provisional)")
    else:
        pri, psrc = "", "no impact/urgency supplied"

    # --- naming. Rule 2 - identical issue, identical name - drives the order.
    if master:
        new_sd, name_src = master, "master name (agreed)"
        if tid in PRIOR and PRIOR[tid] != new_sd:
            review.append((tid, "Name realigned to master",
                           f"Named '{PRIOR[tid]}' earlier, before the registry match was found. "
                           f"Now a child of '{master}' ({mst.get(master,'no MST tag')})."))
    elif tid in CLUSTER_OF:
        new_sd, name_src = CLUSTER_OF[tid], "cluster name (shared by all tickets on this issue)"
        ccat = CLUSTERS[new_sd]["cat"]
        if ccat != cat:
            review.append((tid, "Category set by cluster",
                           f"Read as '{cat}' from the wording but joins cluster '{new_sd}' "
                           f"(category '{ccat}'). Taking the cluster's so the bracket and the "
                           f"tag agree. If '{cat}' is the better reading, rename the cluster."))
            cat = ccat
        if tid in PRIOR and PRIOR[tid] != new_sd:
            review.append((tid, "Name realigned",
                           f"Named '{PRIOR[tid]}' earlier. Now part of a tracked cluster, so it "
                           f"takes the shared name - rule 2 requires one issue, one name."))
    # A hand-written name outranks one carried forward from an earlier run.
    # These two were the other way round until 26 Aug, which made MANUAL_NAME
    # unreachable for any ticket a previous run had already named: the owner
    # corrected two truncated free-form names, the entries were added, and the
    # run kept emitting the old drafted text because PRIOR was tested first.
    # A human naming a ticket is the strongest signal there is; rule 2 still
    # holds because the hand-written name is what later runs then carry forward.
    elif tid in MANUAL_NAME:
        new_sd, name_src = MANUAL_NAME[tid], "written by hand - free-form ticket"
        if tid in PRIOR and PRIOR[tid] != new_sd:
            review.append((tid, "Name replaced by hand",
                           f"Earlier runs called this '{PRIOR[tid]}'. A MANUAL_NAME entry now "
                           f"names it '{new_sd}', which takes precedence."))
    elif tid in PRIOR:
        new_sd, name_src = PRIOR[tid], "carried forward from an earlier run (unchanged)"
        want = "UNCATEGORISED" if cat == "Unclassified" else cat
        m_br = re.match(r"^\[([^\]]+)\]\s*(.*)$", new_sd)
        if m_br and m_br.group(1) != want:
            new_sd = f"[{want}] {m_br.group(2)}"
            name_src = "carried forward, bracket realigned to the category"
            review.append((tid, "Bracket realigned",
                           f"Kept the wording from '{PRIOR[tid]}' but the category is now "
                           f"'{cat}', so the bracket was corrected to match."))
    else:
        new_sd, name_src = C.propose_master_name(sd, cat)[0], "drafted from short description"

    # --- KBA. Strong only in the main sheet; best-ranked exposed in the detail
    # sheet because the threshold's calibration is still open.
    hits = C.find_kbas_best(cat, master, kbas, kidx, sd, desc) or []
    strong = [(k, sc) for k, sc, _t in hits if (sc or 0) >= C.KBA_REPORT_THRESHOLD]
    kba = "; ".join(f"{k['KB Number']} ({sc:.0f})" for k, sc in strong[:2])
    all_kba = "; ".join(f"{k['KB Number']} ({(sc or 0):.0f}) {str(k.get('Title',''))[:44]}"
                        for k, sc, _t in hits[:3])
    kba_top = f"{hits[0][0]['KB Number']} - {str(hits[0][0].get('Title',''))[:60]}" if hits else ""

    # --- root cause: a suggestion with a ~43% ceiling from text alone
    rcd = C.suggest_root_cause_learned(sd, desc, rcs, cat, priors)
    rc, rc_conf, rc_basis = rcd["root_cause"], rcd["confidence"], rcd["basis"]

    # --- scope
    sym_all = f"{C.strip_pipe_prefix(sd)} {desc or ''}".lower()
    oos = [t for t in OUT_OF_SCOPE_TERMS if C._matches(t, sym_all)]
    in_scope_gap = any(C._matches(t, sym_all) for t in IN_SCOPE_NO_CATEGORY)
    out_of_scope = ("Yes" if oos else "No - category gap" if in_scope_gap
                    else "Likely" if cat == "Unclassified" else "")
    if oos:
        review.append((tid, "Likely out of scope",
                       f"Mentions {', '.join(oos)} - corporate IT or the ticketing platform "
                       f"itself, not an IWG customer-facing product. The destination may be "
                       f"outside L2 entirely."))
    elif cat == "Unclassified" and not in_scope_gap:
        review.append((tid, "Unclassified - check scope",
                       "No category fits. Per standing guidance these are usually outside our "
                       "support scope rather than a keyword gap."))

    # --- tags
    tags = ["TriagedTicket"]
    if master:
        tags.append("ChildTicket")
        t = mst.get(master, "")
        if t:
            tags.append(t)
    if cat != "Unclassified":
        tags.append(cat)
    else:
        review.append((tid, "No category",
                       "Unclassified - cannot be fully tagged until a category is decided."))

    rows.append({
        "TicketID": tid, "Short Description": new_sd, "Master Ticket": master or "",
        "Assigned Group (should be)": g["group"], "Tags": ", ".join(tags),
        "Category": cat, "Root Cause": rc, "KBA": kba, "Priority": pri,
    })
    detail.append({
        "TicketID": tid, "Original short description": sd,
        "New short description": new_sd, "Name source": name_src,
        "Category": cat, "Category source": r.get("source", ""),
        "Master": master or "", "Master confidence": r.get("confidence", ""),
        "Group on export": (s[gcol] if gcol else ""), "Group assigned": g["group"],
        "Group source": g.get("source", ""),
        "Impact (supplied)": s.get("Impact"), "Urgency (supplied)": s.get("Urgency"),
        "Priority": pri, "Priority source": psrc,
        "Root cause (suggested)": rc, "Root cause confidence": rc_conf,
        "Root cause basis": rc_basis, "Out of scope?": out_of_scope,
        "KBA (strong only)": kba,
        "Best-ranked KBA (below threshold - agent judgement)": "" if kba else kba_top,
        "All KBA candidates": all_kba, "JIRA": JIRA_FINDINGS.get(tid, JIRA_NOTE),
        "Tags": ", ".join(tags), "State": s.get("State"),
    })
    if g.get("suggested") and C.canon_group(str(g["suggested"])) != C.canon_group(g["group"]):
        mism.append({"TicketID": tid, "On export": (s[gcol] if gcol else ""), "Rule suggests": g["suggested"],
                     "Kept": g["group"], "Category": cat})

fin = pd.DataFrame(rows)
det = pd.DataFrame(detail)

# ---------------------------------------------------------------- tally
# Pin this to the last run you have SIGNED OFF, not simply the newest file, or a
# superseded run injects retracted clusters into every future one.
#
# Signed off through 21 Aug 2026 (fourth scorecard, 143 rows, covers every batch
# to 21 Aug). Advance this line when a later run is reviewed -- leaving it behind
# silently RESETS every cluster count to the older figure, which reads as normal
# output. The guard below makes that visible instead.
prev_file = os.environ.get("TRIAGE_TALLY_FROM", "runs/Triage_2026-09-08_v4.xlsx")
if not os.path.exists(prev_file):
    sys.exit(f"""tally source missing: {prev_file}
  The Proposed Masters running count lives only inside that workbook.
  Restore it, or set TRIAGE_TALLY_FROM to the last signed-off run.""")

_newer = [f for f in glob.glob("runs/Triage_*.xlsx")
          if os.path.getmtime(f) > os.path.getmtime(prev_file)]
if _newer:
    print(f"  ! tally pinned to {os.path.basename(prev_file)}, but "
          f"{len(_newer)} newer run workbook(s) exist:")
    for f in sorted(_newer, key=os.path.getmtime):
        print(f"      {os.path.basename(f)}")
    print("""    If any of those were signed off, advance TRIAGE_TALLY_FROM or the
    default above -- otherwise their cluster counts are being discarded.""")

prev = pd.read_excel(prev_file, sheet_name="Proposed Masters").copy()
namecol = prev.columns[0]
for old, new, newcat in [
        ("[Invoicing] Invoices paid in D365 still showing unpaid in MyRegus",
         "[SOA] Invoices paid in D365 still showing unpaid in MyRegus", "SOA"),
        ("[Accounts and Companies] Error submitting renewal team request in TeamHub",
         "[Renewals] Error submitting renewal team request in TeamHub", "Renewals"),
        ("[Login] WorldKey PIN rejected as invalid on HP Cloud Printing portal",
         "[Quick Access] WorldKey PIN rejected as invalid on HP Cloud Printing portal",
         "Quick Access")]:
    prev[namecol] = prev[namecol].replace(old, new)
    prev.loc[prev[namecol] == new, "Category"] = newcat

IDCOL = "Ticket IDs (all runs)"
if IDCOL not in prev.columns:
    prev[IDCOL] = prev["Ticket IDs (current batch)"].fillna("")
prev["Current-batch count"] = 0
prev["Ticket IDs (current batch)"] = ""

for name, c in CLUSTERS.items():
    if (prev[namecol] == name).any():
        idx = prev.index[prev[namecol] == name][0]
        prior_ids = [x.strip() for x in str(prev.at[idx, IDCOL]).split(";") if x.strip()]
        prev.at[idx, "Current-batch count"] = len(c["ids"])
        prev.at[idx, "Ticket IDs (current batch)"] = "; ".join(c["ids"])
        prev.at[idx, IDCOL] = "; ".join(sorted(set(prior_ids) | set(c["ids"])))
        if c["note"]:
            prev.at[idx, "Note"] = c["note"]
    else:
        prev = pd.concat([prev, pd.DataFrame([{
            namecol: name, "Category": c["cat"], "Resolved-history count": 0,
            "Current-batch count": len(c["ids"]),
            "JIRA master already exists?": JIRA_NOTE, "Status": "",
            "Ticket IDs (current batch)": "; ".join(c["ids"]),
            "Ticket IDs (resolved history)": "", IDCOL: "; ".join(c["ids"]),
            "Match terms": c["terms"], "Note": c["note"],
        }])], ignore_index=True)

# Recomputed from the ID list rather than incremented, so a re-run cannot
# double-count.
prev["Resolved-history count"] = prev["Resolved-history count"].fillna(0).astype(int)
prev["Total seen"] = prev.apply(
    lambda r: r["Resolved-history count"]
    + len([x for x in str(r[IDCOL]).split(";") if x.strip()]), axis=1)
prev["Threshold (10)"] = prev["Total seen"].apply(
    lambda n: "OVER THRESHOLD - propose master" if n > 10 else f"{11-int(n)} more needed")
prev["Status"] = prev["Total seen"].apply(
    lambda n: "READY - needs your approval + MST tag" if n > 10
    else "below threshold - tracking")
prev = prev.sort_values("Total seen", ascending=False)

# ---------------------------------------------------------------- master audit
# Every ticket->master link asserted since 12 Aug was re-checked on 19 Aug. Six
# were wrong. If ChildTicket / MST tags were already applied in ServiceNow for
# these, they need removing.
# The 19 Aug master audit and its reversal are recorded in the 19 Aug workbook
# and in BENCHMARK.md. Nothing to correct this run.
CORRECTIONS = []
corr = pd.DataFrame(CORRECTIONS, columns=[
    "TicketID", "Was", "MST tag involved", "Should be", "Reason"])
if corr.empty:
    corr = pd.DataFrame([{"TicketID": "-", "Was": "-", "MST tag involved": "-",
                          "Should be": "-",
                          "Reason": "No master links corrected this run. The 19 Aug audit and its reversal are in Triage_2026-08-19_v3.xlsx and reference/BENCHMARK.md."}])

# ---------------------------------------------------------------- other sheets
gsum = fin.groupby("Assigned Group (should be)").size().reset_index(name="Tickets")
csum = fin.groupby("Category").size().reset_index(name="Tickets").sort_values(
    "Tickets", ascending=False)
psum = fin.groupby("Priority").size().reset_index(name="Tickets")
tagsheet = pd.DataFrame([{
    "TicketID": r["TicketID"], "Tag 1": "TriagedTicket",
    "Tag 2": "ChildTicket" if "ChildTicket" in r["Tags"] else "",
    "Tag 3": next((t for t in r["Tags"].split(", ") if t.startswith("MST")), ""),
    "Tag 4": r["Category"] if r["Category"] != "Unclassified" else "",
} for _, r in fin.iterrows()])

REVIEW_EXTRA = [
    ("TTN-143719", "ROOT CAUSE FOUND - fix built, not yet released", "TTN-143719 '[ENHANCE-9600] Prevent back-dated charges and double-billing on occupancy step amendments' is Fixed, Ready For Release, fix version R26.08.01 dated 2026-08-13 but NOT YET RELEASED. It covers Kitchen Amenities, Beverages and Unlimited Coffee on Long-Term Office and Workstation bookings. Tickets already matched to it: INC0768814 and INC0768331 (KA backbill), INC0768932 (Kitchen Amenity double-billed, Japan) and very likely INC0768542 from 19 Aug (unlimited coffee and tea still billed). The JIRA notes Operations is patching the double-billing monthly with manual credit notes - which is what the [Invoicing] Credit note cluster has been recording. These should be linked to the JIRA and held, not worked one by one, and more will arrive until R26.08.01 ships."),
    ("TEAMHUB", "ESCALATE - 9 tickets and NO JIRA covers it", "The TeamHub renewal-team cluster is at 9 of 10 and a JIRA search on 21 Aug found nothing tracking it. CEN has two open amend-agreement bugs - CEN-49075 (renewal price incorrect after repeated saves, New, unassigned) and CEN-46754 (RENEWBOOKING action failed even when renewal succeeds, Blocked) - but neither is the production 'error occurred when trying to submit your request' failure that eight reporters have now hit. This needs raising with the TeamHub team as a new defect."),
    ("DID", "Likely data corrections, not a defect", "PAPI-80621 '[WITH L2] [OOMA] Customer is requesting the change of DID number' is Pending and records the same shape: the DID on the Customer Portal does not match Cerebro because the number was purged there. It is explicitly logged 'for track purpose only, not for Proton team'. That supports treating the 8-ticket DID cluster as data corrections handled by L2 rather than a code defect - and is worth confirming, because if the portal keeps serving a purged number there may be a sync fix worth having."),
    ("INC0768846", "NOT A REAL TICKET", "Short description and description are both the single word 'test'. Nothing to triage - close it."),
    ("INC0768929", "Not our defect", "The customer's own corporate security blocks file uploads to external sites. Needs a workaround (email the receipt, or an allow-list on the customer side) rather than a fix."),
    ("INC0768872", "Repeat of INC0768500", "Same reporter, same customer request, same wording as INC0768500 from 19 Aug, with added detail that two profiles are active and the VO profile should be deactivated. Check whether INC0768500 is still open."),
    ("INC0768932", "Reported as affecting multiple clients", "AHD states this is a system issue currently affecting multiple clients. Now confirmed as TTN-143719 symptom 2. Supplied Impact 4 gives P3; the JIRA evidence suggests the real blast radius is larger."),
    ("INC0768946", "Reported as affecting the whole centre", "TeamHub service charge dates render as 07-1月-2006 instead of 1-7月-2006, stated as affecting multiple users across the entire centre on TeamHub 2.82 - a localisation defect."),
    ("INC0767028", "Printer category still undecided - now 4 tickets", "Fourth printer ticket. Classifies as Quick Access only because the reporter mentions refreshing WKP from MyRegus Quick Access while troubleshooting; the fault is that the document sits on a loading screen and never prints. Grouped with INC0768143 and INC0768271 under one UNCATEGORISED name, per your 17 Aug ruling."),
    ("INC0768787", "Master match to confirm", "A Suspended notification appears in MyRegus but Titan shows no suspension history and no outstanding balance. Linked to MST-71215; MST-71212 'Account showing blocked in My Regus' is the alternative reading."),
    ("INC0768818", "Master match to confirm", "Linked to MST-71224 'Unable to find linked account to switch' at High. The user is redirected to an unlinked account and linking fails with 'office account does not exist'."),
    ("INC0768805", "Bulk data fix, not an incident", "France customer data hotfix, phase 2, with two attached files of corrected account data. A deployment request rather than a fault report."),
]
rev = pd.DataFrame([{"TicketID": t, "Issue": k, "Detail": d}
                    for t, k, d in list(review) + REVIEW_EXTRA],
                   columns=["TicketID", "Issue", "Detail"])

with pd.ExcelWriter(OUT, engine="openpyxl") as xl:
    fin.to_excel(xl, sheet_name="Finished Triage", index=False)
    det.to_excel(xl, sheet_name="Triage Detail (full)", index=False)
    prev.to_excel(xl, sheet_name="Proposed Masters", index=False)
    corr.to_excel(xl, sheet_name="Master Corrections", index=False)
    pd.read_csv("reference/priority-matrix.csv").to_excel(
        xl, sheet_name="Priority Matrix", index=False)
    rev.to_excel(xl, sheet_name="Review", index=False)
    gsum.to_excel(xl, sheet_name="Group Summary", index=False)
    csum.to_excel(xl, sheet_name="Category Summary", index=False)
    psum.to_excel(xl, sheet_name="Priority Summary", index=False)
    (pd.DataFrame(mism) if mism else pd.DataFrame(
        columns=["TicketID", "On export", "Rule suggests", "Kept", "Category"])
     ).to_excel(xl, sheet_name="Group Mismatches", index=False)
    tagsheet.to_excel(xl, sheet_name="Tags", index=False)

from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
wb = load_workbook(OUT)
hdr = Font(bold=True, color="FFFFFF")
fill = PatternFill("solid", fgColor="2F5597")
for ws in wb:
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for c in ws[1]:
        c.font, c.fill = hdr, fill
        c.alignment = Alignment(vertical="center", wrap_text=True)
    for col in ws.columns:
        w = max((len(str(c.value)) for c in col if c.value is not None), default=10)
        ws.column_dimensions[col[0].column_letter].width = min(max(w + 2, 12), 55)
wb.save(OUT)

# ---------------------------------------------------------------- assertions
bad = []
for _, r in fin.iterrows():
    m = re.match(r"^\[([^\]]+)\]", str(r["Short Description"]))
    want = "UNCATEGORISED" if r["Category"] == "Unclassified" else r["Category"]
    if not m or m.group(1) != want:
        bad.append((r["TicketID"], r["Short Description"], r["Category"]))
kids = fin[fin["Tags"].str.contains("ChildTicket")]
assert not bad, f"bracket/category mismatch: {bad}"
assert fin["Short Description"].notna().all(), "blank name"
assert all("MST" in t for t in kids["Tags"]), "ChildTicket without an MST tag"

print(f"WROTE {OUT}  ({len(fin)} tickets)   [assertions passed]")
print("\n--- group ---")
print(gsum.to_string(index=False))
print("\n--- priority ---")
print(psum.to_string(index=False))
print("\n--- category ---")
print(csum.to_string(index=False))
print("\n--- tally ---")
print(prev[[namecol, "Total seen", "Threshold (10)"]].to_string(index=False))
print(f"\nmismatches: {len(mism)}   review rows: {len(rev)}   master corrections: {len(corr)}")
