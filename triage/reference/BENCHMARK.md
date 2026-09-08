# Benchmark against 623 resolved/closed tickets

Source: `resolved and closed for training.xlsx` — 494 Closed, 129 Resolved.

**The set splits in two, and only one half is valid ground truth.** 377 tickets were triaged under the current process and carry tags; 246 predate it and have none. The learned tables are built from the tagged 377 only, and the headline figures are measured on them. The old-process subset is reported separately because its routing reflects a process that no longer applies.

| Measure | New process (377) | Old process (246) |
|---|---|---|
| Category | **89.5%** | no category labels to score against |
| Assignment group, category read from the tag | **84.6%** | n/a |
| Assignment group, end-to-end (category inferred too) | **83.3%** | 54.1% |
| Root cause | **42.4%** | 25.4% |

Category inference costs almost nothing: 84.6% with the true category versus 83.3% inferring it.

## How routing got from 48% to 84%

| Approach | New-process accuracy |
|---|---|
| Surface rule alone — route on the visible surface | 48.4% |
| Learned category→group table | 79.6% |
| + XC sub-rule, residual XC to Portal | **84.6%** |

The surface rule as first specified was barely better than chance across three groups. Its dominant failure was tickets whose symptom appears in MyRegus but which Titan owns. Category is the far stronger predictor, so routing is category-first with the surface rule kept as tie-break for genuinely split categories and as fallback where there is no training evidence.

**XC needed a sub-rule.** Telephony/OOMA/DID → Proton, parking → Portal first. The residual — scanned pages, TeamHub services, credit requests — measured as Portal, and defaulting it to Proton cost 20 errors on its own. Fixing that was worth +5 points.

**Two changes that measured worse and were rejected**: enabling the surface tie-break on Payments - Credit Card dropped accuracy to 80.1%, and extending it to Registration and Login dropped it to 79.0%. The simpler table wins.

Remaining errors, largest first: 16 Payments - Credit Card tickets that went to Titan against an 83%-Portal category; 6 Invoicing; small numbers on Short Stay and Accounts and Companies. These are the genuine minority cases inside otherwise consistent categories and are not separable from the text.

## Root cause: ~43% is the ceiling from ticket text

| Approach | Result (30% holdout) |
|---|---|
| Always answer the most common value (Data Corruption) | 31.5% |
| Naive Bayes over description tokens | 42.9% |
| Majority per category | 42.4% |
| Majority per (category, group) | 36.4% |
| My original conservative rule | 12.2% |
| **Shipped: category prior, overridden only by JIRA-backed evidence** | **42.4%** |

The label records what the investigation found, not what the customer wrote, so it is only weakly predictable from the description. Mined signals were thin even for the largest class — Data Corruption, with 131 training examples, yielded only `incorrect`, `set`, `missing` above threshold — and Software Bug produced obvious overfitting artefacts (`colombia` at lift 166666, from one ticket).

Measured consequence: ticket-wording signals are **worse** than the category prior. Letting them override it dropped accuracy from 42% to 33%, so only JIRA-backed evidence overrides. Wording is kept as a runner-up.

**Treat root cause as a suggestion for agent confirmation.** It is right about two times in five, and that is close to the achievable limit without the investigation outcome.

## Label distribution

Root cause — 13 of the 29 picklist values have ever been used:

```
Data Corruption 194 · Configuration Error 105 · Unknown Cause 91 · Third-Party Service Failure 55
Access Issue 52 · Human Error 50 · Software Bug 22 · Training Issue 21 · Process Failure 16
Performance Degradation 3 · Patching Issue 2 · Application Crash 1 · Dependency Failure 1
```

Group: L2-Titan 261 · L2-Portal 253 · L2-Proton 109.

## Decisions recorded

- **Masters are linked by name, not by PRB.** The `Problem` column holds PRB records on 107 tickets, but the service owner confirms PRB is not a reliable way to connect masters. The `[Category] Short Description` name remains authoritative; `MST-xxxxx` tags are a secondary cross-reference.
- **Untagged tickets are old-process**, not a data-quality defect. Excluded from training and reported separately.
- Canonical spellings confirmed: **`Patching Issues`** (the picklist form, though resolved tickets show `Patching Issue`) and **`Contract API/Agreements`** (tags also contain `ContractAPI/Agreements`).
- Three categories have no training evidence — Help and Inbox, Renewals, Staff - Attendance and Timeoff — and fall back to the surface rule.

## Artefacts

- `reference/group-by-category.csv` — learned category→group table with purity and distribution
- `reference/root-cause-priors.csv` — most common root cause per category, with the full distribution
- `reference/root-cause-signals-learned.csv` — mined signals with lift, kept for inspection rather than relied on

---

# Human review of a live batch (24 tickets, `triage1corrected.xlsx`)

The first genuine scorecard: a reviewer graded my output ticket by ticket. It found errors the resolved-ticket benchmark could not, because three of the four failures were **policy** errors, not classifier errors.

| Measure | As delivered | After fixes |
|---|---|---|
| Category | 79% | **96%** |
| Routing | 67% | **96%** |
| Priority | 29% | **100%** |
| KBAs offered | 15, of which 13 judged useless | 0 (strong-only) |

Mean quality score was 3.6/5, with 6 tickets marked "Major correction".

## Four root causes

**1. I was overriding the answer already in the export.** All 8 routing errors were tickets where I overrode a populated `Assignment group`. Taking the sheet verbatim scored 22/24; my learned table plus JIRA-evidence overrides scored 16/24 — my overrides were 2 right and 8 wrong. The sheet now wins, with exactly one sanctioned exception: the owner's standing `Login → Proton` rule. **Do not widen that exception without measuring.**

**2. Priority: every ticket in the batch was P3.** I said P2 nine times and left it blank eight. The matrix was fine; my impact inference read scope broader than practice does. Default is now **P3**, deviating only for outage evidence (P1) or urgency-4 consultation/request work (P4).

**3. My KBA confidence band is anti-correlated with usefulness.** All 13 suggestions I labelled "possible" (6–12) were judged not useful. The only 2 the reviewer found useful I had labelled "weak". The band carries no signal, so only **strong** (≥12) reaches the output. Precision over recall: better to offer nothing than 13 wrong articles.

**4. The pipe hint was actively harmful.** 6 of 7 category errors came from trusting it. Agents write the broad **area**, the ticket is a narrower **issue**:

```
"Accounts & Companies" | error submitting renewal team request  -> Renewals   (x2)
"Invoices"             | unable to upload TDS document          -> Documents
"Payments - Credit Card Registration" | ACH details not saved    -> Payments Registration
```

Measured: hint-first 71%, symptom-first 83%. Policy reversed with the owner's agreement — symptom first, hint only when the symptom is unclassifiable.

## Bugs the review exposed

- **Symptom classification was reading the pipe prefix.** `triage_row` classified on the unstripped short description, so "Customer Portal | Accounts and Companies | Account inactive in Myregus" classified as Accounts and Companies when the symptom is Login. Stripping it fixed the last category error and is what took the batch from 92% to 96%.
- **Booking split fired backwards.** The owner rule is: booking issues in **TeamHub → Bookings (Products)**, in **Customer Portal → Bookings (Products) - Short Stay**. For this rule the leading app label *is* the signal, so unlike routing it reads the whole short description. TeamHub wins when both are named. A portal named as *working* ("available on My Regus but not on the Regus site") must not claim the ticket.
- **XC lost to Services.** Symptom-first sent "add service" and "mail forwarding" tickets to Services. XC has 58 resolved tickets to Services' 5, so XC now owns product-and-services wording and Services keeps only its specific entitlement terms.
- Added `account inactive` / `inactive in myregus` to Login — a keyword gap flagged several batches earlier and confirmed by the reviewer.

## Cost of the fixes

Category on the 377 resolved tickets moved 90.1% → 88.7%, a 1.4-point loss, in exchange for +17 points on the reviewed batch. Taken deliberately: the human review reflects current practice, the resolved set includes older labelling. Routing on the resolved set is now 97.6%, since the sheet is authoritative there too.

## Still unresolved

`INC0766960` — "mark invoices as PAID, status in MyRegus still unpaid" — filed by the reviewer as **SOA**, not Invoicing. Payment-status-versus-statement is a domain distinction I cannot infer from the text. Flagged rather than guessed.

## Owner corrections, 13 Aug 2026

Two classification rules given by the service owner, both encoded and regression-tested:

**Invoice/payment mismatch is `SOA`, not `Invoicing` — and routes to `L2 - Titan`.** Anything settled in one system but showing unpaid in another. This also resolved `INC0766960`, the single category error left unexplained after the human review: it was this same pattern. **The reviewed batch is now 24/24 on category.** Invoicing keeps invoice creation and content problems; the mismatch terms moved to SOA, which at precedence 10 beats Invoicing at 30.

**IWG card issues are `CSU`, and route to `L2 - Portal`.** Deliberately scoped to IWG card *issues* — activation, not working — rather than the bare term. Matching bare "iwg card" pulled a Login ticket into CSU because the printer quotes *"Please tap your IWG card or enter your World Key PIN"* in its own prompt. A product name inside an error message is not the subject of the ticket, the same trap as `staff mode` and `something went wrong`.

Category on the 377 resolved tickets moved 88.7% → 88.5%, a 0.2-point cost for +4 points on the reviewed batch.

## Run of 14 Aug 2026 — two silent bugs and a naming rule that wasn't holding

25 tickets, 15 of them new. Both ground-truth sets were re-measured after every change: **377 resolved stayed at 88.5%, the reviewed batch stayed at 24/24.** Nothing here was a trade-off.

**An empty pipe hint resolved to a real category.** A free-form ticket truncated at a trailing pipe (`… Type of Ticket: Customer |`) produced `raw == ''`, and an empty string prefix-matches every category name, so it silently resolved to **CSU**. Empty is the absence of evidence, and now returns `None`.

**Pipe-splitting fired on tickets that merely contain a pipe.** `strip_pipe_prefix` assumed `App | Area | Symptom`, so on an email pasted into the ticket it kept only the text after the last pipe — `'VO Standard'`, or nothing at all. New `is_pipe_structured()` gate: the convention's first segment is a short app label, never a paragraph, so a first segment over 6 words or 60 characters means the pipes are incidental. This one bug was corrupting the input to every downstream step on 8 of 25 tickets.

**Six tickets on one issue got six different names.** Rule 2 says same issue, identical name, character for character — but naming ran per ticket, so the card-registration cluster produced six variations, all of them mangled email boilerplate (`[Payments Registration] Hi Team, - Nenad Radulović 6-digits: 4-digits: 3442 Customer`). Naming is now a precedence chain: **matched master → tracked cluster → earlier run → drafted**. A cluster is the same issue seen repeatedly, so every ticket in one carries the cluster's name even though no master exists yet.

**And the rule wasn't holding across runs either.** INC0767810 was named "Global Protect VPN is not working" on 13 Aug and redrafted as "Global Protect VPN access issue" on 14 Aug — the same ticket, two names. Names now carry forward from previous run workbooks and are only changed deliberately, with the change logged on the Review sheet. One such realignment this run: INC0767409 moved onto the SOA cluster name once the link to INC0766960 was spotted.

**`propose_master_name` was drafting from email boilerplate.** Added salutation stripping (`Hi/Hello/Dear team`) and labelled-field stripping (`Company Name:`, `Account Number:`, `6-digits:`).

### The serious one: I proposed clusters for issues that already had masters

Caught by the service owner asking "are you using master tickets we already have?" — a fair question, because only **2 of 25** tickets matched a master on the first pass. The answer was no, and it was the worst error in the run: six card tickets were filed as a brand-new cluster while the registry already held **MST-71221** (error adding a payment card), **MST-71579** (setting up a default payment method) and **MST-71513** (expiry date rewritten). Autopayment and cannot-pay-invoice had masters too.

**Why it happened.** I closed the keyword gaps in `categories.csv` and stopped there. The master registry has its own `Symptom keywords` column with the same gaps — tuned to the structured wording of past tickets (`autopayment not working`, `add payment card`) and blind to this batch's free-form email phrasing (`auto pay is not being pulled`, `unable to add the card`, `attempting to upload the card`). Fixing one layer and not the other is what produced a duplicate-master proposal.

**Measured, because master matching does have ground truth** — the 190 resolved tickets carrying an `MST-xxxxx` tag:

| | Before | After 33 added keywords |
|---|---|---|
| Correct master | 183 (96.3%) | **184 (96.8%)** |
| No match (gap) | 1 | **0** |
| Wrong master | 6 | 6 |

Matching on this batch went **2/25 → 13/25**. The 6 wrong are label noise, not misses: their short descriptions name a different master than their own tag, e.g. a ticket titled `[Payments - Credit Card] Cannot pay invoice online` tagged to `Payments Registration`.

**Two rules now enforced in the run script.** A cluster may only exist for a symptom with *no* master in the registry — check the registry before tallying anything. And the tally is carried forward from the last **authoritative** run, pinned by name: the superseded first attempt would have injected its retracted clusters into every future run. Totals are recomputed from an accumulated ticket-ID list rather than incremented, so a re-run cannot double-count.

**A cluster's category wins over the classifier**, for the same reason a matched master's does: otherwise the name's bracket contradicts the category tag. INC0768007 read as `Renewals` but joined an `Accounts and Companies` cluster — flagged, not silently resolved.

### Keyword gaps closed

