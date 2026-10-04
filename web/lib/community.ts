// Shared (client + server) types and rules for community accounts. No secrets here.

export type Role = "family" | "patient" | "leader" | "researcher" | "industry";

export const ROLES: { id: Role; label: string; hint: string }[] = [
  { id: "family", label: "A family member or friend", hint: "Someone close to a person with a rare disease" },
  { id: "patient", label: "A patient", hint: "You live with the condition yourself" },
  { id: "leader", label: "A patient-group leader", hint: "You run or help run a patient organisation" },
  { id: "researcher", label: "A researcher or clinician", hint: "You study the disease or treat patients" },
  { id: "industry", label: "Industry", hint: "Biotech, pharma or a service provider" },
];

export interface SavedItem {
  kind: "questions" | "printout" | "page";
  title: string;
  href: string;
  at: string;
}

export interface PublicUser {
  id: string;
  /** shown to the account holder only */
  email: string;
  role: Role;
  diseases: string[];
  country: string | null;
  consent: { trials: boolean; researcherContact: boolean; weeklyDigest: boolean; groupForms: boolean };
  verified: boolean;
  /** the address was confirmed through the emailed link */
  emailVerified: boolean;
  /** unsubscribed from notification emails */
  emailOptOut: boolean;
  created: string;
  saved: SavedItem[];
}

export interface Announcement {
  id: string;
  diseases: string[];
  title: string;
  summary: string;
  eligibility: string;
  contact: string;
  ethics: string;
  status: "pending" | "approved" | "rejected";
  created: string;
  /** organisation shown to families (never the researcher's email) */
  organisation: string;
}

export interface InboxMessage {
  id: string;
  kind: "announcement" | "contact" | "notice" | "trial" | "grant";
  diseases: string[];
  title: string;
  body: string;
  created: string;
  /** announcements: eligibility, contact, ethics */
  extra?: Record<string, string>;
  /** trial / grant alerts: the public record (ClinicalTrials.gov or NIH RePORTER) */
  url?: string;
}

export const DISEASE_ID = /^(disease:[A-Za-z0-9_-]{2,20}|(MONDO|OMIM|ORPHA):[A-Za-z0-9_.-]{2,20})$/;
export const K_ANON = 5;

/** Coarse countries only (a short list plus "other"), so counts never pinpoint a family. */
export const COUNTRIES = [
  "Australia", "Brazil", "Canada", "China", "France", "Germany", "India", "Italy", "Japan", "Mexico", "Netherlands", "Poland",
  "South Africa", "Spain", "Sweden", "Switzerland", "United Kingdom", "United States", "Other",
];

/** Institutional-looking email domains mark a researcher as verified; everyone else stays unverified. */
export function looksInstitutional(email: string): boolean {
  const d = email.split("@")[1]?.toLowerCase() ?? "";
  return (
    /\.edu$|\.edu\.[a-z]{2}$|\.ac\.[a-z]{2}$|\.nhs\.(uk|net)$|\.gov$|\.uni-[a-z]+\.de$/.test(d) ||
    /(^|\.)(uni|univ|universit|hospital|clinic|klinikum|chu|inserm|cnrs|nih|mrc|charite|karolinska|mayo|chop|broad|sanger|embl|ebi)[a-z.-]*\./.test(d)
  );
}
