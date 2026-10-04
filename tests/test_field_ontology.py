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


def test_every_field_a_gold_scheme_reads_is_live_and_lists_that_scheme():
    """A retired field (schemes=()) carries a placeholder citizen_question -- until 2026-10-04 the
    IGNOAPS chat asked citizens "(Retired field — not asked directly; kept only for internal
    traceability.)" -- and is hidden from extraction. A gold scheme may only read live fields."""
    import json
    from pathlib import Path

    from schemelogic.schema.field_ontology import get_field
    from schemelogic.schema.models import Scheme

    for path in sorted((Path(__file__).resolve().parents[1] / "data" / "gold").glob("*.json")):
        scheme = Scheme.model_validate(json.loads(path.read_text(encoding="utf-8")))
        fields: set[str] = set()

        def walk(node):
            children = getattr(node, "and_", None) or getattr(node, "or_", None)
            if children is not None:
                for child in children:
                    walk(child)
            else:
                fields.add(node.field)

        walk(scheme.inclusion)
        for e in scheme.exclusions:
            fields.add(e.field)
            if e.except_ is not None:
                fields.add(e.except_.field)
        for field in fields:
            spec = get_field(field)
            assert spec is not None, (scheme.scheme_id, field)
            assert scheme.scheme_id in spec.schemes, (scheme.scheme_id, field, spec.schemes)
            assert "Retired field" not in spec.citizen_question, (scheme.scheme_id, field)
