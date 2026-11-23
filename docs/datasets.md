# SSA Disability Datasets — Catalog Documentation

This document describes the dataset catalog served by OpenLens.

For programmatic access, use the `discover_disability_datasets` and `explain_dataset` tools.

---

## How the catalog is grounded

Every dataset's name, description, landing page, download links, data dictionary,
last-modified date, update frequency and temporal coverage come from SSA's own
metadata record on Data.gov. Nothing checkable is typed in by hand.

| File | Role |
|------|------|
| `src/ssa_disability_claims_openlens/data/catalog_sources.json` | Maps each catalog `dataset_id` to its Data.gov slug, or records a manual URL check for resources with no Data.gov record |
| `src/ssa_disability_claims_openlens/data/datagov_snapshot.json` | The Data.gov DCAT records, written by `scripts/sync_catalog.py` — do not edit by hand |
| `src/ssa_disability_claims_openlens/services/dataset_catalog_service.py` | Curated analyst notes only (purpose, use cases, limitations, summary field list) |

To add or change a dataset:

1. Find its record at <https://catalog.data.gov/organization/ssa> and add `dataset_id → slug` to `catalog_sources.json`.
2. Run `python scripts/sync_catalog.py`.
3. Add curated notes in `_CURATED_NOTES`. They must not contradict the record.
4. Run `pytest`. `tests/test_catalog_grounding.py` fails if any URL the server can show is not in the snapshot or a current manual check.
5. If you rate a coverage element `None`, add its Data.gov searches to `data/gap_evidence.json` and run `python scripts/check_gap_claims.py`.

ssa.gov blocks automated link checks, so the Data.gov record is the checkable source
of truth. A weekly workflow (`.github/workflows/sync-catalog.yml`) re-syncs the
snapshot and opens a pull request when SSA changes a record.

---

## Dataset Overview

Frequencies, dates and coverage below are from the Data.gov snapshot synced 2026-11-22.

| ID | Name | Data.gov record | Frequency | Geography | Coverage |
|----|------|-----------------|-----------|-----------|----------|
| `ssa-oasdi-beneficiaries-by-state` | OASDI Beneficiaries by State and County (series) | US-GOV-SSA-3378 | Annual | State/County | 1999–2024 |
| `ssa-ssi-recipients-by-state` | SSI Recipients by State and County (series) | US-GOV-SSA-3414 | Annual (from description) | State/County | 1998–2024 |
| `ssa-di-annual-statistical-report` | Annual Statistical Report on the Social Security Disability Insurance Program | US-GOV-SSA-1667 | Annual | Not stated | 1960–2025 |
| `ssa-disability-claim-data` | SSA Disability Claim Data | US-GOV-SSA-308 | Annual | State | FY2001 on |
| `ssa-state-agency-workload-data` | SSA State Agency Workload Data | US-GOV-SSA-307 | Monthly | State | Oct 2000 on |
| `ssa-hearing-office-workload` | Hearing Office Workload Data - Current Report | US-GOV-SSA-303 | Monthly | Hearing office | Current report |
| `ssa-hearing-wait-time` | Average Wait Time Until Hearing Held Report - Current Report | US-GOV-SSA-304 | Monthly | Hearing offices | Current report |
| `ssa-field-office-locator` | Field Office Contact Information | US-GOV-SSA-1733 | Quarterly | All field offices | Current snapshot |
| `ssa-field-office-visitors` | Field Office Visitors (Average Daily) - FY 2006 On | US-GOV-SSA-434 | Annual | Not stated | FY2006 on |
| `ssa-initial-disability-processing-time` | Combined Title II Disability and Title XVI Blind and Disabled Average Processing Time - FY 2016 On | US-GOV-SSA-1409 | Monthly | Not stated | FY2016 on |
| `ssa-reconsideration-processing-time` | Disability Reconsideration Average Processing Time (Excludes technical denials) - FY2014 On | US-GOV-SSA-1768 | Annual | Not stated | FY2014 on |
| `ssa-alj-disposition-data` | ALJ Disposition Data - Current Report | US-GOV-SSA-299 | Monthly | ALJ / hearing office | Current report |
| `ssa-dds-accuracy` | Disability Determination Services (DDS) Accuracy | US-GOV-SSA-344 | Annual | Not stated | FY2007 on |
| `ssa-ticket-to-work-fy11-17` | Ticket to Work FY11-17 | US-GOV-SSA-1915 | One-time (FOIA) | Not stated | FY2011–2017 |
| `ssa-national-beneficiary-survey` | National Beneficiary Survey: Disability Statistics (series) | US-GOV-SSA-3379 | Irregular | Not stated | 2015, 2019 |
| `ssa-field-office-employee-counts-2016` | 2016 Field Office Employee Counts | US-GOV-SSA-1918 | One-time (FOIA) | Field office | FY2016 |
| `ssa-field-office-visitor-counts-2016` | 2016 Field Office Visitor Counts | US-GOV-SSA-1917 | One-time (FOIA) | Field office | FY2016 |
| `ssa-field-office-appointments-21-days` | Percentage of Field Office Claims Appointments Scheduled Within 21 Days - FY 2005-2015 | US-GOV-SSA-431 | Monthly (discontinued) | Not stated | FY2005–2015 |
| `ssa-field-office-claims-pending` | Field Office Claims Pending | US-GOV-SSA-435 | Annual (from description) | National | FY2006–2022 |
| `ssa-field-office-telephone-service` | Field Office Telephone Service - Monthly National Answer Rate and Busy Rate | US-GOV-SSA-1414 | Monthly | National | FY2013 on |
| `ssa-title2-claim-receipts-by-field-office-2016` | 2016 Title 2 Claim Receipts by Field Office | US-GOV-SSA-1919 | One-time (FOIA) | Field office | FY2016 |
| `ssa-di-ssi-participants-employment-2015` | DI & SSI Program Participants: Characteristics & Employment, 2015 | US-GOV-SSA-2278 | One-time | Not stated | 2015 |
| `ssa-nscf` | National Survey of SSI Children and Families (NSCF) | US-GOV-SSA-328 | One-time survey | Continental U.S. | 2001–2002 |
| `ssa-red-book` | Red Book: A Guide to Work Incentives | none — manual check | — | National | Policy reference |

