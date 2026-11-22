"""
Tests for the rating rubric, the critical-element cap, question normalisation,
scope detection, report transparency, and uncatalogued-dataset leads.
"""

from __future__ import annotations

import re
import unittest.mock as mock

import pytest

from src.ssa_disability_claims_openlens.models import CoverageRating, InformationElement
from src.ssa_disability_claims_openlens.services import answer_coverage_service as acs
from src.ssa_disability_claims_openlens.services.dataset_catalog_service import (
    DataGovAdapter,
    DatasetCatalogService,
    StaticCatalogAdapter,
    _lead_terms,
    _title_stem,
)

ENGINE = acs.AnswerCoverageEngine()


# ── Rubric rules ──────────────────────────────────────────────────────────────


class TestRubric:
    @pytest.mark.parametrize("entry", acs._COVERAGE_KB, ids=[e.element for e in acs._COVERAGE_KB])
    def test_rating_is_consistent_with_datasets(self, entry: acs._CoverageEntry) -> None:
        assert entry.coverage_quality in ("Full", "Partial", "Proxy", "None")
        if entry.coverage_quality == "None":
            assert not entry.dataset_ids, "A 'None' element cannot cite datasets"
        else:
            assert entry.dataset_ids, f"A '{entry.coverage_quality}' element must cite datasets"

    @pytest.mark.parametrize("entry", acs._COVERAGE_KB, ids=[e.element for e in acs._COVERAGE_KB])
    def test_rationale_cites_a_source(self, entry: acs._CoverageEntry) -> None:
        assert entry.rationale.strip(), "Every element needs a rationale"
        assert re.search(r"US-GOV-SSA-\d+|search evidence", entry.rationale), (
            "The rationale must cite a Data.gov record id or the recorded search evidence"
        )

    def test_element_names_are_unique(self) -> None:
        names = [e.element for e in acs._COVERAGE_KB]
        assert len(names) == len(set(names))


class TestCriticalCap:
    @staticmethod
    def _el(quality: str) -> InformationElement:
        return InformationElement(element=quality, description="", available=quality != "None",
                                  coverage_quality=quality)

    def test_proxy_critical_caps_at_limited(self) -> None:
        elements = [self._el("Proxy"), self._el("Full"), self._el("Full")]
        score, note = acs._apply_critical_cap(70.0, elements, [2, 1, 1])
        assert score == 39.0 and "Limited" in note

    def test_partial_critical_caps_at_partial(self) -> None:
        score, note = acs._apply_critical_cap(90.0, [self._el("Partial"), self._el("Full")], [2, 1])
        assert score == 74.0 and "Partial" in note

    def test_full_critical_is_not_capped(self) -> None:
        assert acs._apply_critical_cap(90.0, [self._el("Full")], [2]) == (90.0, "")

    def test_supporting_only_is_not_capped(self) -> None:
        assert acs._apply_critical_cap(100.0, [self._el("Full")], [1]) == (100.0, "")

    def test_cap_note_appears_in_report(self) -> None:
        a = ENGINE.evaluate("How long are appointment wait times at SSA field offices?")
        assert a.coverage_rating == CoverageRating.LIMITED
        assert "Rating capped at Limited" in a.format_report()


# ── Matching robustness ───────────────────────────────────────────────────────


def _elements(question: str) -> set[str]:
    return {e.element for e in ENGINE.evaluate(question).required_information_elements}