| Category | Was landing as | Gap |
|---|---|---|
| Payments Registration | Payments - Credit Card | add / set up / upload a card, `default payment preference`, `cc details`, card shows as expired |
| Payments - Credit Card | Mobile, Unclassified | `auto pay is not being pulled`, `card is not pulling`, can't pay invoices with a registered card |
| XC (Product and Services) | Unclassified | `callstream`, cannot make or receive calls |
| Renewals | Unclassified | `renew agreement`, `unable to renew` |

**Bare `cc` removed from Payments - Credit Card.** It fired on any ticket mentioning card details and beat nothing: identical scores on both sets with and without it. Removing it let INC0768031's real symptom — in the body, not the truncated title — reach the classifier.

**Bare `mobile` removed from Mobile**, which had been claiming tickets that mention the app only as background ("I saw on his mobile app all permissions are open"). Replaced with failure-direction wording plus `mobile application` and `mobile key`. Cost 3 errors on the resolved set and fixed 1; two of the three were recovered by the two added terms, and the last is **label leakage** — its short description is literally `[Mobile] [Quick Access] Error when trying to get authentication code`, so it only ever scored right by reading its own tag out of the title. Worth knowing the 88.5% baseline is slightly inflated by tickets that print their answer.

## Second human scorecard — 24 tickets, 14 Aug 2026

A full `AI_vs_Human_Triage_Scorecard` on the same day's batch, graded against my v2 output. Every correction below was encoded and re-measured against all three ground-truth sets.

| Measure | v2 as delivered | After the corrections |
|---|---|---|
| Category | 18/21 (86%) | **21/21 (100%)** |
| Routing | 17/21 (81%) | **19/21 (90%)** |
| Priority | 18/20 (90%) | 18/20 — unresolved, see below |
| Short description | 15/20 (75%) | **20/21** |

Nothing regressed: 377 resolved held at 88.5%, master matching at 184/190, and routing on the 377 actually **rose to 98.4%**.

**OOMA and DID override the sheet.** The reviewer flipped INC0767819 and INC0767855 from a *populated* `L2-Portal` cell to `L2 - Proton`. This is now the second sanctioned exception alongside `Login → Proton`. Deliberately scoped to the two products named and **not** generalised to telephony: a Callstream ticket in the same batch (INC0767995) was accepted as Portal. The rule agrees with historical routing too, which is why the resolved-set score went up rather than down.

**"Unable to log a credit note" is XC, not Roles and Permissions.** I read "unable to log" as a permissions problem; credit notes are an XC product-and-services function. `credit note` moved from Invoicing to XC.

**A cluster's category can be the thing that's wrong.** I had INC0768007 read as `Renewals` by the classifier but overrode it with the cluster's `Accounts and Companies` — correctly insisting the name's bracket and the tag must agree, but fixing the wrong side. The reviewer confirms `Renewals`. **When a clustered ticket's classified category disagrees with the cluster name, the cluster name is the more likely error** — it is an unapproved proposal, whereas the classifier is reading this specific ticket. Cluster renamed and the two earlier tickets move with it.

**A carried-forward name must not carry a stale bracket.** INC0767842 was named `[UNCATEGORISED]` before its category was known; once `activation fee` classified it as Bookings (Products) the bracket had to follow. Wording is preserved, the bracket is realigned, and the change is logged.

**Unclassified usually means out of scope, not a keyword gap.** Owner guidance, and it changes what to do about it: stop hunting for keywords and check whether the ticket is ours at all. INC0767976 went to `L3-ServiceNow Platform` — a destination outside the three L2 queues — because the reporter could not raise a ticket in ServiceNow itself. Out-of-scope candidates are now flagged with an `Out of scope?` column and a review row; they are never auto-routed, because inventing a destination outside L2 is not safe.

### One hypothesis tested and rejected

INC0767895's sheet said `L2 - Titan`, the reviewer said `L2 - Portal`, and the learned category rule would have been right. So: *when a master matches, should the master's category group beat the sheet?* Measured on the 265 master-matched resolved tickets, the learned rule disagrees with the desk's own group **49 times**. Adopting it would break 49 to fix 1. Rejected — the sheet stays authoritative.

### Still open

- **Priority, 2 of 20.** INC0767857 (`U1 × I3` → matrix P2) and INC0768004 (`U3 × I3` → matrix P4) were both graded **P3**. It isn't a transposed matrix — swapping the axes gives the same cells. Either the supplied Impact/Urgency are noisy or the grid diverges from practice in those two cells. Not changed unilaterally: the grid was supplied by the owner and is 18/20.
- **INC0767937.** Matched to MST-76060 *"Unable to send agreement from Preview OSA screen"*; the reviewer named it *"Unable to see Preview OSA screen for Move Office"* — cannot **see** the screen, in the **Move Office** flow. That may be a distinct issue rather than a child of that master.

## Run of 17 Aug 2026 — the "Troubleshooting attempted" trap

20 tickets. Four misclassifications traced to **one** cause, which makes it the most valuable finding since the master-registry gap.

**The `Troubleshooting attempted:` section lists what the agent checked and found FINE.** Reading a symptom out of it inverts the meaning. Two clear cases in this batch:

```
INC0768070  "Checked the customer portal for balance mismatch, invoice visibility..."
            -> matched the [SOA] Balance Mismatch master. The ticket is about
               undelivered invoice emails. That master has NO MST tag, so it
               would have raised a tagging blocker on an unrelated ticket.

INC0768143  "Confirmed successful WorldKey login"
            -> classified Login. The ticket says authentication works, the job
               reports complete, and nothing prints. It is a printer fault.
```

Form-field lines do the same thing: `Booking reference number: 170274728` classified a TeamHub renewal error as `Bookings (Products)`, purely because the template asks for a booking reference.

Both are now stripped by `symptom_body()` before category classification and master matching. **Cost: 1 ticket on the 377 resolved set (88.5% → 88.2%)** — and that one is label noise, a ticket titled `[Bookings (Products) - Short Stay] …` but tagged `Bookings (Products)`, which had been landing on its tag because of a TeamHub mention inside its own troubleshooting block. Everything else held: master matching 184/190, routing 98.4%, 14-Aug scorecard unchanged.

**`classify_category` was not using the ruled-out guard that `match_master` uses.** So a phrase that could not win a master could still win a category. The layers now share one definition of evidence, and `RULED_OUT` gained the "named as working" family — `authentication works`, `confirmed successful`, `sent successfully`, `listed correctly`, `no setup errors`. This is the same trap as `staff mode` and `mobile`, but stated positively: **a component named as working is not the fault**, and the sentence that proves it works is the one most likely to contain its name.

### Two clusters that were genuinely new

Checked against all 46 masters first, and `master_candidates` returned nothing for either:

- `[Bookings (Products)] Cannot rollback a booking terminated while provisional` — INC0768094, INC0768115. Same fault, same day, both Titan: terminated while provisional, now un-editable, actions greyed out.
- `[Bookings (Products) - Short Stay] Meeting room booking does not complete at the payment step` — INC0768112, INC0768123. The second says "a lot of customers and non-customers" are affected.

### Out-of-scope flag needed a third state

Treating every `Unclassified` ticket as likely out of scope was too blunt. Printers are plainly in scope — L2 - Proton owns them — they simply have no category. The flag now reads `No - category gap` for those, so it stops contradicting the review row that asks for a category decision.

### Open decision: no printer category

Three printer faults across two batches (INC0767930, INC0768143, INC0768179), all routed to L2 - Proton, none classifiable. Either add a `Printer` category or fold printing into `XC (Product and Services)`. Until then they cannot carry a full tag set.

## KBA search was under-reporting because of query dilution

Prompted by the owner asking why no articles were being suggested. Two runs in a row had offered zero. The precision policy was working as designed — and it was masking a recall bug.

**The scorecard already said so.** `Missed KB / fix` is the second most common correction reason, 7 of 48 rows. Every one of those is a row where an article *was* offered and judged not useful. So the complaint was never "no article exists", it was "you found the wrong one". Going silent does not fix that; it just stops being wrong out loud. (`Human · Knowledge Article` is empty on every row, so the correct article was never recorded — see below.)

**The cause: the IDF overlap score is not normalised for query length, and I was querying with the whole ticket.** Long queries add tokens that match nothing and drag the right article's score down:

| Query | Best article | Score |
|---|---|---|
| Whole ticket (42 tokens) | `KB0020210 Worldkey pin is not working` | 9.1 |
| Short description only (8 tokens) | same article | **17.9** |

Same article, same index, one side of the threshold and then the other. Across the batch the best-candidate score had median 5.3 and max 9.1 against a threshold of 12 — mathematically incapable of reporting anything.

**The search itself is fine.** Probed with a focused phrase, the right article ranks first: `worldkey pin printer` → 19.3, `printer not printing` → 13.3, `mail forwarding charges` → 14.6, `credit card registration myregus` → 13.2. The articles were there all along.

**Fix: `find_kbas_best()` queries with the short description AND the full symptom text and keeps each article's best score.** Neither wins outright — a free-form email has a useless title and needs the body, while a well-formed ticket is diluted by it. Ranking uses a length-normalised score (`score / sqrt(tokens)`), which put the correct article 1st in 6 of 6 hand-checked tickets versus 5 of 6 raw. Reporting still thresholds on the **raw** score, so `KBA_REPORT_THRESHOLD` keeps its meaning and this change cannot quietly widen what gets offered. Result: 0/20 → 2/20 with the threshold untouched.

**The threshold is now the binding constraint, and its calibration is invalid.** The "all 13 possible suggestions were useless" finding was measured on articles surfaced by the diluted query, so it says nothing about what a corrected query surfaces at the same score. Ranking is now reliable enough that the top candidate is usually right, but that is my own judgement on six tickets, not the owner's.

**What would settle it**: the correct KB number recorded against a batch of tickets, in the scorecard's existing `Human · Knowledge Article` column. With ~20 of those the threshold can be set from data instead of guessed. Until then the top-ranked candidate is exposed on the detail sheet as *"Best-ranked KBA (below threshold — agent judgement)"* — visible, clearly not asserted, and not in the Finished Triage KBA column.

## Third human scorecard — 20 tickets, 17 Aug 2026

| Measure | As delivered | After corrections |
|---|---|---|
| Category | 17/20 (85%) | **20/20 (100%)** |
| Short description | 17/19 (89%) | **18/19 (95%)** |
| Routing | 15/19 (79%) | **16/19 (84%)** |
| Priority | 12/19 (63%) | **14/19 (74%)** |
| Root cause | 12/19 (63%) | unchanged — above the ~43% text ceiling already |

Nothing regressed: 377 resolved 88.2%, master matching 184/190, 623 routing 98.4%, 14-Aug scorecard unchanged.

**Printers are `Quick Access` — but only printer *access*.** The answer to the open category question, and it came with a distinction I would have flattened. INC0767930 (linked to wrong centre) and INC0768179 (WorldKey PIN) are Quick Access; INC0768143 (job reports complete, nothing prints) was confirmed as **UNCATEGORISED**. So Quick Access covers *getting to* the printer — PIN, badge, centre linkage — not print output. A blanket `printer` keyword would have been wrong on the third ticket. The WorldKey PIN terms moved from Login to Quick Access with them.

**The SOA routing rule was only half-built.** The owner's 13 Aug instruction was "any mismatch related to invoices and payment is SOA category **and Titan group**". I implemented the category half and left routing to the sheet, so INC0765337 sat on Portal and was corrected to Titan. `SOA → L2 - Titan` is now the **third** sanctioned override, alongside `Login → Proton` and `OOMA/DID → Proton`. It costs nothing on the 623-ticket routing check.

**A tracked cluster was renamed for the second time.** `[Login] WorldKey PIN rejected…` → `[Quick Access] WorldKey PIN rejected…`, because the reviewer categorised INC0768179 as Quick Access. Same lesson as INC0768007, now confirmed twice: **when a clustered ticket's category disagrees with the cluster name, the cluster name is the error.** The 5 earlier tickets in that cluster were tagged `Login` and need retagging if the rename is adopted.

### Priority: the supplied matrix does not reproduce the desk's grading

39 graded tickets now carry both a supplied Impact/Urgency and a human priority. The empirical picture:

| U × I | matrix says | human actually chose | n |
|---|---|---|---|
| 1 × 4 | P3 | P3 ×15 | 15 |
| 3 × 3 | P4 | P4 ×10, **P3 ×4** | 14 |
| 2 × 4 | P4 | P4 ×4, **P3 ×2** | 6 |
| 2 × 2 | P2 | **P4 ×2** | 2 |
| 1 × 3 | P2 | **P3 ×1** | 1 |
| 3 × 4 | P4 | P4 ×1 | 1 |

**In 39 graded tickets the reviewer never once chose P1 or P2.** Every time the matrix said P2, the answer was P3 or P4. So the P1 evidence gate now covers P2 as well: without outage or major-function evidence the result is capped at **P3**. That is an extension of an existing rule, not an edit to the owner's grid.

| Rule | Score on 39 |
|---|---|
| Matrix as supplied | 30/39 (77%) |
| + P1/P2 require outage evidence, else P3 | 31/39 (79%) |
| + Quick Access → P4 | **33/39 (85%)** |
| Always P3 | 22/39 (56%) |
| Category-majority priority — **rejected** | fits 34/39 but only 29/39 (74%) leave-one-out |

Category-derived priority looked attractive at 87% fit and fell to 74% under leave-one-out, below the matrix. Rejected. `Quick Access → P4` is kept but is **provisional on 3 of 3 samples** — agents rate printer tickets Impact 2 / Urgency 2 and the desk treats them as low. The first counter-example should retire it.

