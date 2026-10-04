"use client";

// "Direction fits" / "Direction mismatch" flag next to a therapy for a disease or variant group.
// Shown only when the drug's direct target is the disease gene (see lib/direction.ts). Not a score.
import Link from "next/link";
import { useAtlas } from "../GraphProvider";
import { directionFor, directionForVg, therapiesForGene, useDirection, type DirectionFlag as Flag } from "@/lib/direction";

const verb = (f: Flag) => (f.drug === "decrease" ? "lowers" : "raises");
const amount = (f: Flag) => (f.disease === "GoF" ? "too much" : "too little");

function vgName(label: string | undefined, id: string) {
  return (label ?? id.split(":").slice(2).join(":").replace(/-/g, " ")).replace(/^[A-Z0-9]+:\s*/, "");
}

function One({ f, therapy, disease, plain, vgLabel }: { f: Flag; therapy: string; disease: string; plain: boolean; vgLabel?: string }) {
  const who = f.vg ? `${f.gene} ${vgName(vgLabel, f.vg).toLowerCase()}` : disease;
  const text = plain
    ? f.fits
      ? `${therapy}: it ${verb(f)} ${f.gene} activity, and ${who} involves ${amount(f)} of it, so it pushes in the helpful direction.`
      : `${therapy}: it ${verb(f)} ${f.gene} activity, but ${who} involves ${amount(f)} of it, so it may push the wrong way.`
    : `${f.fits ? "Direction fits" : "Direction mismatch"} (${therapy}): this drug ${verb(f)} ${f.gene} activity; ${who} involves ${amount(f)} ${f.gene} activity.`;
  return (
    <p
      className={`mt-1.5 flex gap-1.5 rounded-md px-2 py-1 text-xs leading-snug ${f.fits ? "bg-[#eef6f1] text-[#25603f]" : "border border-warn-line bg-warn-bg text-warn-ink"}`}
      title="From the drug's direct target and the disease's direction of effect (G2P, ClinGen, DisMech, atlas edges). A flag, not a score."
    >
      <span aria-hidden="true" className="font-semibold">
        {f.fits ? "✓" : "!"}
      </span>
      <span>
        {plain && <b className="font-semibold">{f.fits ? "Direction fits. " : "Direction mismatch. "}</b>}
        {text}
        {plain && " Discuss with your clinician."}
      </span>
    </p>
  );
}

/** Flag(s) for a therapy and a disease (disease-level, or per variant group when the gene mixes directions). */
export function DirectionFlags({ therapyId, diseaseId, plain = false, max = 3 }: { therapyId: string; diseaseId: string; plain?: boolean; max?: number }) {
  const data = useDirection();
  const atlas = useAtlas();
  const flags = directionFor(data, therapyId, diseaseId);
  if (!flags.length) return null;
  const idx = atlas.status === "ready" ? atlas.idx : null;
  const tl = idx?.nodeById.get(therapyId)?.label?.split(" (")[0] ?? "This treatment";
  const dl = idx?.nodeById.get(diseaseId)?.label?.split(" (")[0] ?? diseaseId.replace(/^disease:/, "");
  return (
    <div>
      {flags.slice(0, max).map((f) => (
        <One key={`${therapyId}-${f.vg ?? diseaseId}`} f={f} therapy={tl} disease={dl} plain={plain} vgLabel={f.vg ? idx?.nodeById.get(f.vg)?.label : undefined} />
      ))}
      {!plain && flags.some((f) => f.vg) && (
        <p className="mt-1 text-[11px] text-ink-3">
          Depends on the variant group.{" "}
          <Link href="/method#direction" className="underline">
            How this flag works
          </Link>
        </p>
      )}
    </div>
  );
}

/** Flag for a therapy and one variant group (used on /variant and /sequence results). */
export function DirectionFlagVg({ therapyId, vgId, plain = false }: { therapyId: string; vgId: string; plain?: boolean }) {
  const data = useDirection();
  const atlas = useAtlas();
  const f = directionForVg(data, therapyId, vgId);
  if (!f) return null;
  const idx = atlas.status === "ready" ? atlas.idx : null;
  const tl = idx?.nodeById.get(therapyId)?.label?.split(" (")[0] ?? "This treatment";
  return <One f={f} therapy={tl} disease={f.gene} plain={plain} vgLabel={idx?.nodeById.get(vgId)?.label} />;
}

/** For a variant group: every curated therapy whose direct target is this gene, with its direction flag. */
export function VgDirectionList({ gene, vgId, plain = false }: { gene: string; vgId: string; plain?: boolean }) {
  const data = useDirection();
  const ids = therapiesForGene(data, gene).filter((t) => directionForVg(data, t, vgId));
  if (!ids.length) return null;
  return (
    <div className="mt-2">
      <p className="text-xs font-medium text-ink-3">Treatments that act directly on {gene}, for this group of changes:</p>
      {ids.map((t) => (
        <DirectionFlagVg key={t} therapyId={t} vgId={vgId} plain={plain} />
      ))}
    </div>
  );
}