---

## Dataset Details

### OASDI Beneficiaries by State and County
**Strengths:** State and county tables; long annual series  
**Weaknesses:** Annual only; beneficiaries only — no applications, denials or pending claims  
**Best for:** Geographic distribution of disability beneficiaries

### SSI Recipients by State and County
**Strengths:** State and county tables; recipients, federal payments and federally administered state supplementation  
**Weaknesses:** Annual only; recipients only — no applicants or denials  
**Best for:** SSI program size and payments by geography

### Annual Statistical Report on the SSDI Program
**Strengths:** Program and demographic statistics on disability beneficiaries since 1960  
**Weaknesses:** Report tables, no machine-readable download listed; beneficiaries only  
**Best for:** Demographic profile of SSDI beneficiaries

### SSA Disability Claim Data
**Strengths:** State-level receipts, determinations, eligible population and favorable determination (allowance) rates by fiscal year  
**Weaknesses:** Initial level only; state level only; record last modified 2022  
**Best for:** Comparing initial allowance rates across states

### SSA State Agency Workload Data
**Strengths:** Monthly state-level receipts, pending, decisions and allowances for initial, reconsideration and CDR cases, by SSDI/SSI  
**Weaknesses:** State agency levels only; no processing times  
**Best for:** Monthly state allowance and workload trends

### Hearing Office Workload Data
**Strengths:** Pending, receipts, dispositions and average processing time for each OHO hearing office  
**Weaknesses:** Averages only; no claimant demographics; past months are separate records  
**Best for:** Hearing backlog monitoring by office

### Average Wait Time Until Hearing Held
**Strengths:** Average months from hearing request to hearing held  
**Weaknesses:** Averages only; hearing stage only  
**Best for:** Tracking hearing wait times

### Field Office Contact Information
**Strengths:** Locations, telephone numbers and hours for all field offices; quarterly  
**Weaknesses:** No visit volumes, wait times or staffing per office; no history  
**Best for:** Geographic proximity analysis

