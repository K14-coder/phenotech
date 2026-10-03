import type { Persona } from "./persona";
// Guided tours. Captions double as the demo video script, so keep each to one or two plain sentences.
// Each step: the page to show, the element to highlight ([data-tour=...] anchors), and an optional action.

export type TourAction = "openSearch" | "openLimitingEvidence" | "showPrecomputedProposal";

export interface TourStep {
  title: string;
  caption: string;
  path: string;
  target: string;
  action?: TourAction;
}

export interface Tour {
  id: string;
  name: string;
  /** the profile the tour is told from (set when the tour starts) */
  persona?: Persona;
  steps: TourStep[];
}

export const TOURS: Record<string, Tour> = {
  maria: {
    id: "maria",
    name: "Follow Maria",
    persona: "leader",
    steps: [
      {
        title: "Start with the gene name",
        caption: "Maria leads a small patient group for VAMP2. She starts by typing the gene name into the search box.",
        path: "/?q=VAMP2",
        target: '[data-tour="search"]',
        action: "openSearch",
      },
      {
        title: "What goes wrong",
        caption: "The page explains in plain words what goes wrong in VAMP2. Each chip opens the evidence behind it.",
        path: "/disease/VAMP2",
        target: '[data-tour="mechanisms"]',
      },
      {
        title: "The closest disease",
        caption: "STXBP1-related disorders come out closest, because both disturb the same machinery that nerve cells use to release their signals.",
        path: "/disease/VAMP2",
        target: '[data-tour="closest-0"]',
      },
      {
        title: "Every link shows its evidence",
        caption: "Every link shows its sources. Anything that limits or contradicts it is listed too, never hidden.",
        path: "/disease/VAMP2",
        target: '[data-tour="counter"]',
        action: "openLimitingEvidence",
      },
      {
        title: "Work that already exists",
        caption: "Simons Searchlight already covers VAMP2, so Maria’s families can join a study that exists today.",
        path: "/disease/VAMP2",
        target: '[data-tour="covers-group"] li',
      },
      {
        title: "Before we join forces",
        caption: "Side by side, the atlas shows what the two communities share, what differs, and what an expert should check first.",
        path: "/compare?a=VAMP2&b=STXBP1",
        target: '[data-tour="compare-share"]',
      },
      {
        title: "A sourced proposal",
        caption: "Maria drafts a collaboration proposal to the STXBP1 Foundation. Every sentence links to the evidence it relies on.",
        path: "/disease/VAMP2",
        target: '[data-tour="proposal"]',
        action: "showPrecomputedProposal",
      },
      {
        title: "How we know",
        caption: "“How we know” counts the links with sources and the quotes checked word for word, and says what the atlas will never do.",
        path: "/method",
        target: '[data-tour="method-numbers"]',
      },
    ],
  },
  syt2: {
    id: "syt2",
    name: "A family with no patient group",
    persona: "family",
    steps: [
      {
        title: "A new diagnosis",
        caption: "A family has just learned their child has a change in the SYT2 gene. They type the gene name into the search box.",
        path: "/?q=SYT2",
        target: '[data-tour="search"]',
        action: "openSearch",
      },
      {
        title: "What this means",
        caption: "The page opens with what SYT2 means in plain words. Every fact has a “How do we know this?” link.",
        path: "/disease/SYT2",
        target: '[data-tour="plain"]',
      },
      {
        title: "An honest answer",
        caption: "The atlas says plainly that there is no patient group just for SYT2, and that this is not the family’s fault.",
        path: "/disease/SYT2",
        target: '[data-tour="no-group"]',
      },
      {
        title: "The closest community",
        caption: "The closest communities already exist, and a registry accepts people with SYT2.",
        path: "/disease/SYT2",
        target: '[data-tour="closest-community"]',
      },
      {
        title: "Questions, not advice",
        caption: "Treatment evidence becomes a question to bring to the child’s doctor, with a page to print for the appointment.",
        path: "/disease/SYT2",
        target: '[data-tour="questions"]',
      },
      {
        title: "Help build the missing community",
        caption: "Finally, the family can tell the atlas about a group, or start one, so the next family finds it.",
        path: "/disease/SYT2",
        target: '[data-tour="help-build"]',
      },
    ],
  },
};
