from schemelogic.discovery.categories import CATEGORIES, categories_for


def test_farmer_scheme_matches_farmers():
    assert "farmers" in categories_for("Pradhan Mantri Kisan Samman Nidhi", "Financial support for landholding farmers")


def test_scholarship_scheme_matches_students():
    assert "students" in categories_for("National Scholarship Portal", "Scholarships for meritorious students")


def test_women_scheme_matches_women():
    assert "women" in categories_for("Mukhyamantri Majhi Ladki Bahin Yojana", "Financial assistance for women")


def test_health_scheme_matches_health():
    assert "health" in categories_for("Ayushman Bharat Yojana", "Health cover for secondary and tertiary care")


def test_housing_scheme_matches_housing():
    assert "housing" in categories_for("Pradhan Mantri Awas Yojana", "Housing for all initiative")


def test_scheme_can_match_multiple_categories():
    cats = categories_for("Scheme for women farmers", "Support for women engaged in farming")
    assert "women" in cats
    assert "farmers" in cats


def test_scheme_with_no_keyword_match_returns_empty_set():
    cats = categories_for("Some Totally Unrelated Infrastructure Grant", "Roads and bridges funding")
    assert cats == set()


def test_case_insensitive_matching():
    assert "health" in categories_for("HOSPITAL SUPPORT SCHEME")


def test_all_category_names_are_lowercase_stable_identifiers():
    for cat in CATEGORIES:
        assert cat == cat.lower()


def test_description_none_does_not_crash():
    cats = categories_for("Farmer Support Scheme", None)
    assert "farmers" in cats