class TestMatching:
    @pytest.mark.parametrize(
        ("question", "element"),
        [
            ("Which counties have the most disability beneficiaries?", "Geographic disaggregation of outcomes"),
            ("How many applicants are approved in each state?", "Disability program allowance rates"),
            ("What share of claims are ultimately approved after all appeals?",
             "Linked claim history across decision levels"),
            ("Why are disability claims denied?", "Reasons for claim denials"),
            ("Are SSI payments adequate for basic needs?",
             "Income and economic status of applicants and recipients"),
            ("How many beneficiaries go back to work?", "Return-to-work outcomes"),
            ("Are field offices sparse relative to the disability population?",
             "Geographic distribution of disability service access"),
        ],
    )
    def test_paraphrases_reach_the_core_element(self, question: str, element: str) -> None:
        assert element in _elements(question)

    def test_appointment_waits_do_not_match_claim_processing(self) -> None:
        elements = _elements("How long are appointment wait times at SSA field offices?")
        assert "Field office appointment wait times" in elements
        assert "Disability claim processing times" not in elements

    def test_plural_and_singular_match_the_same_elements(self) -> None:
        assert _elements("Which county has the most beneficiaries?") == _elements(
            "Which counties have the most beneficiaries?"
        )

    def test_singularisation_keeps_program_names(self) -> None:
        _, singular = acs.normalise_question("SSI status and access across offices")
        assert singular == "ssi status and access across office"


class TestScope:
    @pytest.mark.parametrize(
        ("question", "scope"),
        [
            ("Are there racial disparities in allowance rates by state?", "State level"),
            ("Which counties have the most beneficiaries?", "County level"),
            ("Which hearing offices have the longest waits?", "Hearing office level"),
            ("Which field offices have the highest workload?", "Field office level"),
        ],
    )
    def test_scope_comes_from_the_question(self, question: str, scope: str) -> None:
        a = ENGINE.evaluate(question)
        assert a.intent is not None and scope in a.intent.scope

    def test_questions_without_an_intent_category_get_a_general_intent(self) -> None:
        a = ENGINE.evaluate("Do allowance rates vary by state?")
        assert a.intent is not None
        assert a.intent.intent_category == "General"
        assert a.intent.scope == "State level"


# ── Report transparency ───────────────────────────────────────────────────────


class TestReportTransparency:
    def test_report_explains_every_rating(self) -> None:
        a = ENGINE.evaluate("Are there racial disparities in SSA disability allowance rates by state?")
        report = a.format_report()
        assert "## How Each Element Was Rated" in report
        for el in a.required_information_elements:
            assert el.rationale and el.rationale.replace("|", "/") in report

    def test_report_states_its_basis(self) -> None:
        report = ENGINE.evaluate("Do allowance rates vary by state?").format_report()
        assert "Dataset contents were not downloaded or inspected" in report


# ── Uncatalogued-dataset leads ────────────────────────────────────────────────


def _summary(slug: str, title: str, ident: str) -> dict:
    return {
        "slug": slug,
        "dcat": {
            "title": title,
            "identifier": ident,
            "description": "d",
            "landingPage": {"accessURL": f"https://www.ssa.gov/data/{slug}.html"},
        },
    }


class TestLeads:
    def test_lead_terms_drop_generic_words(self) -> None:
        terms = _lead_terms("Are there racial disparities in SSA disability allowance rates by state?")
        assert terms == ["racial", "disparity", "allowance"]

    def test_title_stem_groups_editions(self) -> None:
        assert _title_stem("Hearing Office Workload Data - August 2025") == _title_stem(
            "Hearing Office Workload Data - Current Report"
        )

    def test_leads_exclude_catalogued_editions_and_are_capped(self) -> None:
        response = {"results": [
            _summary("hearing-office-workload-data-august-2025", "Hearing Office Workload Data - August 2025", "US-GOV-SSA-3348"),
            _summary("fast-track", "Percentage of Fast-Track Receipts - FY 2010 On", "US-GOV-SSA-327"),
            _summary("dds-accuracy-x", "Pre-Effectuation Review of Disability Determinations - FY 2016", "US-GOV-SSA-1"),
            _summary("a", "Alpha Dataset", "US-GOV-SSA-2"),
            _summary("b", "Beta Dataset", "US-GOV-SSA-3"),
        ]}
        adapter = DataGovAdapter("https://catalog.data.gov/api/v1")
        service = DatasetCatalogService(static_adapter=StaticCatalogAdapter(), live_adapters=[adapter])
        client = mock.MagicMock()
        client.__enter__.return_value.get.return_value.json.return_value = response
        with mock.patch("httpx.Client", return_value=client):
            leads, note = service.find_uncatalogued_leads("Do allowance rates vary by state?")
        titles = [lead["title"] for lead in leads]
        assert "Hearing Office Workload Data - August 2025" not in titles
        assert len(leads) == 3
        assert leads[0]["identifier"] == "US-GOV-SSA-327"
        assert leads[0]["url"] == "https://catalog.data.gov/dataset/fast-track"
        assert "allowance" in note

    def test_unavailable_live_search_is_reported(self) -> None:
        adapter = DataGovAdapter("https://catalog.data.gov/api/v1")
        service = DatasetCatalogService(static_adapter=StaticCatalogAdapter(), live_adapters=[adapter])
        client = mock.MagicMock()
        client.__enter__.return_value.get.side_effect = Exception("timeout")
        with mock.patch("httpx.Client", return_value=client):
            leads, note = service.find_uncatalogued_leads("Do allowance rates vary by state?")
        assert leads == [] and "unavailable" in note

    def test_report_has_no_unassessed_leads_section(self) -> None:
        report = ENGINE.evaluate("Do allowance rates vary by state?").format_report()
        assert "Not Yet Assessed" not in report
        assert "Live Data.gov search terms" not in report