**Unresolved, and not resolvable from Impact/Urgency**: all 6 remaining errors are cells where the matrix says P4 and the reviewer said P3 — `U3×I3` and `U2×I4`. Those same cells produce *correct* P4s for SOA tickets, so the split happens inside the cell. Either the agents' Impact/Urgency are noisy, or priority depends on something the grid does not capture.

### Root cause: three graded values are not in the picklist

`Documentation Error`, `Configuration Issue` and `Quick Access` were entered as root causes and none exists in the 29-value list (`Configuration Issue` is presumably `Configuration Error`; `Quick Access` looks like a category pasted into the wrong column). Also 3 of my `Configuration Error` answers were graded `Unknown Cause` — the desk reaches for Unknown Cause more readily than the category prior does.

## Run of 18 Aug 2026 — two safety bugs in the run script

15 tickets. All four ground-truth measures held (377 resolved 88.2%, master matching 184/190, 623 routing 98.4%, 17-Aug scorecard category 20/20). The interesting findings were in the runner, not the classifier.

**A Low-confidence master was being applied.** `triage_row` returns the best master plus a confidence, and the rule has always been "Low = a tie between masters, do not apply" — but the run script tested only `if master:`. INC0768427 ("cannot make payment through CC. Cannot add CC.") ties MST-71216 and MST-71221 because it genuinely reports both, and would have been tagged a child of whichever sorted first. Now unlinked and sent to review.

**A master with no MST tag was being tagged anyway.** `[SOA] Balance Mismatch` is the one registry row without a tag, and the documented rule is to raise a blocker rather than half-link. INC0768311 matched it on "incorrect balance" and came out tagged `ChildTicket` with no `MST-xxxxx`, which the tag invariant forbids. The runner now drops such a link and raises the blocker.

Both bugs shared a cause worth remembering: **`triage_row` reports its confidence and its blockers, and the runner was ignoring them.** Dropping a master also has to drop the category it carried, or the ticket keeps a category inherited from a link that was just refused.

**The SOA D365→MyRegus cluster is now 7 and growing fastest** — three more this batch (INC0766583, INC0767871, INC0768311). Two decisions are overdue: the name still says "Invoices paid … showing unpaid" while most members are payments and vouchers that never arrived at all, and `[SOA] Balance Mismatch` now competes with the cluster for the same tickets while having no MST tag.

**An exact duplicate.** INC0768271 is byte-identical to INC0768143 from the previous batch — same customer, same centre, same text. Worth a duplicate check on ID and on description hash in future runs.

**A keyword rejected for cost.** `amend agreement` looked like a clean fix for INC0768359, but a resolved ticket "Not able to amend agreement" is tagged `XC (Product and Services)` while the 14 Aug review put TeamHub amend/renew errors under `Renewals`. The evidence conflicts, adding it cost a measured error, so it was removed and the ticket left Unclassified for an owner decision.

## Run of 19 Aug 2026 — TeamHub renewals reaches 8 of 10

26 tickets, all new. Every measure held: 377 resolved 88.2%, master matching 184/190, 623 routing 98.4%, 17-Aug scorecard category 20/20.

**The headline is a cluster, not a classifier finding.** The TeamHub renewal-team cluster took three more (INC0768533, INC0768544, INC0768550) and stands at **8 of 10**, from seven reporters across four batches. A sibling cluster — the amend-agreement flow itself erroring or freezing — opened at **4** (INC0768359, INC0768485, INC0768499, INC0768524). That is 12 tickets on the TeamHub agreement journey inside a week, which is worth escalating before either count crosses the threshold.

The split between the two is deliberate: one is the *handoff* to the renewals or retention team failing, the other is the *amendment itself* erroring. They may turn out to be one defect, and the note says so.

**Two over-broad keywords caught and scoped.**

`credit note` in XC was claiming any ticket that mentioned one — a late-payment-fee correction, a double-billed access card, and an AutoPay under-collection all landed in XC. The 14 Aug ruling was specifically that *"unable to log a credit note"* is XC, which is the portal **function**. Requesting a credit note for a billing error is Invoicing. XC now keeps only the function wording.

`document` in Documents matched the UBL rule text inside a Greek e-invoicing validation error. Dropping the bare term cost two confirmed answers — INC0768111, which the reviewer had graded Documents, and a resolved ticket about Adobe Reader — so instead it was replaced with the document **actions** those cases actually use (`file uploaded`, `delete the file`, `cannot open the file`, `adobe reader`). Same principle as `printer`: the category is about doing something to a document, not about the word appearing.

**The regression harness now lives in the repo.** It had been sitting in `/tmp` and was wiped when the sandbox restarted, which is a poor place for the one thing that has to run after every change. `measure.py` at the workspace root reports all four ground-truth sets and picks up new scorecards automatically by filename.

## Fourth scorecard — 143 rows covering every batch to 21 Aug

The first review covering the 18–21 Aug runs. Scores on the four unreviewed batches:

| | 18 Aug | 19 Aug | 20 Aug | 21 Aug | total |
|---|---|---|---|---|---|
| Category | 14/15 | 25/26 | 21/21 | 10/11 | **70/73 (96%)** |
| Routing | 14/14 | 26/26 | 21/21 | 6/10 | **67/71 (94%)** |
| Priority | 10/14 | 26/26 | 19/21 | 8/10 | **63/71 (89%)** |
| Short description | 14/15 | 22/26 | 20/21 | 10/11 | **66/73 (90%)** |
| Root cause | 11/15 | 9/26 | 12/21 | 0/10 | **32/72 (44%)** |

**Root cause was the one weak field, and it was fixable.** With 110 graded priorities and 97 usable root causes there is now enough data to rebuild the priors from what the desk actually chooses rather than from the older resolved set. Rebuilt: **44% → 67%** on the graded rows, **62% leave-one-out**. Three priors changed and one category was added:

| Category | Was | Now | Evidence |
|---|---|---|---|
| Renewals | *(absent)* | **Performance Degradation** | 6 of 10 |
| SOA | Data Corruption | **Configuration Error** | 10 of 11 |
| Login | Access Issue | **Configuration Error** | 3 of 3 |
| Bookings (Products) | — | **Unknown Cause** | 8 of 8 |

The pattern behind it: the desk reaches for `Unknown Cause` on request-type tickets and reserves specific causes for reproducible faults. `Performance Degradation` for the TeamHub renewal family is the sharpest single signal — it says the desk reads those as slowness, not a logic defect.

**Priority is at its ceiling with the supplied fields.** On 110 graded tickets the matrix alone scores 80%; the shipped rule (matrix + P1/P2 capped to P3 without outage evidence + Quick Access → P4) scores **86%**, exactly matching an empirically re-derived matrix. The residual 15 errors sit inside two cells that genuinely split — `U3×I3` gave P4 thirty-two times and P3 ten times, `U2×I4` gave P4 twelve times and P3 four. **Across 110 graded tickets the reviewer has never once chosen P1 or P2.** No further change is justified from Impact and Urgency alone.

### The scorecard's tick boxes were broken, and not by the formula

Diagnosed on request. The formulas themselves were correct; they had been **destroyed by a paste**. Across the 143 data rows:

```
2,388  cells holding a non-breaking space (looks blank, is not empty)
  588  literal ✓        121  literal ✗        (hard-coded, never recalculate)
  130  cells still holding a formula, all in rows 114-146
```

So a corrected value no longer updates its tick, and a `CHAR(160)` "blank" defeats both `COUNTIF` and the reviewer's eye. The non-breaking spaces are the signature of content pasted from a rendered table or web page.

Fixed copy written with: every tick rebuilt as a formula across rows 5–1003, `CHAR(160)` stripped, comparison made tolerant of brackets, case, spacing and `UNCATEGORISED` ≡ `Unclassified`, Dashboard ranges moved off the `INC0000001` example row, and `fullCalcOnLoad` set so Excel recomputes on open.

**A bug in my own fix, caught before shipping**: the first attempt mapped tick columns off by one and wrote formulas that referenced the tick cell itself — 25 circular references. Asserting on the generated file caught it. Verified: 0 circular references, 0 tick cells without a formula.

### Contradictions to resolve rather than encode

Four places where this scorecard disagrees with an earlier instruction, left unchanged and flagged:

- **INC0768543** — graded `Payments - Credit Card` / "Cannot pay invoice online", but on 19 Aug the instruction was that this ticket belongs to `MST-71579 Issue setting up default payment method`, which is `Payments Registration`.
- **Amend-agreement category** — INC0768359 graded `Bookings (Products)` on 18 Aug, while the same cluster's tickets (INC0768485/499/524) were accepted as `Renewals` on 19 Aug.
- **Call answering routing** — INC0768827 and INC0768872 corrected Portal → Proton on 21 Aug, but INC0768500, the same request from the same reporter, was accepted as Portal on 19 Aug.
- **Short description** — three tickets (INC0768438, INC0768500, INC0768592) were rewritten from the master's name to the ticket's own symptom, which cuts against rule 2 as implemented.

**21 Aug root causes are unusable**: ten of them hold a category name (`Accounts and Companies`, `Invoicing`, `XC (Product and Services)`, `Renewals`, `Documents`) rather than a value from the 29-item picklist. Excluded from the rebuild rather than learned from.

## JIRA connected, 21 Aug 2026 — one defect explains a whole cluster

The Atlassian connector is authorised. First pass answered questions the ticket text could not.

**TTN-143719 is the root cause behind four tickets and a cluster.** `[ENHANCE-9600] Prevent back-dated charges and double-billing on occupancy step amendments` — **Fixed, Ready For Release, fix version R26.08.01 dated 2026-08-13 but not yet released.** QA passed 17 Aug, UAT 20 Aug.

- Root cause: an `OccupancyStepId` mismatch in `MandatoryRecurringServiceHelper.AddMandatoryServices` creates a fresh `ServiceSale` with a new `SaleItemLink`, no billing history and a **backdated** `StartDate` — so billing retroactively charges every period since the original booking start.
- Second symptom: an occupant-count change leaves the original recurring row billing in parallel with the new one.
- In scope: **Kitchen Amenities, Beverages, Unlimited Coffee** on Long-Term Office and Workstation bookings.

That covers INC0768814 and INC0768331 (KA backbill), INC0768932 (Kitchen Amenity double-billed, Japan, "affecting multiple clients"), and almost certainly INC0768542 from 19 Aug (unlimited coffee and tea still billed). **The JIRA also states Operations is patching the double-billing monthly with manual credit notes** — which is exactly what the `[Invoicing] Credit note requested for an incorrectly billed charge` cluster has been recording without knowing why. Those tickets should be linked and held, not worked individually, and more will arrive until R26.08.01 ships.

**Nothing in JIRA covers the 9-ticket TeamHub renewal cluster.** CEN has two open amend-agreement bugs — CEN-49075 (renewal price incorrect after repeated saves, New, unassigned) and CEN-46754 (RENEWBOOKING action failed even when renewal succeeds, Blocked) — but neither is the production *"error occurred when trying to submit your request"* failure. Eight reporters, no tracking issue. That is now the strongest case for raising a new defect.

**PAPI-80621 supports treating the DID cluster as data corrections.** `[WITH L2] [OOMA] Customer is requesting the change of DID number`, Pending, records the portal DID not matching Cerebro because the number was **purged** there, and is explicitly logged *"for track purpose only, not for Proton team"*. It also independently confirms the owner's correction that DID work belongs to the OOMA master.

### Practical note for future JIRA use

**The connector's `fields` parameter is not honoured** — every issue returns its full description, and a 50-result search blew the token limit twice. Use `searchResultMode: "count"` first and only fetch when the count is small. Tight JQL beats broad JQL plus field selection.

## Run of 21 Aug 2026 — the TeamHub renewal cluster reaches 9

12 tickets, the smallest batch yet. All measures held: 377 resolved 88.2%, master matching 184/190, routing 98.4%, 17-Aug scorecard 20/20.

**`[Renewals] Error submitting renewal team request in TeamHub` is at 9 of 10.** Eight reporters, five batches. The sibling amend-agreement cluster is at 4. One more occurrence of either crosses the threshold.

**Another generic-phrase master match caught.** INC0767028 — a printer document that *"sits on a loading screen and never prints"* — matched `MST-71537 When trying to login via mobile, loading screen appears` on the bare phrase `loading screen`. Same family as `did number`, `staff mode` and `cc`: a common UI phrase used as a master discriminator. `Context required = login` now scopes it, which costs nothing on the benchmarks because that master's real subject is logging in.

**Printer output faults are now a tracked cluster at 3.** INC0767028, INC0768143, INC0768271. Grouped under one `[UNCATEGORISED]` name so all three stay consistent with the 17 Aug ruling that print output is not Quick Access. Worth noting INC0767028 *would* have classified as Quick Access, but only because the reporter mentions refreshing WKP from MyRegus Quick Access as a troubleshooting step — the fault is print output. That is the fourth printer ticket and the category decision is still open.

**Two tickets citing the same JIRA.** INC0768814 and INC0768331 both cite `TTN-143719` for KA backbill charges that cannot be removed — tracked as a cluster so the link is visible even though the Atlassian connector is unauthorised and the issue cannot be read.

**One ticket that is not a ticket.** INC0768846 has `test` as both its short description and its description. Flagged for closure rather than triaged.

## Run of 20 Aug 2026 — a truncated title was hiding the fault

21 tickets. **11 matched an existing master**, the highest yet, and across all batches master links now stand at **42 of 104** (14 before the owner's correction, 30 after it, 42 after this run's fix). Every ground-truth measure held: 377 resolved 88.0%, master matching 184/190, routing 98.4%, 17-Aug scorecard 20/20.