### Field Office Visitors (Average Daily)
**Strengths:** Long monthly series of average daily visitors  
**Weaknesses:** Per-office breakdown not described in the record  
**Best for:** Trends in demand for in-person service

### Initial and Reconsideration Processing Times
**Strengths:** Average days from filing to payment or denial for initial claims (monthly, FY2016 on) and reconsiderations (annual, FY2014 on)
**Weaknesses:** Averages only; geographic breakdown not described in the records
**Best for:** How long disability decisions take at each level

### ALJ Disposition Data
**Strengths:** Dispositions, allowances, denials and favorable decisions by ALJ and hearing office
**Weaknesses:** Current report only; hearing offices not mapped to the areas they serve
**Best for:** Hearing-level allowance rates

### DDS Accuracy
**Strengths:** Accuracy of state agency medical determinations since FY2007
**Weaknesses:** SSA's own quality review measure
**Best for:** Quality of initial decisions

### Ticket to Work FY11-17 and National Beneficiary Survey
**Strengths:** Ticket assignments to Employment Networks; survey statistics on beneficiaries' employment interest and activity
**Weaknesses:** Ticket data ends FY2017 and has no outcomes; survey covers 2015 and 2019 only
**Best for:** Work incentive participation context

### FY2016 Field Office Employee and Visitor Counts; Appointments Within 21 Days
**Strengths:** Per-office staffing and visitor counts (FY2016); share of claims appointments scheduled within 21 days (FY2005–2015)
**Weaknesses:** One-time FOIA releases and a discontinued series — no current data
**Best for:** Historical baselines for field office demand, staffing and appointment access

### FY2016 Title II Claim Receipts by Field Office
**Strengths:** Title II disability claims received by each field office; pairs with FY2016 employee counts for a claims-per-staff ratio  
**Weaknesses:** One-time FOIA release; Title II only (no SSI); receipts only — no pending counts or decision times  
**Best for:** Historical baseline for disability claim volume by office

### Field Office Claims Pending and Telephone Service
**Strengths:** Yearly field office claims pending, FY2006–2022; monthly phone answer and busy rates, FY2013 on  
**Weaknesses:** National totals only; claims pending combines all claim types and ends in FY2022; phone data excludes abandoned and overflow calls  
**Best for:** National trends in field office backlog and phone access

### DI & SSI Participants: Characteristics & Employment (2015) and NSCF (2001–2002)
**Strengths:** Work activity before and after award; household socioeconomic status of SSI child applicants and recipients  
**Weaknesses:** One-time publications; NSCF covers children only  
**Best for:** Indirect evidence on return to work and on applicants' economic circumstances

### Red Book
**Strengths:** SSA's guide to work incentive rules  
**Weaknesses:** Policy reference only; no statistics  
**Best for:** Work incentive rules for return-to-work questions

---

## Known Cross-Dataset Gaps

Every gap listed as "no data" is backed by recorded Data.gov searches in
`src/ssa_disability_claims_openlens/data/gap_evidence.json`. `scripts/check_gap_claims.py`
re-runs them and fails when a new result needs review (weekly in CI).

1. **No race/ethnicity** — No SSA dataset on Data.gov reports applications, decisions or beneficiaries by race or ethnicity
2. **No denial reasons** — No SSA dataset reports why claims are denied (medical vs. technical)
3. **Applicant income only historical** — The only source is a 2001–2002 survey of SSI children and families (US-GOV-SSA-328); no adult or current data
4. **No travel distance, service areas or office accessibility data** — None of these are described by any SSA dataset; the only related record is national interpreter call counts
5. **No individual-level linkage** — Initial, reconsideration and hearing data cannot be linked for the same claimant, so end-to-end waits cannot be computed
6. **Field office operations only historical** — Per-office staffing, visitor and Title II claim receipt counts exist only for FY2016; appointment timeliness only for FY2005–2015; current claims pending and phone service data are national only
7. **No sub-state outcome data** — State agency allowance data stops at state level; hearing offices are not mapped to the areas they serve
8. **Averages only** — Processing-time datasets publish averages, not distributions