# ── Office-level decision times ───────────────────────────────────────────────

FIELD_OFFICE_DECISION_Q = "Which field offices have the longest decision wait times?"
OFFICE_DECISION_ELEMENT = "Disability decision times by field office or DDS"


class TestOfficeDecisionTimes:
    def test_question_is_limited_not_partial(self) -> None:
        a = ENGINE.evaluate(FIELD_OFFICE_DECISION_Q)
        assert a.coverage_rating == CoverageRating.LIMITED
        assert OFFICE_DECISION_ELEMENT in {e.element for e in a.required_information_elements}

    def test_intent_and_premise_note(self) -> None:
        a = ENGINE.evaluate(FIELD_OFFICE_DECISION_Q)
        assert a.intent is not None
        assert a.intent.intent_category == "Performance"
        assert "Disability Determination Services" in a.intent.premise_note
        assert "**Note on the question**" in a.format_report()

    def test_national_averages_become_supporting(self) -> None:
        entries = [
            (next(e for e in acs._COVERAGE_KB if e.element == name), 2)
            for name in ("Disability claim processing times", OFFICE_DECISION_ELEMENT)
        ]
        weights = {e.element: w for e, w in acs.AnswerCoverageEngine._apply_refinements(entries)}
        assert weights == {"Disability claim processing times": 1, OFFICE_DECISION_ELEMENT: 2}

    @pytest.mark.parametrize(
        "question",
        [
            "How long are appointment wait times at SSA field offices?",
            "Are walk-in wait times longer at rural field offices?",
            "Which hearing offices have the longest waits?",
            "Which field offices have the highest workload?",
        ],
    )
    def test_service_waits_and_hearing_offices_do_not_match(self, question: str) -> None:
        assert OFFICE_DECISION_ELEMENT not in _elements(question)

    def test_dds_questions_match(self) -> None:
        assert OFFICE_DECISION_ELEMENT in _elements(
            "How long do DDS offices take to decide claims in each state?"
        )


class TestMissingInformationAndImpact:
    def test_critical_proxy_elements_are_listed_as_missing(self) -> None:
        a = ENGINE.evaluate(FIELD_OFFICE_DECISION_Q)
        assert any(m.startswith(OFFICE_DECISION_ELEMENT) for m in a.missing_information)
        assert "## Missing Information\n\n- " in a.format_report()

    def test_impact_does_not_overstate_proxy_coverage(self) -> None:
        a = ENGINE.evaluate(FIELD_OFFICE_DECISION_Q)
        assert "substantially addressed" not in a.gap_analysis.impact_on_answer
        assert OFFICE_DECISION_ELEMENT in a.gap_analysis.impact_on_answer

    def test_supporting_proxy_elements_keep_the_standard_impact(self) -> None:
        el = InformationElement(element="X", description="", available=True, coverage_quality="Proxy")
        gap = ENGINE._build_gap_analysis([el], [1])
        assert "substantially addressed" in gap.impact_on_answer
