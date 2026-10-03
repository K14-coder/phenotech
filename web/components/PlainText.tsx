"use client";

// Wraps glossary terms in a text with their plain-language explanation (first mention of each), so
// Devon never meets jargon without one.
import { Fragment } from "react";
import { GLOSSARY } from "@/lib/glossary";
import { Term } from "./Term";

// longest first, so "developmental and epileptic encephalopathy" wins over "encephalopathy"
const KEYS = Object.keys(GLOSSARY)
  .filter((k) => k.length > 3 && !["mechanism", "contested", "inferred", "hypothesis", "confidence", "centrality", "cross-cluster bridge"].includes(k))
  .sort((a, b) => b.length - a.length);
const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const RE = new RegExp(`\\b(${KEYS.map(escape).join("|")})(s?)\\b`, "gi");

export function PlainText({ text }: { text: string }) {
  const out: React.ReactNode[] = [];
  const seen = new Set<string>();
  let last = 0;
  for (const m of text.matchAll(RE)) {
    const key = m[1].toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    const at = m.index ?? 0;
    if (at > last) out.push(text.slice(last, at));
    out.push(
      <Term key={at} k={key}>
        {m[0]}
      </Term>,
    );
    last = at + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return <>{out.map((x, i) => (typeof x === "string" ? <Fragment key={`t${i}`}>{x}</Fragment> : x))}</>;
}