**A short description is only a title when someone wrote one.** ServiceNow truncates a pasted email into the short description at ~160 characters, frequently mid-sentence. INC0768753 cut off at *"…set as the Default Payment Preference; however,"* — so master matching, which prefers the short description, saw only the setup context and matched a payment-setup master, while the actual fault (autopay never runs) sat in the very next clause.

**The first fix was the wrong discriminator.** Using `is_pipe_structured` to decide cost 2 on the master benchmark, because plenty of genuine titles have no pipe — `[Login] Client not receiving verification code via mobile phone` was treated as body text and lost to a sibling master. The precise test is whether **the body starts with the short description**: if it does, the short description is a body prefix and there is no title to prefer, so the whole text is matched. `_is_body_prefix()` does that, and it recovered the 2 while keeping the 12 gained.

**Two clusters grew and one opened.** `[SOA] Duplicate or invalid posting in MyRegus needs reversing` at **5** — the mirror image of the D365-sync cluster: there the record never arrived, here it arrived twice or wrongly. Staff Mode bookings reached 3.

**Volume worth reporting even when a master already exists.** Eight tickets now sit under `MST-71283` (wrong DID on the MyRegus profile) across five batches, three of them on the same day, and every reporter states the correct DID in the ticket — which reads as data correction rather than a code defect. Six sit under `MST-71218` (autopay not collecting). A master existing is not a reason to stay quiet about the rate.

## The master audit was wrong — masters are BROADER than their wording

**Retracted: the "6 of 46 links were wrong" audit below.** The owner's correction — *"you didn't use masters correctly, there are more of them that you should have used"* — was the opposite of my conclusion, and they were right.

**MST-71283 "OOMA issues with DID" is the registry's only home for DID and call-answering issues.** OOMA is the telephony platform behind Call Answering; a reporter has no reason to name it. So a "wrong DID on the customer profile" ticket *is* an OOMA/DID ticket. My audit unlinked four correct links on the reasoning that the word never appears.

**The test I built that on was measuring label leakage.** I found that "all 33 resolved tickets under MST-71283 mention OOMA" and treated it as proof the word must appear. All 33 of those tickets have the master name pasted into their short description — so of course it appeared. The test contained no independent evidence at all, and I used it to justify a `Context required` gate.

**The general error: I was reasoning from text presence rather than domain reality.** A master is the desk's name for an underlying issue, and the underlying platform, product or mechanism is usually *not* in the reporter's words. Under-linking is worse than it looks, because a ticket with no master silently becomes a candidate for a new cluster — I twice proposed clusters for issues that already had masters, once in each direction.

**Net effect of the reversal**: master links across all batches went from 14 to **30 of 83**, no low-confidence ties left, and every ground-truth measure held (377 resolved 88.0%, master matching 184/190, routing 98.4%). The one point lost on the resolved-category set comes from masters now driving more categories, which is the correct behaviour.

Links restored or newly found:

| Ticket(s) | Master | How it was missed |
|---|---|---|
| INC0767819, INC0767855, INC0768158, INC0768538, **INC0768500**, INC0767995 | `MST-71283 OOMA issues with DID` | Required the literal word "OOMA" |
| **INC0768543**, INC0768427 | `MST-71579 Issue setting up default payment method` | "cannot pay AND cannot add" read as a tie between two masters instead of one master's issue |
| INC0768542 | `MST - 011-25 Recurring services charged after termination` | Read "termination" as whole-agreement only |
| INC0768438, INC0768592 | `MST-71218 Autopayment not working` | Delayed deduction and under-collection are autopayment failures |
| INC0768546, INC0768590 | `MST - 002-25 Account needs activation` | An inactive or unactivated account needs activation |
| INC0768571 | `MST-70822 Error logging in to MyRegus staff mode` | "Staff Login Issue" is staff mode |

**Two clusters retracted** because the registry already covered them: the DID-on-profile cluster (→ MST-71283) and the card add-and-pay cluster (→ MST-71579).

### What replaces the bad heuristic

When testing a candidate master link, ask **what the master is about**, not whether its words appear:

1. **Is this the same underlying issue?** The platform, product or mechanism in the master's name is often absent from the ticket. DID display problems are OOMA issues; staff login problems are staff mode.
2. **Is there another master that covers it better?** MST-71283 is the *only* DID master, so a DID ticket goes there unless a more specific one exists.
3. **Beware evidence that could be label leakage.** If resolved tickets carry the master name in their own short description, any test over their text is circular.
4. **Prefer linking to a plausible master over leaving a ticket unlinked.** An unlinked ticket becomes cluster-proposal fuel and can duplicate the registry. Flag a Medium link for confirmation instead.

The audit below is kept for the record. Its process — checking every link — was right; its conclusions were mostly wrong.

## Retracted audit, 19 Aug 2026 — "6 of 46 links were wrong"

Prompted by the owner: "you have made multiple issues with incorrect masters". Every ticket→master link asserted since 12 Aug was re-checked against the master's own scope. **6 of 46 were wrong**, and all four fixes cost nothing on any ground-truth set.

| Ticket(s) | Was linked to | Why it was wrong |
|---|---|---|
| INC0767819, INC0767855, INC0768158, INC0768538 | `MST-71283 OOMA issues with DID` | Matched on the bare keyword `did number`. **All 33 resolved tickets under that master mention OOMA. None of these four does** — they are Call Answering DID *display* problems. |
| INC0768542 | `MST - 011-25 Recurring services charged after termination` | I added `no longer in recurring sales` **to make this ticket match**. The agreement is not terminated. |
| INC0768546 | `MST-71215 Client unable to log in (not verified, suspended, locked)` | Matched on `unable to log in` — the category-level symptom, not a discriminator. The account is *inactive* and the client is *new*. |

**The common failure is keyword-fitting: adding or accepting a keyword that describes the TICKET rather than the MASTER'S issue.** Three tests would have caught all six, and are now part of the process:

1. **Does the master's own subject appear?** OOMA is in the master's name. A DID ticket with no OOMA in it cannot be an OOMA ticket. `Context required` exists for exactly this and is now set on MST-71283.
2. **Is the matching keyword a discriminator or a category-level symptom?** `unable to log in` is what makes a ticket *Login*; it cannot also be what makes it one specific Login master.
3. **Do the resolved tickets under that master look like this one?** Decisive here: MST-71215 and MST-011-25 both have **zero** resolved tickets, so the keywords I added to them were serving nothing — a strong signal I had invented a link rather than found one.

**The four DID tickets were a hidden cluster.** Because a master was claiming them, they never reached the tally. Unlinked, they are `[XC (Product and Services)] Incorrect DID number shown on MyRegus profile` at **4 across three batches** — a real recurring issue that a wrong master had been concealing. Routing is unaffected: the DID→Proton rule is separate and the reviewer confirmed it.

**A caution about weak confirmation.** The reviewer graded INC0767819 and INC0767855 and corrected only their *routing*. I read that as endorsement of the whole row. It was not: both tickets' category is `XC` whether or not the OOMA master applies, so a category tick carried no information about the master link. **A ✓ on a field that a wrong link would not have changed is not evidence the link is right.**

Kept after review, with reasons: INC0768004/032/420/422 → `Cannot pay invoice online` and INC0768037 → `Autopayment not working` all match the master's issue directly even where the keyword is a paraphrase. INC0768238 → `MST-71223` is a genuine match — the client disputes accepting a renewal — but that master sits under Short Stay while this is a Titan office agreement, so the *category* is flagged rather than the link.

**Assertions now run inside the runner**, so a bracket/category mismatch, a blank name, or a `ChildTicket` without an MST tag fails the run instead of reaching the workbook.

## Impact and Urgency now arrive on the export

From this batch the export carries `Impact` and `Urgency` columns. **Use them; do not infer.** Priority becomes a straight matrix lookup, which is the same principle as the Assignment group: a field the export supplies is not second-guessed. The P1 outage cap still applies. Every Impact supplied so far is 3 or 4, which is consistent with P3 being the working default.

## Benchmark expanded to 3,716 tickets, 24 Aug 2026

`training 2.xlsx` (Feb 2024 – Aug 2026, 3,361 rows from 2026) replaces the 623-row set as the
resolved-ticket benchmark. It multiplies the two tag-derived truth sets by roughly six:

| Truth set | Was | Now |
|---|---|---|
| Category, from `Tags` | 377 | **2,370** |
| Master, from `MST-` tags | 190 | **1,237** |
| Routing, from the desk's group | 623 | **0 — column absent** |

**All 1,237 MST tags resolve to a master in the registry, none unmapped.** That is the single
most reassuring number here: the registry is not drifting away from what the desk actually tags.

Measured on it, with rows opened from **1 Jul 2026** held out and reported separately:

| | All | Held out (≥ 2026-07-01) |
|---|---|---|
| Category | 2049/2370 = **86.5%** | 297/338 = **87.9%** |
| Master | 1192/1237 = **96.4%** | 140/141 = **99.3%** (0 gaps, 1 wrong) |

### 86.5% is not a regression from the recorded 89.5%

Different set, six times larger, reaching back two years. Broken down by quarter the older
labelling is plainly the drag, and current practice is flat against the old figure:

```
2025Q3   21 rows  66.7%      2026Q1  910 rows  88.4%
2025Q4  156 rows  80.8%      2026Q2  942 rows  85.7%
                             2026Q3  338 rows  87.9%
```

The ~180 pre-2026 rows pull the headline down by about two points. **Score the holdout, not the
headline**, when judging a change.

### A real weak spot the small set was hiding

Accuracy by category, where there are at least 30 rows to judge on:

| Category | Rows | Correct |
|---|---|---|
| Bookings (Products) | 52 | **48.1%** |
| Invoicing | 101 | 70.3% |
| SOA | 80 | 78.8% |
| Accounts and Companies | 138 | 81.2% |
| Bookings (Products) - Short Stay | 202 | 82.2% |
| Payments Registration | 262 | 86.3% |

`Bookings (Products)` losing more than half its rows is worth a keyword pass on its own — it was
invisible at 377 rows. Note it also sits behind two known contradictions: the amend-agreement
tickets split between `Bookings (Products)` and `Renewals`, and its root-cause prior was set to
`Unknown Cause` on 8 of 8. Resolve the contradiction before tuning keywords, or the tuning
chases a moving label.

### What this export cannot measure, and why

- **Routing.** No assignment-group column, so the 623-row routing check is gone rather than
  reduced. The harness now says `SKIPPED` instead of dividing by zero.
- **Priority.** There is no `Impact` column, and `Severity` is the constant `3 - Low` on all
  3,716 rows. The matrix is urgency × impact, so it cannot be re-derived from this file.
- **Root cause.** No resolution-code or close-notes column. Root cause is still scorecard-only.

A re-export carrying `Assignment group`, `Impact` and the resolution code would close all three.

### Contamination, and the holdout that answers it

25 of the 139 scorecard-graded tickets are inside this export. Fitting on the whole file and then
quoting scorecard accuracy would be scoring partly on training rows — hence the 1 Jul cut.

Two harness changes came out of this and matter beyond it. Scorecard rows now fall back to the
training export for ticket text when a batch export is missing, but **routing is skipped for
those rows**: they carry no supplied group, so scoring them measures the fallback rule rather
than the shipped "the group on the export wins" behaviour, and it reads as a 76% routing
regression that does not exist. And the run now prints a warning when no batch export is found
at all, instead of printing an empty scorecard section that looks like a pass.

## KBA index refreshed to 620 articles, 24 Aug 2026

A full `kb_knowledge` export replaced the 396-article index. It is a clean superset — every
existing KB Number is present, 224 are new, no duplicates within the export, and nothing in the
old index is missing from it. So this was a rebuild rather than a merge.

**What had to be carried across by hand.** The export has no memory of the mapping work: 36
rows carry a `Covers master ticket` value (10 High confidence, 26 Medium) and 6 carry Notes.
Those are human judgement and nothing regenerates them, so `rebuild_kba_index.py` joins them
back on KB Number and refuses to run if any existing KBA is absent from the export.

**Two format facts the export does not tell you.** ServiceNow ships `Article body` as raw HTML
— all 553 non-empty bodies — while the index stores prose, so the rebuild strips tags and
entities. And `Search text` is capped at **1200 characters**: 126 rows in the old index sat
exactly at that length, which is a deliberate guard against the query dilution recorded above,
not an accident. Raw bodies average 5,121 characters, so dropping the cap would have quintupled
document length and diluted every query.

`Knowledge base` replaces the old `Audience` vocabulary. The mapping was derived from the 396
overlapping rows rather than guessed, and is unambiguous — every value maps to exactly one
audience, no conflicts:

```
IT L1 Service Desk KB -> L1        Customer Support -> Customer Support
IT L2/L3 Technical KB -> L2        End-User Support -> End User
Centre Support        -> Centre Support    Known Errors -> Known Errors
```

### Effect: coverage up, accuracy still unmeasured

Category and master matching are **unchanged to the decimal** (86.5% / 96.4%) — the KBA index is
built separately from master matching, so extra articles cannot degrade them. That is the whole
risk profile of this change.

On 600 sampled tickets:

| | 396 KBAs | 620 KBAs |
|---|---|---|
| Ticket gets any suggestion | 498/600 = 83.0% | **549/600 = 91.5%** |
| Top hit rated *strong* | 34 | **45** |

**89 tickets had their top KBA change to a different article.** That churn is not validated —
`measure.py` has no KBA metric at all, because there is no ground truth for which article the
desk actually used. Coverage rose; whether the suggestions are *better* is unproven, and
should not be reported as if it were.

