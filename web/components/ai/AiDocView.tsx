"use client";

import { Fragment } from "react";
import type { GraphIndex } from "@/lib/graph";
import type { AIResult } from "@/lib/ai";
import type { AiDoc } from "@/lib/ai-shared";
import { relationSentence } from "@/lib/text";
import { useEvidence } from "../evidence/EvidenceProvider";

/**
 * Renders a structured AI document. Each sentence carries numbered superscript citations that open
 * the Evidence panel; sentences with no valid citation are muted and labelled as AI framing.
 */
export function AiDocView({ idx, result }: { idx: GraphIndex; result: AIResult }) {
  const { openEdge } = useEvidence();
  if (!result.doc) return null;
  const doc = result.doc;

  // number citations in order of first appearance; drop ids this graph doesn't have
  const numbers = new Map<string, number>();
  for (const s of doc.sections) for (const x of s.sentences) for (const id of x.edge_ids) {
    if (idx.edgeById.has(id) && !numbers.has(id)) numbers.set(id, numbers.size + 1);
  }
  const cited = (ids: string[]) => ids.filter((id) => numbers.has(id));

  return (
    <article className="space-y-5">
      <header>
        <h3 className="text-[17px] font-semibold leading-snug text-ink">{doc.title}</h3>
        <AiMeta result={result} />
      </header>
      {doc.sections.map((sec, si) => {
        const email = /email/i.test(sec.heading);
        return (
          <section key={si} className={email ? "rounded-lg border border-line bg-subtle/50 px-4 py-3" : ""}>
            {sec.heading && <h4 className="text-sm font-semibold text-ink">{sec.heading}</h4>}
            <p className="mt-1.5 text-[15px] leading-[1.7] text-ink-2">
              {sec.sentences.map((s, i) => {
                const ids = cited(s.edge_ids);
                const framing = ids.length === 0;
                const nextFraming = i + 1 < sec.sentences.length && cited(sec.sentences[i + 1].edge_ids).length === 0;
                return (
                  <Fragment key={i}>
                    <span className={framing ? "text-ink-3" : ""}>{s.text}</span>
                    {ids.map((id) => {
                      const e = idx.edgeById.get(id)!;
                      return (
                        <sup key={id} className="ml-0.5">
                          <button
                            type="button"
                            onClick={() => openEdge(id)}
                            title={`Evidence: ${relationSentence(e, idx.nodeById.get(e.source), idx.nodeById.get(e.target))}`}
                            aria-label={`Open evidence ${numbers.get(id)}`}
                            className="inline-flex min-h-[18px] min-w-[18px] items-center justify-center rounded border border-line bg-white px-1 text-[11px] font-medium tabular-nums text-accent-700 hover:border-accent-500 hover:bg-accent-50"
                          >
                            {numbers.get(id)}
                          </button>
                        </sup>
                      );
                    })}
                    {framing && !nextFraming && (
                      <sup className="ml-1 whitespace-nowrap text-[10px] font-medium uppercase tracking-[0.04em] text-ink-3" title="This text has no direct source in the atlas.">
                        AI framing, no direct source
                      </sup>
                    )}{" "}
                  </Fragment>
                );
              })}
            </p>
          </section>
        );
      })}
    </article>
  );
}

export function AiMeta({ result }: { result: AIResult }) {
  const when = result.generatedAt ? formatTime(result.generatedAt) : null;
  const source =
    result.source === "precomputed" ? "precomputed offline" : result.authPath === "chatgpt" ? "live, using your ChatGPT plan" : result.authPath === "api_key" ? "live, using the OpenAI API" : "live";
  return (
    <p className="mt-1 text-xs text-ink-3">
      AI-generated from the cited sources · {result.model ?? "model unknown"}
      {when ? ` · ${when}` : ""} · {source}. Check each claim against its evidence.
    </p>
  );
}

function formatTime(iso: string) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function docToText(doc: AiDoc): string {
  return [doc.title, ...doc.sections.map((s) => `${s.heading}\n${s.sentences.map((x) => x.text).join(" ")}`)].join("\n\n");
}
