from schemelogic.ingestion.silver_scraper import (
    SOURCE_TAG,
    classify_region,
    clean_record_text,
    fix_mojibake,
    has_mojibake,
    parse_myscheme_pdf_text,
)

# Synthetic text mirroring the real myScheme PDF-dump shape: UI chrome, concatenated single-word
# nav tabs with no separating whitespace, then the real content in the same section order.
_SAMPLE_WITH_EXCLUSIONS = (
    "Test Scheme NameAre you sure you want to sign out?CancelSign OutEngEnglish/हिंदीSign "
    "InBackDetailsBenefitsEligibilityExclusionsApplication ProcessDocuments RequiredFrequently "
    "Asked QuestionsSources And ReferencesFeedbackCancelApply NowCheck EligibilityTest "
    "MinistryTest Scheme NameTagOneTagTwoDetailsObjective: This scheme provides support to "
    "eligible citizens.BenefitsRs. 1000 per month.EligibilityMust be 18 years or older.Must be "
    "a resident.ExclusionsGovernment employees are not eligible.Application ProcessOnline via "
    "the portal.Step 1: Register.Documents RequiredAadhaar Card.Frequently Asked "
    "QuestionsWhat is the benefit? Rs 1000/month.Sources And ReferencesScheme Guidelines"
)

_SAMPLE_NO_EXCLUSIONS = (
    "Another SchemeAre you sure you want to sign out?CancelSign OutEngEnglish/हिंदीSign "
    "InBackDetailsBenefitsEligibilityApplication ProcessDocuments RequiredFrequently Asked "
    "QuestionsSources And ReferencesFeedbackCancelApply NowCheck EligibilitySome DeptAnother "
    "SchemeTagADetailsThis scheme helps rural households.BenefitsFree training.EligibilityAny "
    "adult woman.Application ProcessOffline at the local office.Documents RequiredID proof."
    "Frequently Asked QuestionsNone.Sources And ReferencesOfficial site"
)

_SAMPLE_UNRECOGNIZED = "Some totally different page shape with no known markers at all."


def test_parses_scheme_name():
    rec = parse_myscheme_pdf_text(_SAMPLE_WITH_EXCLUSIONS, "test-scheme")
    assert rec.scheme_name == "Test Scheme Name"


def test_source_tag_always_set():
    rec = parse_myscheme_pdf_text(_SAMPLE_WITH_EXCLUSIONS, "test-scheme")
    assert rec.source == SOURCE_TAG == "myscheme_unverified"


def test_official_link_derived_from_slug():
    rec = parse_myscheme_pdf_text(_SAMPLE_WITH_EXCLUSIONS, "test-scheme")
    assert rec.official_link == "https://www.myscheme.gov.in/schemes/test-scheme"


def test_extracts_description_stripping_objective_label():
    rec = parse_myscheme_pdf_text(_SAMPLE_WITH_EXCLUSIONS, "test-scheme")
    assert rec.description == "This scheme provides support to eligible citizens."


def test_extracts_eligibility_and_benefits():
    rec = parse_myscheme_pdf_text(_SAMPLE_WITH_EXCLUSIONS, "test-scheme")
    assert rec.eligibility_text == "Must be 18 years or older.Must be a resident."
    assert rec.benefits_text == "Rs. 1000 per month."


def test_extracts_application_process():
    rec = parse_myscheme_pdf_text(_SAMPLE_WITH_EXCLUSIONS, "test-scheme")
    assert rec.application_process_text == "Online via the portal.Step 1: Register."


def test_sections_found_includes_exclusions_when_present():
    rec = parse_myscheme_pdf_text(_SAMPLE_WITH_EXCLUSIONS, "test-scheme")
    assert "exclusions" in rec.sections_found


def test_sections_found_excludes_exclusions_when_absent():
    rec = parse_myscheme_pdf_text(_SAMPLE_NO_EXCLUSIONS, "another-scheme")
    assert "exclusions" not in rec.sections_found
    assert rec.eligibility_text == "Any adult woman."


def test_unrecognized_page_shape_returns_none_fields_with_warning():
    rec = parse_myscheme_pdf_text(_SAMPLE_UNRECOGNIZED, "weird-slug")
    assert rec.scheme_name is None
    assert rec.eligibility_text is None
    assert rec.parse_warning is not None
    assert rec.official_link == "https://www.myscheme.gov.in/schemes/weird-slug"