Closing that gap needs tickets labelled with the KBA the desk actually applied. Until then the
KBA column stays a suggestion to confirm, like root cause.

67 articles arrived with no body and are indexed on title alone, so they match weakly.

## Run of 23 Aug 2026 — a cluster placement that would have created a wrong master

Four tickets. The most valuable thing in this batch is a near miss.

**INC0769090 nearly went into the wrong renewals cluster.** It reads *"Sorry! An error occurred
while renewing recent termination"*, and `[Renewals] Error submitting renewal team request in
TeamHub` was sitting at **9 of 10** — so placing it there would have crossed the threshold and
triggered a new master. It does not belong there. The reporter's path was `Company > Amend
agreement > Select booking(s) > Renew recent termination`: the amendment **itself** failed. The
9-count cluster is the *handoff to the renewals team* failing — "submit your request", "central
renewal support", "connect to centralized renewals". None of that appears here.

It went to the sibling `[Renewals] Error when amending an agreement in TeamHub`, which is now
**5**. The distinction is the one the sibling's own comment warns about, and this is the first
time it has actually mattered: getting it wrong would have created a master for an issue seen
nine times, merged two distinct faults under one name, and stopped anyone counting the real one.

### Two keyword gaps, one of which also corrupted a priority

Both tickets fell through to `Unclassified` on symptom text and then took whatever the pipe hint
gave them:

| Ticket | Was | Should be |
|---|---|---|
| INC0769018 "Unauthorized company name change on customer account" | Quick Access | **Accounts and Companies** |
| INC0768988 "Primary and secondary Customer not receiving monthly invoice email" | Unclassified | **Invoicing** |

The first also **changed the priority**: the shipped rule sends Quick Access to P4, so a
misclassification silently downgraded a ticket that the matrix grades P3. Category errors are
not confined to the category column.

Keywords added — `company name change`, `company name was changed`, `company name changed
without`, `unauthorized company name` to Accounts and Companies; `not receiving monthly invoice`,
`not receiving invoice email`, `invoice email has not been received` to Invoicing. All four rows
now classify from the symptom rather than the hint fallback. Measured: **no change**, 86.5%
category and 96.4% master, exactly as before — the terms are narrow enough not to disturb
anything else.

### A defect found and deliberately not fixed

`pipe_hint()` ends in a loose token-overlap fallback that accepts a match on **one** shared word,
and breaks ties by category precedence order. `Accounts & Access` shares exactly one token with
`Quick **Access**` and one with `**Accounts** and Companies`. Quick Access wins purely because it
is tested first.

That is arbitrary, and any two-word hint whose words straddle two categories hits it. Tightening
it — requiring two shared tokens, or scoring by overlap ratio — is a change to `classify.py` with
a much wider blast radius than a keyword addition, so it is recorded here rather than made
mid-run. **It should be tested against the benchmark before shipping, not reasoned about.**

Fixing the symptom keywords makes the hint moot for these two rows, but the defect is still live
for every ticket whose symptom does not classify.

### Still open from this batch

**INC0768982** — *"OSA sending shows inconsistent office content"* — classified
`Contract API/Agreements` on the `osa` keyword. The OSA sent successfully; the fault is that the
webmaster message arrived twice, first with one office and then with both. That is a notification
duplication, not agreement state being wrong, and it matches no existing cluster or master. Left
unclustered at a single occurrence rather than opening a cluster for one ticket. Worth watching:
if a second arrives it is a genuine new cluster, not a member of the amend-agreement one.

## Run of 26 Aug 2026 — 11 tickets, and a master matching on a troubleshooting tool

**The renewals cluster reached 10.** INC0769490 is verbatim the cluster symptom — Meisha Adams
enters a comment on a renewal team request, clicks Continue, gets *"An error occurred while
trying to submit your request. Please log an IT Ticket."* Nine reporters, six batches, still no
JIRA. The script's rule is `n > 10`, so 10 does **not** trip it and the sheet reads "1 more
needed". It has sat at or near threshold since 19 Aug and is worth raising on the count alone.

`[Bookings (Products)] Cannot rollback a booking terminated while provisional` went 3 → 5 on
INC0769483 and INC0769513. **Both cite the same booking reference, 172355166**, under different
reporters and company names, so they may be one occurrence reported twice — which would make the
real count 4. Counted as two and flagged; nothing turns on it at this distance from 10.

### A master matched on a tool name from the troubleshooting section

INC0769494 — *"Wrong credit card is showing up on MyRegus"* — matched
`[XC (Product and Services)] OOMA issues with DID` and was renamed to it. The only evidence was
the single keyword **`callstream`**, which appears in the ticket solely as a step the agent took:
*"Checked whether the affected record has a Titan ID in CallStream Manager."* CallStream Manager
is an internal lookup tool, not a symptom.

This is the "Troubleshooting attempted" trap again, but reaching through a **master keyword**
rather than a category one, which makes it worse: rule 2 gives the master authority over the
category, so a correct pipe hint of `Payments - Credit Card` was overridden by a false master.

The evidence for removing it was unambiguous. Across the 3,716-ticket benchmark, `callstream`
appears **once** — on an Invoicing ticket about charges aligned to the wrong company, with no
OOMA, DID or call-answering wording and no MST tag. The keyword has never once identified an
OOMA ticket. Removed; category and master both unchanged at 86.5% / 96.4%, and INC0769494 now
classifies correctly as Payments - Credit Card at P3 rather than P4.

**A bare tool name is not a symptom keyword.** Worth auditing the other masters for the same
shape.

### Two rows left wrong on purpose, because the fix is not a keyword

INC0769416 and INC0769431 both classified as **Login**, which then routed them to **L2 - Proton**
by the standing owner rule — overriding the group on the sheet, and reporting no mismatch because
the override is by design.

- **INC0769431** — *"TeamHub | Performance Issue | outage affecting Finland centres after
  reinstall and login"*. The symptom is a TeamHub outage stopping agreement processing across
  multiple Finland centres. "login" appears only as remediation the reporter already tried. This
  is a **P2 multi-centre outage sitting in the wrong queue**, and it is the most operationally
  serious error in the batch.
- **INC0769416** — *"issues in Edicom - India ... invoices rejected and we are unable to log
  in"*. Edicom is a third-party e-invoicing provider. The login is to **Edicom**, not to a
  Proton-owned surface.

Neither is a missing keyword: the word *login* is genuinely present in both, in the symptom text
rather than a troubleshooting block, so stripping troubleshooting sections would not catch them.
Fixing them means teaching Login to require an IWG authentication surface, or to yield when a
concrete non-auth failure is also present — a `classify.py` change with wide reach, which
BENCHMARK says to test against the benchmark rather than make mid-run.

Recorded rather than fixed, and both flagged to the desk. **Because Login overrides the sheet, a
category error here becomes a routing error** — the one place where getting the category wrong
silently moves a ticket to another team.

## Owner corrections, 26 Aug 2026 — and a naming rule that made them unreachable

Three rulings on the 26 Aug batch, all encoded and regression-tested.

| Ticket | Was | Owner's ruling |
|---|---|---|
| INC0769440 | Unclassified | **SOA** |
| INC0769560 | Unclassified | **Enquiry** — a new category |
| INC0769568 | Unclassified | **XC (Product and Services)** |

**`Enquiry` is a new category**, precedence 10, for Sales Hub enquiry state and transitions —
cannot be set to WON, or locked after a prior status. Every keyword chosen for it returns **zero
hits across the 3,716-ticket benchmark** (`sales hub enquiry`, `set enquiry to won`, `set to
won`, `relivened`, `parent enquiry`, `child enquiry`), so a new precedence-10 category cannot
steal rows from an existing one. Confirmed: category and master unchanged at 86.5% / 96.4%.

The other two rulings were checked against the benchmark before encoding rather than taken on
trust, and both are corroborated: `titan balance` appears once, tagged **SOA**; `recurring tab`
appears three times, one tagged **XC (Product and Services)**. A third candidate, `immediate
invoice`, was **rejected** — 25 tickets with no category consensus. Precision beats coverage.

### The naming defect: a hand-written name could never win

The owner also objected to INC0769440's short description, which read *"[SOA] Provide the Titan
balance for the following accounts in"* — free-form email truncated mid-sentence. `MANUAL_NAME`
entries were added, and the run kept emitting the old text.

The branch order was:

```
if <cluster> ... elif tid in PRIOR ... elif tid in MANUAL_NAME ... else <drafted>
```

`PRIOR` holds names carried forward from earlier run workbooks. Any ticket a previous run had
already named therefore hit `PRIOR` first, and **`MANUAL_NAME` was unreachable for it**. The
entry was silently ignored, and only the bracket was realigned — which made it look like the
correction had partly landed.

That inverts the intent. A human naming a ticket is the strongest signal available; a drafted
name carried forward is the weakest. `MANUAL_NAME` now sits above `PRIOR`, and an override
against a differing prior name is recorded on the Review sheet. Rule 2 still holds — one issue,
one name — because the hand-written name is what later runs carry forward.

**This defect scales with age.** MANUAL_NAME worked when a ticket was named for the first time,
so it looked correct in testing; it only failed on re-triage, which is exactly when a human is
correcting something. Any earlier hand-written name added for an already-triaged ticket was
also being discarded.

INC0769409 was given a hand-written name at the same time — same truncation, category not in
dispute. INC0769416 has the same problem and was deliberately left alone: its Login category is
flagged as wrong above, and naming it would bake that in.

### Owner correction: INC0769416 is not a login fault at all

I read *"New invoices issued since Aug20 were rejected and we are unable to log in"* as a login
problem at a third party, and said so. Wrong on the substance, not just the routing. The reported
fault is that **invoices were rejected by Edicom**, the India e-invoicing platform; "unable to log
in" is a *second symptom of that same outage*, not the issue being raised. Correct category is
**Invoicing**.

The benchmark supports it. All four tickets mentioning `edicom` are invoice or credit-note
failures — reissuing CNs not uploaded during an "Edicom suspension", hotfixing CNs for posting —
and one arrives pipe-hinted `E-invoicing | Invoicing issue`. None is an authentication problem.
Three of the four currently classify as Unclassified, so `edicom` should pick them up too.

Added to Invoicing: `edicom`, `e-invoicing platform`, `invoices were rejected`. Category and
master unchanged at 86.5% / 96.4%.

**Routing corrected itself.** With the category right, the Login -> Proton override no longer
fires and the group falls back to the sheet: `L2 - Titan`, source `sheet (authoritative)`. This
is the concrete demonstration of the point recorded above — where Login overrides the sheet, a
category error *is* a routing error, and fixing the category fixes both.

The source short description is truncated mid-word (`... unable to log `), so the name is written
by hand from the body: *"[Invoicing] Invoices rejected in Edicom India since 20 Aug"*.

**A caution for reading these tickets.** Two symptoms in one sentence do not carry equal weight.
"X was rejected **and** we cannot log in" reports one fault with two consequences, and the
classifier matched the second clause because `log in` is a stronger keyword than anything in the
first. Only INC0769431 now remains on the wrong side of this — there the word *login* describes
remediation already attempted, not a symptom at all.

## Fifth scorecard, 26 Aug 2026 — 186 rows, and the Login override narrowed

The reviewer's grading of the 26 Aug batch corrected four categories and one routing, and
**corrected me on a claim I had made twice**.

### I argued INC0769431's category was wrong. It was not.

I recorded, in two places, that classifying INC0769431 as `Login` was an error — the ticket is a
TeamHub outage and "login" appears only as remediation the reporter had tried. The reviewer
graded the category **Login** and moved the *routing* to `L2 - Portal`.

So the category was right and only the destination was wrong. The lesson is narrower than the
one I drew: a ticket can genuinely be about signing in and still not belong to Proton.

### The override is right 6 times in 7 — so it stays, but scoped

Across every row the reviewer has graded as Login:

```
INC0767607  INC0767639  INC0768546  INC0768571  INC0768590  INC0769406   -> L2 - Proton
INC0769431                                                               -> L2 - Portal
```

Deleting the override to fix one row would have broken six. Instead it now requires the login to
be the **fault** rather than a passing mention.

Of the 22 Login keywords, exactly one — a bare `login` — can match a ticket where signing in is
incidental. Every other names a failure: `unable to log in`, `account blocked`, `verification
code`, `otp`, `password reset`. `_login_is_the_fault()` requires one of the specific terms, and
the two cases separate cleanly:

| | Matched on | Routes to |
|---|---|---|
| INC0769406 *"unable to log in to Customer Portal - account blocked"* | specific | Proton (override fires) |
| INC0769431 *"...after reinstall and login"* | bare token only | Portal (sheet wins) |

The term list is held in `classify.py`, **not** read from `categories.csv`, so that adding a
keyword for classification cannot silently move tickets between teams. That should be a separate
decision.

**This is not verified by `measure.py`.** The routing check is skipped for want of an assignment
-group column in the benchmark export, so the change rests on the seven graded Login rows and
direct tests of the two with recoverable text. Narrower evidence than a keyword change, and it
should be re-checked when a routing-capable export exists.

### Batch result after the corrections

**Category 11/11, routing 11/11, priority 10/11.**

### Priority is the weak field now, and the "never P2" finding is dead

Across all 186 graded rows priority agrees **136/166 = 81.9%**, down from the 86% recorded at 110
rows. The earlier note that *"across 110 graded tickets the reviewer has never once chosen P1 or
P2"* no longer holds: **P2 has now been chosen twice**, both in this batch. P1 still never.

Disagreements, largest first:

```
16  AI P4 -> human P3      10  AI P2 -> human P3      2  AI P2 -> human P4
 1  AI P3 -> human P4       1  AI P4 -> human P2
