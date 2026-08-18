from schemelogic.schema import field_ontology
from schemelogic.schema.models import PredicateCategory, SimplePredicate


def test_all_fields_have_unique_names():
    names = [f.name for f in field_ontology._FIELDS]
    assert len(names) == len(set(names))


def test_get_field_known_and_unknown():
    assert field_ontology.get_field("is_indian_citizen") is not None
    assert field_ontology.get_field("not_a_real_field") is None


def test_fields_by_category_matches_all_categories():
    for cat in PredicateCategory:
        for f in field_ontology.fields_by_category(cat):
            assert f.cat == cat


def test_all_field_names_matches_ontology_dict():
    assert set(field_ontology.all_field_names()) == set(field_ontology.FIELD_ONTOLOGY.keys())


def test_format_for_prompt_contains_every_live_field_name():
    """Retired fields (empty `schemes` tuple) are deliberately excluded from the prompt -- pure
    token waste, the LLM has no use for a field it should never propose. See format_for_prompt's
    docstring. Checks each retired field's own bullet-list entry is absent, not bare substring
    absence of its name -- a retired field's name may legitimately still appear in passing inside
    another (live, included) field's docstring, e.g. explaining what it was renamed to."""
    text = field_ontology.format_for_prompt()
    for f in field_ontology._FIELDS:
        if f.schemes:
            assert f.name in text
        else:
            assert f"- {f.name} (" not in text


def test_value_type_is_one_of_known_types():
    for f in field_ontology._FIELDS:
        assert f.value_type in ("boolean", "number", "string", "date")


def test_ontology_proposed_defaults_false_and_is_settable():
    p = SimplePredicate.model_validate({"field": "x", "op": "==", "value": True})
    assert p.ontology_proposed is False
    p2 = SimplePredicate.model_validate(
        {"field": "brand_new_field", "op": "==", "value": True, "ontology_proposed": True}
    )
    assert p2.ontology_proposed is True
