import { explain } from "@/lib/glossary";

/**
 * Plain-language explainer for a technical term. Hover or keyboard-focus shows a one-line
 * definition. Renders plain text if the glossary has no entry.
 */
export function Term({ children, k }: { children: string; k?: string }) {
  const tip = explain(k ?? children);
  if (!tip) return <>{children}</>;
  return (
    <span className="term" tabIndex={0} aria-label={`${children}: ${tip}`}>
      {children}
      <span className="term-tip" role="tooltip" aria-hidden="true">
        {tip}
      </span>
    </span>
  );
}

/** Inline one-line explanation (for places where a tooltip is not enough, e.g. mechanism pages). */
export function Explainer({ term, className = "" }: { term: string; className?: string }) {
  const tip = explain(term);
  if (!tip) return null;
  return <p className={`text-sm leading-relaxed text-ink-3 ${className}`}>{tip}</p>;
}