```

Two opposing errors, not one: the grid under-rates a large group of P3s as P4, and over-rates a
smaller group as P2. That is not a matrix that needs shifting in one direction.

The single miss this batch, INC0769459, shows the mechanism. The export supplies `Impact 4 - Low`,
which with `Urgency 2 - High` grids to P4. The body says *"it is not only this customer. The
problem exists with all customers and types of customers."* Per `priority-impact.csv` that is
Impact **2**, "widespread issue". The supplied Impact contradicts the ticket's own words.

**Not fixed.** Impact is explicitly a human decision, and overriding a supplied field from body
text is exactly the kind of second-guessing that has cost accuracy before. The right move is to
*surface* it — flag on Review when the body states a scope wider than the supplied Impact — and
leave the grade alone. Recorded for a decision rather than done.

## Run of 27 Aug 2026 — 17 tickets, five keyword gaps, no new clusters

Tally pin advanced to `Triage_2026-08-26_v2.xlsx`, the reviewer-graded run (category 11/11,
routing 11/11). One registry master matched: INC0769774 to MST-71579 *Issue setting up default
payment method*. **No cluster gained a member**, which is the correct outcome rather than a
missing step — none of the 17 repeats a tracked symptom.

### Five categories were falling through, four now fixed

| Ticket | Was | Now |
|---|---|---|
| INC0769659 upload fails in TeamHub | Accounts and Companies *(pipe hint)* | **Documents** |
| INC0769701 balance paid on invoice, still overdue | Unclassified | **SOA** |
| INC0769722 Proton absence file not produced | Unclassified | **Staff - Attendance and Timeoff** |
| INC0769780 rejected invoice | Unclassified | **Invoicing** |
| INC0769677 guest code not working on OTR | Bookings (Products) | *unresolved — see below* |

Every candidate keyword was probed against the benchmark first, and **two were rejected**:

- **`authentication code`** splits **Login 10 / Quick Access 7** across 18 tickets. Genuinely
  ambiguous in the desk's own labelling, so adding it to either category would encode a coin
  toss.
- **`unable to upload`** splits Documents 6 / Mobile 3 across 15. Used the precise phrases
  instead (`uploading documents`, `upload client files`, `uploads fail`), all zero-hit and
  therefore incapable of stealing an existing row.

`balance mismatch` was also left alone: 87 tickets, SOA-dominant at 20 but far too broad.
`showing as overdue` (zero hits) does the job for INC0769701 without the blast radius.

Category and master unchanged at 86.5% / 96.4%.

### INC0769677 is left wrong, because the evidence points two ways

*"OTR | Authentication Issue | Authentication Code/Booking Reference is not working on OTR"*,
body describing a guest code failing after ACA checks. It classified **Bookings (Products)**
purely on `Booking Reference` in the title — a reference number the reporter quoted, not the
fault. That much is clearly wrong.

What is right is not clear. ACA is access control, which argues Quick Access; but the benchmark
says `authentication code` leans **Login**, 10 to 7. Forcing either would be guessing at a
domain distinction, so it is flagged for the desk rather than encoded.

### Ten hand-written names

Free-form email and form-field openers drafted into truncated sentences or strings of account
numbers — INC0769788 produced *"12206491Company Name: Wocu Monitoring S.L.Case ID: C--R9T3"*,
where the ID-stripping regex had also eaten part of the case reference. All ten replaced.

### Open for the desk

- **INC0769654** — Titan requires a CIN for the *Not GST Registered* fiscal status in India.
  Unclassified, and no category obviously fits a tax-configuration rule. Needs a ruling.
- **INC0769721** — the title says *"Unable to view enquiries assigned to me - No results found"*
  while the body describes *"incorrect pricing and availability"*. Two different faults in one
  ticket; the category `Enquiry` follows the title. Worth confirming which is real.
- **INC0769610** — supplied `Impact 4 - Low`, but the body says the day-office booking failure
  hits *"all the clients"* at Vienna Kohlmarkt. A single centre is impact **2** by
  `priority-impact.csv`. Second batch running where the supplied Impact contradicts the ticket's
  own words; see the INC0769459 note above. Still not overridden — impact is a human decision.
- **The `[SOA] Balance Mismatch` decision is now overdue.** INC0769638 and INC0769701 are both
  balance mismatches. The registry master of that name still has **no MST tag**, so it cannot
  claim them, and folding them into the D365-sync cluster would worsen the naming problem
  already recorded against it. Allocate the tag or scope the master's keywords.

### Owner rulings on the 27 Aug batch

**INC0769677 is Quick Access.** The owner supplied the domain fact the ticket does not state:
the authentication code is the **WiFi code a customer is issued while a booking is active**. So
the booking reference is context for the code, not the subject of the fault — and the code is
access, not sign-in.

Bare `authentication code` was still **not** added to Quick Access. It appears on 10 Login-tagged
benchmark tickets, and Quick Access outranks Login on precedence, so adding it would have
captured all ten. Inspecting those 17 tickets shows the split is by phrase shape, not by any
mention of WiFi:

```
Quick Access   "error when trying to GET authentication code"   "authentication code EXPIRED"
Login          "page STUCK ON authentication code"   "customer LOGS IN and gets..."
               "not receiving VERIFICATION CODE OTP via email"
```

Encoded that shape — `get authentication code`, `authentication code expired`, `authentication
code is not working`, `authentication code/booking reference`, and the WiFi variants — rather
than the bare term. Category and master unchanged at 86.5% / 96.4%.

Renamed away from the leading `Booking Reference`, which was what pulled it to Bookings in the
first place.

**Its priority moved P3 -> P4 as a side effect.** The shipped rule sends Quick Access to P4, and
this ticket's `Impact 4 / Urgency 1` would otherwise grid to P3. That is the same rule that, in
reverse, cost INC0769018 a grade on 26 Aug when its category moved *off* Quick Access. Flagged
rather than special-cased: a category ruling silently regrades the priority, and the desk should
see that it happened.

**INC0769654 stays Unclassified**, confirmed correct by the owner pending a new category for
tax and fiscal configuration. **INC0769721 confirmed correct** as Enquiry.

## Run of 28 Aug 2026 — a different export shape, and a feedback loop that erased a category

Seven tickets, and **not the daily batch export**. This is an *In Progress* backlog pull: five of
the seven already carry `TriagedTicket` tags from earlier runs, and the column set is the
resolved/closed shape — **no `Assignment group`, no `Impact`**.

### It crashed, and that was the right thing to notice

`find_group_column` returned None and `s[gcol]` raised `KeyError: nan`. Fixed in three places, and
the run now says up front what the missing columns cost it:

- **Routing is rule-derived for every row.** "The group on the export wins" has nothing to defer
  to, so the group column here is a *suggestion*, not a triage.
- **Priority cannot be gridded at all** and every row is blank. Correct behaviour — impact is a
  human decision and there is no impact to read — but a whole column of blanks looks like a bug
  unless the run says why.

### The feedback loop: our own names erase the category on re-triage

INC0769721 was `Enquiry`, confirmed by the owner on 27 Aug. On re-triage it came back
**Unclassified**.

The desk writes the triaged name back into ServiceNow, so the ticket re-exported with *our* title:
`[Enquiry] Error - No results found`. That string contains no Enquiry keyword — the word
"enquiry" survives only inside the bracket we wrote — so classification found nothing and fell
through.

**Any ticket we name and then re-triage is exposed to this**, and it gets worse as more names are
written back. The fix reads the leading `[Category]` bracket, placed deliberately **last** in the
chain: a positive symptom match still wins, so it can only recover a category, never entrench an
old one over fresh evidence.

Measured, it is not just a fix for this batch — **category rises 86.5% -> 87.0%** (2049 -> 2063 of
2370). Fourteen benchmark tickets were losing their category the same way.

### Enquiry had no routing row

Three rows came back `NEEDS CONFIRMATION`: the new `Enquiry` category was never added to
`groups.csv`, so with no sheet value to fall back on there was nothing to route by. Added
`Enquiry -> L2-Sales Apps Support`, which is what the reviewer assigned both graded Sales Hub
tickets (INC0769382, INC0769560).

**Not verifiable by `measure.py`** — the routing check is still skipped for want of an
assignment-group column in the benchmark export. It rests on those two graded rows.

**Adding a category means adding its routing row.** `Enquiry` was created on 26 Aug and this was
missed; it stayed invisible for two runs because the sheet supplied the group both times.

### Open

- **INC0764296** is a Sales Hub ticket classified `Accounts and Companies` and therefore routed
  `L2 - Portal`, not Sales Apps. Its subject is a missing centre-manager contact record, so the
  category looks right and the routing follows from it — but the desk may want Sales Hub tickets
  with Sales Apps regardless of category. Flagged, not forced.
- Its drafted name was *"Contact details for the manager of are missing"* — `LABELLED_ID` strips
  `center <digits>`, which is right for a trailing reference and wrong mid-sentence. Hand-named.

## Run of 28 Aug 2026 (real batch) — 15 of 35 were unclassified, and why

The first file supplied for 28 Aug was an *In Progress* backlog pull; it was replaced with the
daily batch. The backlog run is kept as `Triage_2026-08-28_backlog*.xlsx` so it still supplies
prior names without being mistaken for the day's triage.

35 tickets. The first pass left **15 unclassified — 43% of the batch**. Almost all of one family.

### Thirteen tax-authority clearance failures, and they need their own category

Egypt, Croatia, Greece, Romania, Panama and Malaysia, all invoices rejected or stuck at a
national e-invoicing authority: `[ETA error] Error Code: 4604`, `Upload Failed`, `Número del
documento fiscal duplicado`, `IN PROGRESS - LPF invoices`, `Stamp duty amount of correlated
invoice is exceeded`.

**They were splitting five to Invoicing and eight to Unclassified on incidental wording** — the
same fault reading two different ways depending on whether the reporter happened to write a
sentence or paste an error dump.

The benchmark says what the desk actually does with them, and it is not a category at all:

```
eta error                 25 tickets   no category tags
in progress invoices       7 tickets   no category tags
einvoice                  48 tickets   no category tags
                          tagged instead: EI-19031, EI-18594, "Pending EI team", "ETA chased"
```

**These go to a dedicated E-Invoicing workstream and are never category-tagged.** That is why no
category fits: the desk does not use one.

**Proposed: an `E-Invoicing` category** for tax-authority clearance and submission failures. 13 in
this batch alone, 48+ in the benchmark. This is the same shape as the printer decision and the
tax/fiscal one raised for INC0769654 on 27 Aug — three categories now waiting on a ruling.

Until then they are classified **Invoicing** as an interim, which is defensible under its own
definition — *"invoice not raised, incorrect..."*, and an invoice rejected by a tax authority has
not been raised. Recorded so the interim is not mistaken for a judgement that Invoicing is right.

**They are NOT a cluster.** Thirteen tickets would trip the 10-ticket rule immediately, but a
cluster is a claim that several tickets are *the same issue*, and these are six different
countries with different authorities and error codes. Same class, not same fault. Filing them as
one master would create a master nobody could act on.

### The rest of the batch

`balance mismatch` was finally added to SOA. It was rejected on 27 Aug as too broad — 87 tickets
— but it is SOA-dominant at 20 with no rival, and measured it costs nothing: **category 87.0% ->
87.1%**. Two more balance-mismatch tickets landed today (INC0769801, INC0769804), making four in
two days, which makes the still-untagged `[SOA] Balance Mismatch` master more overdue, not less.

INC0769807 read as unclassifiable but is a card fault: a CC confirmation email stated MYR 884.12
deducted when MYR 82.12 left the account, plus a double deduction the previous month.

Final: **0 unclassified of 35**, 4 matched to registry masters, no cluster credited.

### Owner ruling, 28 Aug: the short description must EXPLAIN the issue

*"Short description needs to be a one line explanation of the issue, you just cut the words from
what is already there."*

Correct, and it is what the drafter does by design. `propose_master_name()` strips filler,
labelled IDs and trailing clauses, then truncates. On a pipe-structured ticket that works,
because the last pipe segment is already a one-line statement of the fault. On free-form email or
a pasted error dump there is no such sentence to recover, so it returns the opening words:

```
[Invoicing] Related ticket INC0761699 /Hello Team,We encountered a recurring issue
[Memberships] Davies Technology Solutions Limited () Membership account. The account
[Invoicing] CROATIAERROR: Upload FailedINVOICES:7247-26--26--26--26--26--26-1879Please check
[Payments - Credit Card] Jiseung Lim 0127 This client registered their credit card
```

The third also shows `LABELLED_ID` eating repeated invoice numbers mid-string and welding the
remains together.

**A trimmer cannot write an explanation** — it has no way to say what went wrong, only which
words to drop. That is what `MANUAL_NAME` is for, and the correct conclusion is that hand-written
names are the *normal* case for free-form tickets, not an exception for awkward ones. 27 of the
35 rows in this batch are now written from the body:

```
was  [Invoicing] CROATIAERROR: Upload FailedINVOICES:7247-26--26--26-...
now  [Invoicing] Croatia e-invoice upload failed for seven invoices

was  [Payments - Credit Card] Investigate the below issue escalated by the centre team
now  [Payments - Credit Card] Card confirmation email states an amount ten times what was
     actually deducted
