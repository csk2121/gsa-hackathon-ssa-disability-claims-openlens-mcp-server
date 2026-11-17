# SSA Disability Datasets — Catalog Documentation

This document describes the curated SSA disability dataset catalog maintained by OpenLens.

For programmatic access, use the `discover_disability_datasets` and `explain_dataset` tools.

---

## Dataset Overview

| ID | Name | Source | Frequency | Geographic | Temporal |
|----|------|--------|-----------|------------|----------|
| `ssa-oasdi-beneficiaries-by-state` | OASDI Beneficiaries by State and County | SSA Open Data | Annual | State/County | 1990–2023 |
| `ssa-odar-pending-cases` | ODAR Pending Cases by Hearing Office | SSA Open Data | Monthly | Hearing Office | 2007–present |
| `ssa-disability-applications-decisions` | SSI/SSDI Applications and Decisions | SSA Open Data | Annual | National | 1960–2023 |
| `ssa-field-office-locator` | SSA Field Office Locations | SSA Open Data | Quarterly | All Offices | Current only |
| `ssa-disability-research-statistics` | SSA Disability Research Statistics | SSA Open Data | Annual | State | 1970–2023 |
| `ssa-ssi-recipients-by-state` | SSI Recipients by State and County | SSA Open Data | Monthly | State/County | 2008–present |
| `ssa-red-book` | SSA Red Book — Work Incentives | SSA Open Data | Annual | National | 1960–present |
| `data-gov-ssa-performance` | SSA Annual Performance Report | Data.gov | Annual | National | 2003–2023 |

---

## Dataset Details

### OASDI Beneficiaries by State and County
**Strengths:** Strong geographic foundation; county-level data; long time series  
**Weaknesses:** Annual only; no demographic cross-tabs below state level; no denied applicants  
**Best for:** Geographic distribution of disability beneficiaries; state/county equity analysis

### ODAR Pending Cases by Hearing Office
**Strengths:** Monthly frequency; covers all hearing offices; long time series from 2007  
**Weaknesses:** Average processing times only (no distribution); no demographics; no impairment type  
**Best for:** Hearing backlog monitoring; regional processing time comparisons

### SSI/SSDI Applications and Decisions
**Strengths:** Covers applications, awards, denials, and allowance rates by program and impairment  
**Weaknesses:** National only; no race/ethnicity; annual frequency; reconsideration data separate  
**Best for:** National program access trends; impairment category analysis

### SSA Field Office Locations
**Strengths:** Complete directory with geocoordinates for all offices  
**Weaknesses:** No appointment wait times; no staffing data; current snapshot only (no history)  
**Best for:** Geographic proximity analysis; service desert identification

### SSA Disability Research Statistics
**Strengths:** Age and sex breakdown; state-level; long time series  
**Weaknesses:** No race/ethnicity; binary sex categories only; no impairment cross-tab  
**Best for:** SSDI beneficiary demographic analysis; benefit amount comparisons

### SSI Recipients by State and County
**Strengths:** Monthly frequency; state and county level; covers all U.S. jurisdictions  
**Weaknesses:** No demographics below state level; excludes state supplements  
**Best for:** SSI program monitoring; county-level recipient concentration

### SSA Red Book
**Strengths:** Authoritative source for SGA thresholds and work incentive rules  
**Weaknesses:** Policy reference only; no statistics; cannot join to individual records  
**Best for:** Work incentive research; SGA threshold trend analysis

### SSA Annual Performance Report
**Strengths:** Official agency performance metrics; multi-year trend data  
**Weaknesses:** National only; self-reported; metric definitions change  
**Best for:** Processing time trend analysis; performance target vs. actual comparison

---

## Known Cross-Dataset Gaps

1. **No individual-level linkage** — Cannot link a claimant across initial claim, reconsideration, and hearing datasets
2. **No race/ethnicity anywhere** — Race and ethnicity data is absent from all published datasets
3. **No income or asset data** — SSI is means-tested but no income/asset data is published
4. **No wait time operational data** — Appointment wait times and walk-in service times are not collected publicly
5. **No staffing data** — Field office and hearing office staffing levels are not published