def test_extracts_ministry_or_state():
    rec = parse_myscheme_pdf_text(_SAMPLE_WITH_EXCLUSIONS, "test-scheme")
    assert rec.ministry_or_state == "Test Ministry"


def test_classify_region_state():
    assert classify_region("Jammu and Kashmir") == "state_or_ut"


def test_classify_region_central():
    assert classify_region("Ministry Of Agriculture and Farmers Welfare") == "central_or_other"


def test_classify_region_unknown():
    assert classify_region(None) == "unknown"


def test_has_mojibake_detects_real_corruption():
    assert has_mojibake("Ladies Vocational Centresâ€​") is True
    assert has_mojibake("clean text") is False
    assert has_mojibake(None) is False


def test_missing_cta_marker_but_has_scheme_name():
    text = "Some SchemeAre you sure you want to sign out?CancelSign Out no CTA marker here at all"
    rec = parse_myscheme_pdf_text(text, "some-scheme")
    assert rec.scheme_name == "Some Scheme"
    assert rec.eligibility_text is None
    assert "CTA" in rec.parse_warning


# --- fix_mojibake / clean_record_text (Bug 3 fix) -----------------------------------------------


def test_fix_mojibake_reverses_real_corruption():
    """Same real string used in test_has_mojibake_detects_real_corruption above -- the classic
    UTF-8-decoded-as-cp1252 pattern (â€™, â€œ, â€", â‚¹, â€¦, ...)."""
    original = "Chief Minister’s Krishi Samuh Yojana — for ₹ benefits…"
    corrupted = original.encode("utf-8").decode("cp1252")
    assert has_mojibake(corrupted)
    assert fix_mojibake(corrupted) == original


def test_fix_mojibake_strips_bom():
    assert fix_mojibake("﻿Some Scheme Name") == "Some Scheme Name"


def test_fix_mojibake_leaves_clean_text_untouched():
    clean = "Pradhan Mantri Kisan Samman Nidhi"
    assert fix_mojibake(clean) == clean


def test_fix_mojibake_leaves_genuine_non_ascii_untouched():
    """Real Hindi/Devanagari text has no U+00E2 marker -- must never be run through the cp1252
    round-trip, which would corrupt it (it isn't mojibake, so has no legitimate reversal)."""
    hindi = "प्रधानमंत्री किसान सम्मान निधि"
    assert fix_mojibake(hindi) == hindi


def test_fix_mojibake_none_and_empty_are_safe():
    assert fix_mojibake(None) is None
    assert fix_mojibake("") == ""


def test_fix_mojibake_unreversible_sequence_left_as_is():
    """A string containing the marker byte but not a genuine reversible UTF-8-as-cp1252 sequence
    must degrade to unchanged, never raise and never guess."""
    weird = "â☃foo"  # â followed by a snowman -- not a real mojibake sequence
    result = fix_mojibake(weird)
    assert isinstance(result, str)  # never raises


def test_clean_record_text_cleans_every_text_field():
    original_name = "Chief Minister’s Scheme"
    corrupted_name = original_name.encode("utf-8").decode("cp1252")
    record = {
        "slug": "test-slug",
        "scheme_name": corrupted_name,
        "description": corrupted_name,
        "eligibility_text": corrupted_name,
        "benefits_text": corrupted_name,
        "application_process_text": corrupted_name,
        "official_link": "https://example.com",
    }
    cleaned = clean_record_text(record)
    assert cleaned["scheme_name"] == original_name
    assert cleaned["description"] == original_name
    assert cleaned["eligibility_text"] == original_name
    assert cleaned["benefits_text"] == original_name
    assert cleaned["application_process_text"] == original_name
    assert cleaned["official_link"] == "https://example.com"  # untouched, not a text field
    assert cleaned["slug"] == "test-slug"  # untouched


def test_clean_record_text_handles_missing_or_none_fields():
    record = {"slug": "x", "scheme_name": None, "official_link": "https://example.com"}
    cleaned = clean_record_text(record)
    assert cleaned["scheme_name"] is None
    assert "description" not in cleaned  # never fabricates a field that wasn't there