```

Writing them also surfaced two faults the trimmed names had hidden, because reading each body to
summarise it is a check the pipeline cannot perform on itself.

### A second master matching on incidental wording

INC0769888 — *"MyRegus team setup mail forwarding screen blocked"* — matched
`[Login] Account showing blocked in My Regus` (MST-71212) and took Login as its category. A
**screen** was blocked, not an account.

The keyword was `blocked in myregus`, which matches the body's "blocked in MyRegus team setup".
Across the 3,716-ticket benchmark that exact string appears **zero** times; the spaced variant
`blocked in my regus` appears twice and both are correctly MST-71212, and `account blocked` and
`account showing blocked` remain. Removed the unspaced variant: it earned nothing and cost this.
Master matching unchanged at 96.4%, and the ticket now reads XC (Product and Services), which is
right — mail forwarding is a service.

That is the second master this week matching on a word that is context rather than symptom, after
`callstream` on the OOMA master. **Both were single loose keywords with no benchmark support.**
The other 44 masters are worth auditing for the same shape.

## Run of 31 Aug 2026 — a master-keyword audit, and three fixes that raised the benchmark

22 tickets. Four rows were wrong on the first pass, all from the same cause as `callstream` and
`blocked in myregus`: **a master keyword naming a noun the ticket merely mentions.**

Wrote `audit_master_keywords.py` to find the shape systematically. For every keyword it counts
benchmark tickets containing it and how many carry that master's own MST tag; a keyword that
fires often while rarely coinciding with its own master is a false-positive generator.

**The first run of the audit was itself misleading**, and the fix matters. Masters with no MST tag
score 0% by construction — the benchmark cannot judge them — and `[SOA] Balance Mismatch`, which
has no tag, dominated the output as if damning. The audit now skips untagged masters, and the
report says plainly that a keyword naming a *symptom* is fine even when untagged rows dominate;
only a tool, a place or a passing noun is the dangerous shape.

Three keywords scoped, each of which had just mis-triaged a live ticket:

| Keyword | Fires on | Own MST | Mis-matched |
|---|---|---|---|
| `wallet` | 34 | 3 (8.8%) | INC0770216, which is about *paying*, not deleting a card |
| `linked account` | rare | — | INC0770177, Nayax charges *posted to* a linked account |
| `balance mismatch` | 87 | untagged master | INC0770045 and INC0770111, both in troubleshooting narrative |

Replaced with the masters' own symptoms (`delete the card from the wallet`, `find linked
account`, `balance mismatch of the account`). **Category 87.1% -> 87.3%**, master matching
unchanged at 96.4%.

### Two long-standing defects fixed, both previously recorded and deferred

**The pipe-hint tie-break.** Flagged on 26 Aug when `Accounts & Access` resolved to Quick Access
on a single shared token. It happened again: `Products & Services` shares one token with
`Bookings (Products) - Short Stay` and one with `XC (Product and Services)`, and precedence order
decided. Now requires **two** shared tokens and refuses to guess when the best score ties —
returning None, which simply means the symptom text decides. Costs nothing measured.

**The body fallback was reading the raw description.** `symptom_body()` exists to strip the
Troubleshooting block and form-field lines, and is documented as the fix for the 17 Aug trap —
but `triage_row` never used it for the description-body fallback, so the trap kept firing through
that path. Now wired in.

Added to it: `after checking|reviewing|verifying|confirming ...` clauses. The template sentence
*"the issue persists after checking the Statement of Account in the Customer Portal for balance
mismatch, incorrect payment status, or missing credit note"* is a list of things **ruled out**,
and it sent two tickets to SOA on wording neither is about.

Scoped deliberately to those four verbs. *"persists after reinstalling TeamHub, logging in
again"* is remediation the reporter performed, and the reviewer graded INC0769431 **Login** on
exactly those words — a broader rule would have broken an owner-confirmed row. All five
owner-confirmed categories were re-checked after each change and all hold.

### Still open

- **`[Retainers] Retainer issues` is too generic to be a name.** Three different faults — a
  top-up issued incorrectly, a missing Request-retainer-return button, and a balance not
  reflecting a transfer — all became children of it and all now read *"Retainer issues"*. Rule 2
  says children share the master's name; the owner's 28 Aug ruling says the name must explain the
  issue. **The master's own name is the problem**, and renaming or splitting it is the fix.
- **INC0770093 and INC0770113 look like the same fault reported twice** — both are cimdata
  Bildungsakademie GmbH with the wrong DID under Call Answering, and the body of the second says
  "a new, separate unresolved issue". Both are children of the OOMA master, so nothing is
  mis-triaged, but they may be one occurrence.

## Run of 1 Sep 2026 — 13 tickets, and a finance-reconciliation family the cluster cannot hold

Eight of thirteen were unclassified on the first pass, nearly all free-form finance
reconciliation. Twelve keywords closed them, every one probed against the benchmark first;
**`marked as paid` was rejected** — 21 tickets split Invoicing 5 / Payments - Credit Card 3 /
SOA 2, no consensus. Category unchanged at 87.3%, so the additions cost nothing.

One cluster credited: INC0770297 (*"remove or zero-out the duplicate payment in MyRegus"*) joins
`[SOA] Duplicate or invalid posting in MyRegus needs reversing`, now **6**.

### Four more tickets the D365-sync cluster should probably hold, and deliberately does not

INC0770021, INC0770319 and INC0770391 are all the same shape as the cluster
`[SOA] Invoices paid in D365 still showing unpaid in MyRegus`, which sits at 7:

```
INC0770021  payment on the MyRegus SOA not reflected in Dynamics Finance
INC0770391  invoice outstanding in Dynamics but already paid in MyRegus
INC0770319  balance mismatch caused by an unposted invoice the hotfix did not cover
```

**Two of the three run in the opposite direction to the cluster's name** — paid in MyRegus and
outstanding in Dynamics, not paid in D365 and unpaid in MyRegus. Adding them would take the count
from 7 to 10 under a name that describes none of them, which is exactly what the cluster's own
note has warned about since 18 Aug: *"the name says 'Invoices paid ... showing unpaid' but most
members are payments and vouchers that never arrived at all — rename or split"*.

**That decision is now blocking.** Three more arrived today, the cluster is three short of the
threshold, and the next batch could push it over under the wrong name. Renaming it to something
like *"[SOA] Payment or invoice state out of sync between MyRegus, Dynamics and Titan"* — or
splitting it by direction — would let today's three be counted honestly. Until then they are
category-tagged SOA and left out of the tally.

The related `[SOA] Balance Mismatch` master still has **no MST tag**, so it cannot claim them
either. Both decisions are the same knot.

### Generic master names, second instance

INC0770268 — *"Wi-Fi not visible for connectivity, everyone in the centre affected"* — is a child
of `[Network devices] Network devices registration/login` and therefore reads as
*"Network devices registration/login"*, which is not what happened. The category is right; the
master's name is not a description of this ticket.

That is the same problem as `[Retainers] Retainer issues` recorded on 31 Aug, and the audit
independently flagged this master's `network device` keyword as firing on 12 benchmark tickets
with **0** carrying its MST tag. **Two masters now need renaming or splitting** before rule 2 can
give their children a name that explains anything.

## Run of 2 Sep 2026 — 23 tickets, and the E-Invoicing case is now 20 tickets in four days

**Seven more tax-authority clearance failures**: France (no source Location Number, on 8,972
invoices), Portugal (recipient TIN incorrect), Poland (KSeF duplicate document), Finland (stuck In
Progress), Malaysia (sent in Pagero, rejected in Titan), Egypt (DR317, quantity exceeds the
referenced document) and Uganda (approved in EFRIS, not reflecting as succeeded).

That is **20 across 28 Aug and 2 Sep**, plus 48+ in the benchmark, all still classified `Invoicing`
as an interim. Two more providers appear today — **Pagero** and **KSeF** alongside Edicom and
EFRIS — which is the clearest sign yet that this is a workstream and not a category: `pagero`
alone is 18 benchmark tickets, none category-tagged. **The `E-Invoicing` category proposed on
28 Aug should be decided.**

### Probing stopped me getting one wrong

INC0770441 — *"community meeting room not updated online"* — classified `Bookings (Products) -
Short Stay` while its pipe hint said `Centre Setup`, and I was about to correct it to
`Center setup`. The benchmark says otherwise: **`community meeting room` appears on 23 tickets,
20 of them tagged Bookings (Products) - Short Stay** and one Center setup. The classifier was
right and the hint was the misleading signal. Left alone.

This is the second time this week the probe reversed my reading rather than confirming it. It is
cheap and it should stay mandatory before any keyword change.

### Six gaps closed

`pagero`, `recipient tin is incorrect` and `duplicate document` to Invoicing; `enquiries routing`
and `routing to new sales` to Enquiry — INC0770666 is a Sales Hub *enquiry routing* fault that
had read as Bookings; `agreement signed but not loaded` to Contract API/Agreements, matching the
INC0770303 ruling from the day before; `beginning balance` and `amount showing in the invoice
copy` to SOA. Category unchanged at 87.3%.

**A non-English ticket.** INC0770493's body is Portuguese — *"não consegue acessar o Team Hub e,
por isso, não consegue enviar a renovação do cliente"*. Only the English pipe title was
classifiable, and `unable to access team hub` has thin support (2 benchmark tickets, 1 tagged
Login). Recorded as uncertain. **Nothing in the pipeline handles non-English bodies**, and this
is the first one seen; if they are common the keyword tables cannot reach them at all.

### Volume worth noticing

**Four more DID / Call Answering tickets** (INC0770521, 523, 528, 551), all children of the OOMA
master. With the three on 31 Aug that is **seven in three days**, every one a wrong DID under Call
Answering Settings needing a manual correction. The master absorbs them so nothing is
mis-triaged and no cluster is warranted — but seven identical manual corrections in three days is
a defect signal the tally will never surface, because children of an existing master are not
counted.

## Run of 3 Sep 2026 — the naming pipeline was poisoning itself three ways

18 tickets, 0 unclassified. One cluster credited: INC0770844 (*"renewal agreement cannot be sent
to client"*) joins `[Renewals] Error when amending an agreement in TeamHub`, now **6**.

The batch exposed three separate defects in how names are produced, all of which had been
quietly degrading output.

### 1. A trailing generic error segment was becoming the name

`Team Hub| Amend agreement| Unable to amend renewal agreement| Error - Something went wrong`
named the ticket *"Error - Something went wrong"*. The symptom is the segment **before** the
error. **15 of the 85 pipe-structured tickets seen so far end this way** — 18%.

`strip_pipe_prefix` now skips a trailing error only when it is **generic** (`something went
wrong`, `no results found`, `please try again`, `an error occurred`). A specific one is kept:
INC0769290's *"Error occurred during renewal processing"* names the failing process and survives.

### 2. `propose_master_name` had its own copy of the pipe logic

It split on `|` and took the last segment itself, so the fix above did not reach it and the name
stayed *"Error - Something went wrong"* after the classifier had already moved on. It now calls
`strip_pipe_prefix`. **Two copies of the same rule is how they drifted apart**, and the same
shape has now appeared twice — `symptom_body` was likewise written and then not wired into the
body fallback.

### 3. The run was reading its own superseded output

Even after both fixes INC0770701 kept the bad title, because `PRIOR` reads every workbook in
`runs/` — including the **earlier passes of the same day**, which are drafts of the run being
produced, not history. A bad name written by pass one was carried back in by pass three, since
PRIOR outranks the drafted name. `prior_names` now skips workbooks whose filename carries the
same date as the output.

This is the third self-poisoning loop found in a week, after triaged names returning through
ServiceNow (28 Aug) and `MANUAL_NAME` being unreachable behind `PRIOR` (26 Aug). **Anything that
reads `runs/` is reading this pipeline's own opinions back.**

### The build assertion earned its place

`assert not bad, "bracket/category mismatch"` caught two hand-written names whose bracket
disagreed with the computed category — mine, written minutes earlier. One was a wording call
(INC0770759 is Bookings, not Memberships, once the generic error stopped masking the symptom).
The other was a real bug:

**`FORM_FIELD_LINE` was stripping the line that held the symptom.** On the CNP card form,
INC0770925's only statement of the fault is *"Type of Request: Credit Card was rejected or not
authorized by the provider"* — and the stripper removed it, leaving the ticket unclassifiable.
`type of request` is now kept; `type of ticket` ("Customer") is still stripped, being a genuine
label. Category 87.3%, unchanged.

### Open

- **INC0770701's title and body disagree.** The title says *"Unable to amend renewal agreement"*;
  the body says Marcia Santos Maciel *"is unable to access Team Hub and, as a result, is unable
  to submit the customer's renewal"*. That is an access failure, not an amendment failure — and
  it is **the same reporter and issue as INC0770493 on 2 Sep**, which was classified Login.
  Filed as Renewals on the title, flagged rather than silently re-read, and the two tickets may
  be one fault.
- **Three more DID / Call Answering tickets** (INC0770690, 843, 847). That is **ten in four
  days**, all children of the OOMA master and so invisible to the tally.

## Training pass against the 314-row scorecard, 3 Sep 2026

`score_against_scorecard.py` re-runs **today's** code over every graded ticket, rather than
reading the scorecard's own `AI ·` columns, which record what the pipeline said on the day and
so measure bugs already fixed. Text is recovered for 198 of 314 rows; the other 116 are reported
as **uncovered, not dropped** — silently skipping them would flatter the score.

| | Before | After |
|---|---|---|
| Category vs reviewer | 171/197 = 86.8% | **187/197 = 94.9%** |
| Routing vs reviewer | 156/168 = 92.9% | 156/168 = 92.9% |
| Category on the 3,716 benchmark | 87.3% | **87.3%** (unchanged) |

### The rule I had been missing

Six of the twenty-six category errors were one confusion: **`Payments - Credit Card` where the
reviewer said `Payments Registration`**. The benchmark states the rule far more clearly than any
single ticket does:

```
add a credit card        Payments Registration  7 : 1  Payments - Credit Card
add card                 Payments Registration 16 : 3
default payment method   Payments Registration 180 : 60
not authorized                                  6    Payments - Credit Card
payment failed                                  5    Payments - Credit Card
```

**Setting up a payment method is `Payments Registration`, whatever the instrument. `Payments -
Credit Card` is a payment that failed.** The reviewer applied it to direct debit too —
INC0770222, *"unable to set the DD as payment default"*, is Payments Registration, not
Payments - Direct Debit — so the DD default wording moved as well.

`Payments - Credit Card` carries the bare keyword `credit card`, which matches any mention
including "cannot add a credit card"; strengthening Payments Registration's side of the
distinction is what fixed it, rather than weakening a keyword the benchmark supports.

**Two of the new keywords cost 14 benchmark rows and were withdrawn.** `unable to add` and
`cannot add` are domain-agnostic — they fire on document uploads and service additions, and
Payments Registration is precedence 10, so it captured them all. Replaced with card-scoped forms
(`unable to add a card`, `cannot add a credit card`), which recovered the full benchmark score
while keeping the scorecard gain. **Both sets have to be measured; the first version of this
change looked like a win on one and a regression on the other.**

### Nine coverage gaps, each named from its own body

`not posted in myregus` (SOA), `not withdrawn automatically` and `auto payment has not been
proceeded` (Payments - Credit Card), `none of the invoices were raised` and `has not sent invoice
email` (Invoicing), `adding their card details` (Payments Registration), `showing active in otr`
and `mac address` (Network devices), `cca self service` (XC), `day office membership` (Bookings
- Short Stay).

### Two reviewer verdicts contradict earlier verbal rulings — NOT resolved here

- **INC0769677.** The owner said on 27 Aug: *"this should go under quick access since this is
  authentication code for WiFi which they get when they have a valid booking active."* The
  scorecard grades it **Bookings (Products)**. The pipeline still returns Quick Access, following
  the spoken ruling.
- **INC0769654.** The owner said *"we will need a new category for this, but leave it as it is
  now"* — Unclassified. The scorecard grades it **Invoicing**, and the keywords added for the
  other Invoicing gaps now classify it that way.

Both are recorded rather than decided. **A spoken ruling and a graded scorecard are both the
owner's word**, and where they disagree the pipeline should not pick silently.

### A limitation of the scorer worth knowing

It calls `triage_row` only, so **clusters and MANUAL_NAME are not applied**. INC0769483 reports
as a Renewals-vs-Bookings miss, but in a real run it takes its cluster's category and is correct.
Some reported misses are therefore artifacts of the harness, not live errors — the scorer
measures the classifier, not the run.

### Routing is at its practical ceiling

The twelve routing misses run in **both directions** — six Portal to Titan, four Titan to Portal —
and are the desk exercising judgement the ticket text does not carry. Encoding either direction
would break the other. `Every routing error measured came from overriding the sheet` still holds.

## Run of 4 Sep 2026 — first run after the training pass

18 tickets, **0 unclassified**. One cluster credited: INC0771021 (*"MyRegus duplicate CN
postings"*) joins `[SOA] Duplicate or invalid posting in MyRegus needs reversing`, now **7**.

**The payments rule learned from the scorecard held on live tickets.** Six payment tickets in
this batch, split the way the reviewer splits them:

```
Payments Registration   cannot enter any card on the portal   card registration fails
                        uploading the autopay
