"""Gold-set sourcing audit tooling. Offline, read-only: no LLM calls, never edits gold.

The audit itself is a human judgement -- for each predicate, is the rule stated in the cited
source, a documented inference, or unsourced? -- so this script doesn't classify anything. It
produces the raw material that judgement needs, reproducibly:

    PYTHONPATH=. python scripts/audit_gold.py extract              # PDF text -> data/cache/source_text/
    PYTHONPATH=. python scripts/audit_gold.py table                # every predicate, all schemes (markdown)
    PYTHONPATH=. python scripts/audit_gold.py show PM-KISAN        # one scheme: predicates, source_clause, .md
    PYTHONPATH=. python scripts/audit_gold.py search "five acres" [IGNOAPS]   # term, in .md + PDF text
    PYTHONPATH=. python scripts/audit_gold.py sync                 # data/gold/*.json vs tests' copies
    PYTHONPATH=. python scripts/audit_gold.py format [--check]     # rewrite gold in canonical form

The source PDFs live in data/raw_documents/, which is gitignored (large, third-party). `search`
works on whatever has been extracted locally and says so when a scheme's PDFs aren't present,
rather than silently reporting "not found". The .md files a scheme's extraction actually reads are
the same directory -- the audit checks both layers, because a rule present in a primary PDF but
absent from the .md makes an extractor "miss" not the extractor's fault.

Used for docs/GOLD_AUDIT_2026-10-03.md.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

GOLD_DIR = ROOT / "data" / "gold"
RAW_DIR = ROOT / "data" / "raw_documents"
TEXT_DIR = ROOT / "data" / "cache" / "source_text"


def scheme_ids() -> list[str]:
    return sorted(p.stem for p in GOLD_DIR.glob("*.json"))


def load_gold(sid: str) -> dict:
    """The gold scheme as a FULLY EXPLICIT dict. Gold files are stored in canonical form, which omits
    every field at its default (models.dump_gold_json) -- an empty exclusions list, a false
    flagged_for_review, a "self" quantifier -- so reading the raw JSON would KeyError on them. Going
    through the model restores every field."""
    from schemelogic.schema.models import Scheme

    raw = json.loads((GOLD_DIR / f"{sid}.json").read_text(encoding="utf-8"))
    return Scheme.model_validate(raw).model_dump(mode="json", by_alias=True)


def _leaves(node: dict, path: str):
    for key in ("and", "or"):
        if key in node:
            for i, child in enumerate(node[key]):
                yield from _leaves(child, f"{path}.{key}[{i}]")
            return
    yield path, node


def predicates(gold: dict) -> list[dict]:
    """Every predicate in a gold scheme, in a stable order, with its location."""
    out: list[dict] = []
    for path, p in _leaves(gold["inclusion"], "incl"):
        out.append({"loc": path, "field": p["field"], "op": p["op"], "value": p["value"], "kind": "inclusion"})
    # canonical gold (models.dump_gold_json) omits an empty exclusions list
    for i, e in enumerate(gold.get("exclusions", [])):
        out.append({"loc": f"excl[{i}]", "field": e["field"], "op": e["op"], "value": e["value"],
                    "kind": f"exclusion ({e.get('quantifier', 'self')})"})
        if e.get("except"):
            x = e["except"]
            scope = e.get("except_scope", "member")
            out.append({"loc": f"excl[{i}].except", "field": x["field"], "op": x["op"], "value": x["value"],
                        "kind": f"exception (scope: {scope})"})
    return out


def cmd_table() -> None:
    total = 0
    for sid in scheme_ids():
        preds = predicates(load_gold(sid))
        total += len(preds)
        print(f"\n### {sid} ({len(preds)} predicates)\n")
        print("| # | Location | Predicate | Kind | Class | Note |")
        print("|---|---|---|---|---|---|")
        for n, p in enumerate(preds, start=1):
            print(f"| P{n:02} | `{p['loc']}` | `{p['field']} {p['op']} {json.dumps(p['value'])}` "
                  f"| {p['kind']} |  |  |")
    print(f"\n{total} predicates across {len(scheme_ids())} schemes")


def cmd_show(sid: str) -> None:
    gold = load_gold(sid)
    meta = gold["extraction_metadata"]
    print(f"{sid}  unit={gold['unit_of_eligibility']}  confidence={meta['confidence']}  "
          f"flagged={meta['flagged_for_review']}\n")
    for n, p in enumerate(predicates(gold), start=1):
        print(f"  P{n:02} {p['loc']:28} {p['field']} {p['op']} {json.dumps(p['value'])}   [{p['kind']}]")
    sup = gold["temporal_validity"].get("supersedes")
    if sup:
        print(f"\n  supersedes (retired): {json.dumps(sup['retired_predicate'])}")
    print(f"\n--- source_clause ---\n{meta['source_clause']}")
    md = RAW_DIR / f"{sid}.md"
    print(f"\n--- {md.relative_to(ROOT)} ---")
    print(md.read_text(encoding="utf-8") if md.exists() else "(not present locally)")


def cmd_extract() -> None:
    from pypdf import PdfReader

    TEXT_DIR.mkdir(parents=True, exist_ok=True)
    pdfs = sorted(RAW_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"no PDFs under {RAW_DIR} (gitignored -- they must be fetched locally first)")
        return
    for pdf in pdfs:
        reader = PdfReader(str(pdf))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
        (TEXT_DIR / f"{pdf.stem}.txt").write_text(text, encoding="utf-8")
        words = len(text.split())
        warn = "  <-- little extractable text; may be scanned" if words < 200 else ""
        print(f"  {pdf.name:52} pages={len(reader.pages):3} words={words:7,}{warn}")


def cmd_search(term: str, sid: str | None) -> None:
    """Case-insensitive search over the .md and any extracted PDF text, with context. Whitespace
    is normalized first because PDF extraction breaks words across lines ("pu cca", "Househol d"),
    so a zero count here is worth re-checking with a shorter term before concluding absence."""
    pattern = re.compile(re.escape(term), re.IGNORECASE)
    targets = [sid] if sid else scheme_ids()
    for s in targets:
        sources = [RAW_DIR / f"{s}.md"] + sorted(TEXT_DIR.glob(f"{s}_*.txt"))
        if not any(p.exists() for p in sources[1:]) and (RAW_DIR / f"{s}.md").exists():
            note = "  (no extracted PDF text for this scheme -- run `extract`, or it has no saved primary)"
        else:
            note = ""
        print(f"=== {s}{note}")
        for path in sources:
            if not path.exists():
                continue
            text = re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))
            hits = list(pattern.finditer(text))
            print(f"  {path.name}: {len(hits)} hit(s)")
            last = -10_000
            for m in hits:
                if m.start() - last < 300:
                    continue
                last = m.start()
                print(f"      ...{text[max(0, m.start() - 160): m.end() + 160]}...")


def cmd_format(check_only: bool) -> int:
    """Rewrite every gold file in the one canonical form (models.dump_gold_json), or with --check
    only report which aren't canonical. Refuses to write if re-parsing the canonical text would not
    give back an identical Scheme -- formatting must never change meaning."""
    from schemelogic.schema.models import Scheme, dump_gold_json

    not_canonical = 0
    for path in sorted(GOLD_DIR.glob("*.json")):
        text = path.read_text(encoding="utf-8")
        scheme = Scheme.model_validate(json.loads(text))
        canonical = dump_gold_json(scheme)
        if Scheme.model_validate(json.loads(canonical)) != scheme:
            raise SystemExit(f"{path.name}: canonical form does not round-trip -- not writing")
        if text == canonical:
            print(f"  {path.name:22} canonical")
            continue
        not_canonical += 1
        if check_only:
            print(f"  {path.name:22} NOT canonical")
        else:
            path.write_text(canonical, encoding="utf-8")
            print(f"  {path.name:22} rewritten")
    return 1 if (check_only and not_canonical) else 0


def cmd_sync() -> int:
    """data/gold/*.json and the Python copies the tests evaluate must hold the same rules."""
    from schemelogic.schema.models import Scheme
    from tests import gold_fixtures as gf
    from tests.fixtures import PM_KISAN

    copies = {
        "AB-PMJAY": gf.AB_PMJAY, "IGNOAPS": gf.IGNOAPS, "MH-LADKI-BAHIN": gf.MAHARASHTRA_LADKI_BAHIN,
        "PM-UJJWALA-2.0": gf.PM_UJJWALA, "PMAY-G": gf.PMAY_G, "PMMVY": gf.PMMVY, "PM-KISAN": PM_KISAN,
    }
    bad = 0
    for s, copy in copies.items():
        disk = Scheme.model_validate(load_gold(s)).model_dump(mode="json", by_alias=True)
        fixture = Scheme.model_validate(copy).model_dump(mode="json", by_alias=True)
        diff = [k for k in disk if disk[k] != fixture[k]]
        bad += bool(diff)
        print(f"  {s:16} {'in sync' if not diff else 'DRIFTED: ' + ', '.join(diff)}")
    return 1 if bad else 0


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] not in {"table", "show", "extract", "search", "sync", "format"}:
        print(__doc__)
        sys.exit(2)
    if args[0] == "table":
        cmd_table()
    elif args[0] == "show":
        cmd_show(args[1])
    elif args[0] == "extract":
        cmd_extract()
    elif args[0] == "search":
        cmd_search(args[1], args[2] if len(args) > 2 else None)
    elif args[0] == "sync":
        sys.exit(cmd_sync())
    elif args[0] == "format":
        sys.exit(cmd_format(check_only="--check" in args))
