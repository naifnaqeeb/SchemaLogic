"use client";

// Fixed example queries, matching the reference design exactly. Unlike the old demo-scenario
// cards these replace, clicking one sends the literal text through the NORMAL chat pipeline
// (same POST /chat + router.classify_message() path as anything typed by hand) -- no
// special-cased shortcut, no pre-built profile.
const EXAMPLE_QUERIES = [
  "Find agriculture schemes for farmers in Maharashtra",
  "What are the benefits for senior citizens?",
  "Check my eligibility for PM Awas Yojana",
  "Education scholarships for students",
];

interface Props {
  onSelect: (query: string) => void;
  busy: boolean;
}

export function ExampleQueryCards({ onSelect, busy }: Props) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      {EXAMPLE_QUERIES.map((query) => (
        <button
          key={query}
          type="button"
          disabled={busy}
          onClick={() => onSelect(query)}
          className="text-left rounded-2xl border border-gray-200 bg-gray-100 px-4 py-4 text-sl-navy hover:border-sl-accent hover:shadow-(--sl-shadow) transition-all disabled:opacity-50"
        >
          &quot;{query}&quot;
        </button>
      ))}
    </div>
  );
}
