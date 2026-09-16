import type { NextStepsJSON } from "@/lib/types";

export function NextStepsView({ nextSteps }: { nextSteps?: NextStepsJSON }) {
  if (!nextSteps) return null;
  if (!nextSteps.benefits_text && !nextSteps.application_process_text && !nextSteps.official_link) return null;

  return (
    <div className="mt-3 pt-3 border-t border-sl-hairline space-y-1.5">
      <h4 className="font-semibold text-sl-navy">What to do next</h4>
      {nextSteps.benefits_text && (
        <p className="text-sm">
          <span className="font-medium">Benefits:</span> {nextSteps.benefits_text}
        </p>
      )}
      {nextSteps.application_process_text && (
        <p className="text-sm">
          <span className="font-medium">How to apply:</span> {nextSteps.application_process_text}
        </p>
      )}
      {nextSteps.official_link && (
        <a href={nextSteps.official_link} target="_blank" rel="noreferrer" className="text-sm text-sl-accent hover:underline block">
          Official scheme page
        </a>
      )}
    </div>
  );
}
