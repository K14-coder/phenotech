"use client";

import type { GraphIndex } from "@/lib/graph";
import { AiAction } from "../ai/AiAction";

/**
 * "Draft a collaboration proposal". The server rebuilds the context (neighbours and their why-edges,
 * reusable assets, partners, gaps) from graph.json, so only the disease id is sent.
 */
export function ProposalDraft({ idx, payload }: { idx: GraphIndex; payload: { id: string } & Record<string, unknown> }) {
  return <AiAction idx={idx} kind="proposal" payload={{ id: payload.id }} label="Draft a collaboration proposal" busyLabel="Drafting…" />;
}