Payments - Credit Card  registered card details disappeared   payment failure notification
                        automatic card payment failed for months
```

`input credit card` had to be added — the rule was right but that wording was not in the table.

**`server error` was added to Login and immediately withdrawn.** 22 benchmark tickets, only 3
tagged Login. It is the same over-broad shape that cost 14 rows during the training pass, caught
this time before it shipped rather than after. Both sets held: benchmark 87.3%, scorecard 94.9%.

The narrowed Login override also proved itself: INC0771149 (*"TITAN ISSUE (SERVER ERROR) ...
trouble accessing the Titan application"*) classifies Login but carries no authentication-failure
term, so the Proton override correctly did **not** fire and the sheet's `L2 - Titan` stood.

### Still open, and now overdue

- **`[Retainers] Retainer issues`** named a fourth ticket *"Retainer issues"* (INC0771057, a
  client unable to enter an IBAN). Flagged since 31 Aug.
- **Two more DID tickets** (INC0771063, INC0771172) — **twelve in five days**, all invisible to
  the tally as children of the OOMA master.
- **E-Invoicing**: Spain joins France, Portugal, Poland, Finland, Malaysia, Egypt, Uganda and
  Croatia. Still filed under Invoicing as an interim.
- The **D365-sync cluster rename** remains blocking at 7 with three uncounted tickets waiting.

## Run of 7 Sep 2026 — an over-correction from the training pass, caught by live tickets

20 tickets, 0 unclassified. `INC0771323` (*"Occupancy went from 7 to 4, but kitchen amenities
remain charging an extra 3"*) joins `[Invoicing] KA backbill cannot be removed (TTN-143719)`,
now **3** — the JIRA names occupancy-step amendments and Kitchen Amenities explicitly, so this is
the tracked defect rather than a new one.

**The export arrived in `runs/` instead of `for triage/`.** It survived only because
`prior_names` wraps its read in try/except and skipped a workbook with no `Finished Triage`
sheet. Moved. Worth knowing that the input and output folders are one typo apart.

### Removing a keyword to satisfy one graded row broke two live ones

The training pass dropped `unable to access team hub` from Login, because the scorecard grades
INC0770493 as **Renewals**. Today two tickets arrived with exactly that title and no renewal
content at all — INC0771216 (*"Team Hub does not work for four active users"*) and INC0771284
(*"cannot access TeamHub and MyRegus"* after cache clearing and re-signing in). Both fell to
Unclassified.

The keyword is restored. INC0770493 is Renewals because its **body** says the user cannot submit
a renewal, not because TeamHub access is a renewals concern — and Renewals is precedence 10
against Login's 30, so a ticket carrying renewal wording still resolves Renewals. INC0770701,
the same reporter and fault, does exactly that.

**INC0770493 itself cannot be reproduced.** Its title alone — `Team Hub| Access| Unable to access
Team Hub` — classifies Login, and the body is never consulted because the title already matched.
Reaching the scorecard's answer would mean either dropping the keyword again, which breaks two
tickets a week later, or reading the body even when the title classifies, which discards the
"symptom first, short description first" rule measured at 83% against 71%.

Taken deliberately: **-1 scorecard row, +2 correct today.** Scorecard 94.9% -> 94.4%, benchmark
unchanged at 87.3%.

The general lesson is worth more than the row: **a single graded ticket is not a rule.** The
training pass was right to encode the payments distinction, which six rows and 250+ benchmark
tickets supported, and wrong to encode this one, which rested on a single row whose evidence sits
somewhere the classifier does not look.

### Still open, unchanged

`[Retainers] Retainer issues` (a fifth ticket would now take that name), the E-Invoicing category,
the D365-sync cluster rename blocking at 7, and **two more DID tickets — fourteen in six days**.

## Run of 8 Sep 2026 — the trailing-error rule generalised, and evidence on the amend-agreement question

12 tickets. Two clusters credited: INC0771490 joins `[Renewals] Error when amending an agreement
in TeamHub` (now **7**) and INC0771499 joins `[Bookings (Products)] Cannot rollback a booking
terminated while provisional` (now **6**).

### The trailing-error rule was list-based and too narrow

3 Sep's fix listed specific generic errors. Three tickets today ended with errors not on that
list — `Error - Blank screen - Screen not loading` (twice) and `Error - There was a problem
updating enquiry` — and were named after them, while the segment before said *"Unable to amend
agreement"*, *"Unable to amend upcoming renewal"* and *"Unable to allocate or reassign a Tour"*.

Replaced with a rule rather than a list: **if the last segment opens with "Error" and the
previous segment STATES A FAULT** (`unable to`, `cannot`, `no …`, `missing`, `incorrect`,
`failed`), take the previous. INC0769290 still keeps its trailing *"Error occurred during renewal
processing"*, because the segment before it is the area label *"Amend an agreement"* — there the
error is the more informative half. Both sets unchanged.

### Direct evidence on the amend-agreement category, open since 18 Aug

INC0771488's title is *"Unable to amend agreement"*, so `unable to amend agreement` was added to
Renewals to match the cluster's bracket. **The benchmark rejected it**: three tickets carry that
wording and they are tagged **XC (Product and Services) 2, Bookings 1 — none Renewals** — and the
benchmark fell 87.3% -> 87.2%. Reverted.

This is the first measurement on a question the cluster note has carried since 18 Aug: *"a
resolved ticket worded 'Not able to amend agreement' is tagged XC (Product and Services), while
the 14 Aug review put TeamHub amend/renew errors under Renewals."* The resolved data now says
**XC** on the only wording that can be tested. The cluster remains bracketed `[Renewals]` and
INC0771488 stays Unclassified rather than being forced either way.

### INC0771488 left Unclassified on purpose

Its title says *"Unable to amend agreement"* but the body describes **TeamHub not loading at all**
— multiple users, blank screens, *"cannot access anything"*, others unable to send agreements.
That is a TeamHub availability incident, not an amendment fault, so it is **not** in the
amend-agreement cluster despite the matching title. Named by hand from the body and flagged: if
it is an outage it deserves a higher impact than the supplied `4 - Low`.

### Owner ruling, 8 Sep: "Unable to amend agreement" is Renewals

Settles the question the amend-agreement cluster note has carried since 18 Aug. The ruling
**overrides the benchmark**, where the three tickets with that wording are tagged
`XC (Product and Services)` 2 and `Bookings` 1 — older labelling the owner is correcting. Cost
taken knowingly: category 87.3% -> 87.2%, scorecard unchanged at 94.4%.

Six forms encoded (`unable to amend agreement`, `not able to amend agreement`, `cannot amend
agreement`, `unable to amend renewal agreement`, `unable to amend upcoming renewal`). The cluster
bracket `[Renewals]` is now supported by a ruling rather than provisional.

INC0771488 becomes Renewals by that rule. It is still **not** in the amend-agreement cluster: its
body describes TeamHub not loading for multiple users, which is an availability incident that
happens to carry an amendment title.

## Owner rulings, 8 Sep 2026 — eleven open questions settled

| # | Question | Ruling |
|---|---|---|
| 1 | D365-sync cluster: rename or split? | **Goes under Titan** — see below, the naming question is still open |
| 2 | `[SOA] Balance Mismatch` MST tag | **Leave the name as is**; no MST tag for now |
| 3 | Renewals cluster at 10 | Category correct, **a JIRA already exists** — the 21 Aug "no JIRA covers this" is superseded |
| 4 | E-Invoicing category | **No new category — they are `[Invoicing]`** |
| 6 | Printer category | **`XC (Product and Services)`** |
| 7 | `[Retainers] Retainer issues` generic name | **Intentional** — all retainer issues share the one name |
| 8 | `[Network devices]` generic name | **Correct**, and no MST tag for now |
| 9 | INC0769677 | **Quick Access** — a long-term office booking must be active to use the WiFi code |
| 10 | INC0769654 | **Invoicing** |
| 12 | Supplied Impact vs body scope | **A single centre out of a few thousand is genuinely low impact** |
| 13 | DID volume | Permanent fix **in progress but on hold** |
| 14 | Non-English tickets | **Rare, and cancelled** — English only is accepted |

### What changed in the pipeline

**E-Invoicing is settled, not interim.** The 28 Aug proposal for a dedicated category is
withdrawn: the ~20 country clearance failures per week are correctly `[Invoicing]`. The
`EI-xxxxx` tags mark a workstream, not a missing category.

**Printer faults are `XC (Product and Services)`**, closing a question open since 17 Aug. The
cluster is renamed from `[UNCATEGORISED] Printer accepts the job but nothing prints` and nine
printer terms added. No cost to either set.

**Two "problems" I raised were not problems.** The generic master names on `[Retainers] Retainer
issues` and `[Network devices] Network devices registration/login` are deliberate — retainer
issues share one name by design. I had read rule 2 as conflicting with the 28 Aug naming ruling;
the owner's answer is that for master children the shared name is the point.

**The Impact question is closed against me.** I flagged three tickets where the body said "all
customers at this centre" while Impact was `4 - Low`. A single centre out of a few thousand is
low impact, so the supplied value was right each time. Note the tension with the older recorded
rule *"a single centre is impact 2, not 1"* — that rule distinguishes 2 from 1, and does not make
a single centre high impact.

### Still open

**The D365-sync cluster naming.** "Goes under Titan" answers ownership, and those tickets already
route to `L2 - Titan` from the sheet, so nothing changed. But the cluster is still called
*"[SOA] Invoices paid in D365 still showing unpaid in MyRegus"* while holding members that run
the opposite way, and ~4 tickets remain uncounted for that reason. It sits at 7.

**Quick Access -> P4 contradicts the scorecard.** The owner said *"most of the issues are
considered P3 ... procedure wasn't followed properly in the past"*, which argues for retiring the
rule. The scorecard says the opposite: **all 9 Quick Access rows are graded P4**, including
INC0767930 and INC0768179 which the reviewer corrected **down** from the AI's P2. Retiring the
rule would break nine graded rows, so it is left in place and the conflict raised rather than
resolved.
