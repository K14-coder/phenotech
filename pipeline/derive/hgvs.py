"""Reference implementation of the variant-notation parser used by the variant lookup.

This file IS the spec in code form: data/derived/variant_lookup_spec.md documents the same rules
(and regexes) so the UI can port them to TypeScript, and data/derived/variant_test_cases.json is
checked against this module by variants.py.

Public functions
  normalize_c(text)      -> canonical c. string ("c.1162C>T") or None
  normalize_p(text)      -> canonical 1-letter protein string ("R388*", "R397fs", "V241del") or None
  classify_c(c)          -> (consequence, certainty, note) from the c. notation alone
  classify_p(p)          -> (consequence, certainty, note) from the protein notation alone
  parse_query(text, genes, tx2gene) -> dict with gene, transcript, c, p, cnv flag, other genes
  lookup(text, data)     -> result dict (see variant_lookup_spec.md, "Result shape")
"""
from __future__ import annotations

import re

AA3 = {"Ala": "A", "Arg": "R", "Asn": "N", "Asp": "D", "Cys": "C", "Gln": "Q", "Glu": "E", "Gly": "G",
       "His": "H", "Ile": "I", "Leu": "L", "Lys": "K", "Met": "M", "Phe": "F", "Pro": "P", "Ser": "S",
       "Thr": "T", "Trp": "W", "Tyr": "Y", "Val": "V", "Sec": "U", "Pyl": "O", "Ter": "*"}
AA1 = set("ACDEFGHIKLMNPQRSTVWYUO")

# consequence -> variant_group slug (mirrors pipeline/biology/build_biology.py VG_GROUPS)
VG_SLUG = {"nonsense": "truncating", "frameshift": "truncating", "start_lost": "truncating",
           "splice": "splice", "missense": "missense",
           "cnv_single": "whole-gene-deletion", "cnv_multi": "contiguous-gene-deletion"}

# ---------------------------------------------------------------- regexes (ported 1:1 in the spec)
RE_TX = re.compile(r"\b(N[MC]_\d+(?:\.\d+)?)\b", re.I)
RE_TX_GENE = re.compile(r"\b(N[MC]_\d+(?:\.\d+)?)\s*\(\s*([A-Za-z0-9-]+)\s*\)", re.I)
# c. notation: positions may carry intronic offsets (+/-n) or UTR prefixes (-n, *n); ranges with "_"
RE_C = re.compile(
    r"\bc\.\s*((?:[-*]?\d+(?:[+-]\d+)?)(?:_(?:[-*]?\d+(?:[+-]\d+)?))?)\s*"
    r"([ACGTacgt]>[ACGTacgt]|delins[ACGTacgt]+|del[ACGTacgt]*|dup[ACGTacgt]*|ins[ACGTacgt]+|inv)",)
# protein, 3-letter: p.Arg388Ter, p.(Arg388*), Arg388X, p.Arg397SerfsTer37, p.Val241del, p.Leu12=
_AA3 = "(?:" + "|".join(sorted(AA3, key=len, reverse=True)) + ")"
RE_P3 = re.compile(
    r"(?:\b[pP]\.\s*\(?\s*|\b)(" + _AA3 + r")(\d+)(?:_(" + _AA3 + r")(\d+))?"
    r"(" + _AA3 + r"|\*|X|=|\?|fs[A-Za-z*]*\d*|del(?:ins[A-Za-z*]+)?|dup|ins[A-Za-z*]+|[A-Z][a-z]{2}fs\S*)", re.I)
# protein, 1-letter: p.R388*, R388X, p.(R388*), R397Sfs*37, V241del, L12=
RE_P1 = re.compile(
    r"(?:\b[pP]\.\s*\(?\s*|(?<![A-Za-z0-9.]))([ACDEFGHIKLMNPQRSTVWY])(\d+)(?:_([ACDEFGHIKLMNPQRSTVWY])(\d+))?"
    r"([ACDEFGHIKLMNPQRSTVWY*X=?](?:fs\*?\d*)?|fs\*?\d*|del(?:ins[A-Z*]+)?|dup|ins[A-Z*]+)(?![A-Za-z0-9])")
RE_CNV = re.compile(r"(copy[- ]number|\bcnv\b|micro(?:deletion|duplication)|\bdeletion\b|\bduplication\b|"
                    r"\bdel\(|\bdup\(|\)x[0-4]\b|\bx[0134]\b|whole[- ]gene|exons?\s*\d+(?:\s*[-–]\s*\d+)?\s*(?:del|dup))",
                    re.I)
RE_GENE_TOKEN = re.compile(r"\b([A-Z][A-Z0-9]{1,9}(?:-AS1)?)\b")


def _aa(code: str) -> str:
    """3-letter or 1-letter amino-acid code (or Ter/X/*) to 1-letter; '' if not an amino acid."""
    if code in ("*", "X", "x"):
        return "*"
    if len(code) == 3:
        return AA3.get(code[0].upper() + code[1:].lower(), "")
    return code.upper() if code.upper() in AA1 else ""


def normalize_c(text: str):
    m = RE_C.search(text or "")
    if not m:
        return None
    pos, change = m.group(1), m.group(2)
    if ">" in change:
        change = change.upper()
    else:
        kind = re.match(r"(delins|del|dup|ins|inv)", change).group(1)
        change = kind + change[len(kind):].upper()
    return f"c.{pos}{change}"


def normalize_p(text: str):
    """Canonical 1-letter protein change. fs suffixes (SerfsTer37, fs*37) collapse to 'fs'."""
    text = text or ""
    for m in RE_P3.finditer(text):
        a1, pos, a2, pos2, rest = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
        ref = _aa(a1)
        if not ref:
            continue
        rng = f"_{_aa(a2)}{pos2}" if a2 else ""
        r = rest
        if re.search(r"fs", r, re.I):
            return f"{ref}{pos}fs"
        if r.lower().startswith("delins"):
            ins = re.findall(_AA3 + r"|\*", r[6:], re.I)
            return f"{ref}{pos}{rng}delins" + "".join(_aa(x) for x in ins)
        if r.lower().startswith("del"):
            return f"{ref}{pos}{rng}del"
        if r.lower().startswith("dup"):
            return f"{ref}{pos}{rng}dup"
        if r.lower().startswith("ins"):
            ins = re.findall(_AA3 + r"|\*", r[3:], re.I)
            return f"{ref}{pos}{rng}ins" + "".join(_aa(x) for x in ins)
        if r in ("=", "?"):
            return f"{ref}{pos}{r}"
        alt = _aa(r)
        if alt:
            return f"{ref}{pos}{alt}"
    for m in RE_P1.finditer(text):
        ref, pos, a2, pos2, rest = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
        rng = f"_{a2}{pos2}" if a2 else ""
        if "fs" in rest:
            return f"{ref}{pos}fs"
        if rest.startswith(("del", "dup", "ins")):
            return f"{ref}{pos}{rng}{rest}"
        if rest in ("=", "?"):
            return f"{ref}{pos}{rest}"
        return f"{ref}{pos}{_aa(rest[0])}"
    return None


def classify_p(p: str):
    """Consequence from a canonical protein change alone."""
    if not p:
        return None
    if p.endswith("fs"):
        return ("frameshift", "certain", "frameshift in the protein notation")
    if re.fullmatch(r"M1(\?|[A-Z*])", p) or p.endswith("?"):
        return ("other", "likely", "start-codon change (start-lost); grouped with truncating variants")
    if re.search(r"(delins|del|dup|ins)", p):
        if p.endswith("*") or re.search(r"ins[A-Z]*\*", p):
            return ("nonsense", "likely", "in-frame change that introduces a stop codon")
        return ("inframe_indel", "certain", "in-frame deletion/insertion/duplication")
    if p.endswith("="):
        return ("synonymous", "certain", "no amino-acid change")
    if p.endswith("*"):
        return ("nonsense", "certain", "premature stop codon")
    if re.fullmatch(r"[A-Z]\d+[A-Z]", p):
        return ("missense", "certain", "single amino-acid substitution")
    return ("other", "unknown", "protein notation not recognised")


def _pos_parts(pos: str):
    """'1162' -> (1162, 0, ''); '1029+1' -> (1029, 1, ''); '-15' -> (15, 0, '-'); '*20' -> (20, 0, '*')."""
    m = re.fullmatch(r"([-*]?)(\d+)(?:([+-])(\d+))?", pos)
    pre, base, sign, off = m.group(1), int(m.group(2)), m.group(3), m.group(4)
    offset = (int(off) if sign == "+" else -int(off)) if off else 0
    return base, offset, pre


def classify_c(c: str):
    """Consequence from the c. notation alone (no reference sequence available)."""
    if not c:
        return None
    m = re.fullmatch(r"c\.([^A-Za-z_]+?)(?:_([^A-Za-z]+?))?([ACGT]>[ACGT]|delins[ACGT]+|del[ACGT]*|dup[ACGT]*|ins[ACGT]+|inv)", c)
    if not m:
        return ("other", "unknown", "c. notation not recognised")
    p1, p2, change = m.group(1), m.group(2), m.group(3)
    parts = [_pos_parts(p1)] + ([_pos_parts(p2)] if p2 else [])
    offsets = [o for _, o, _ in parts]
    prefixes = [pre for _, _, pre in parts]
    if any(pre in ("-", "*") for pre in prefixes) and all(pre in ("-", "*") for pre in prefixes):
        return ("other", "likely", "untranslated region (UTR) change")
    if any(abs(o) in (1, 2) for o in offsets if o):
        return ("splice", "likely", "canonical splice site (intron position +/-1 or 2)")
    if any(offsets):
        if all(abs(o) <= 10 for o in offsets if o):
            return ("splice", "possible", "intronic change near an exon boundary; may affect splicing")
        return ("other", "unknown", "deep intronic change; effect cannot be read from the notation")
    if ">" in change:
        base = parts[0][0]
        if base in (1, 2, 3) and not p2:
            return ("other", "likely", "start-codon change (start-lost); grouped with truncating variants")
        return ("other", "unknown", "exonic single-letter change: missense, nonsense or silent cannot be told "
                                    "from the c. notation alone (look for the p. notation)")
    # length of deletion / insertion
    start = parts[0][0]
    end = parts[1][0] if p2 else start
    span = end - start + 1
    if change.startswith("delins"):
        net = len(change) - 6 - span
    elif change.startswith("del"):
        net = -span
    elif change.startswith("dup"):
        net = span
    elif change.startswith("ins"):
        net = len(change) - 3
    else:  # inv
        return ("other", "unknown", "inversion")
    if net % 3 == 0:
        return ("inframe_indel", "likely", f"net length change {net:+d} bases keeps the reading frame")
    return ("frameshift", "likely", f"net length change {net:+d} bases shifts the reading frame")


def parse_query(text: str, genes, tx2gene):
    text = (text or "").strip()
    out = {"raw": text, "gene": None, "gene_source": None, "transcript": None, "c": None, "p": None,
           "cnv": False, "non_slice_gene": None}
    m = RE_TX_GENE.search(text)
    if m:
        out["transcript"] = m.group(1).upper()
        out["gene"] = m.group(2).upper()
        out["gene_source"] = "transcript(gene)"
    else:
        mt = RE_TX.search(text)
        if mt:
            out["transcript"] = mt.group(1).upper()
            base = out["transcript"].split(".")[0]
            if base in tx2gene:
                out["gene"], out["gene_source"] = tx2gene[base], "transcript"
    if not out["gene"]:
        for tok in RE_GENE_TOKEN.findall(text.upper()):
            if tok in genes:
                out["gene"], out["gene_source"] = tok, "symbol"
                break
    if not out["gene"]:
        for tok in RE_GENE_TOKEN.findall(text):
            if normalize_p(tok) or tok in ("CNV", "DEL", "DUP", "MANE", "HGVS", "ACMG", "VUS", "NM", "NC"):
                continue
            if re.fullmatch(r"[ACGT]+", tok):
                continue
            out["non_slice_gene"] = tok
            break
    elif out["gene"] not in genes:
        out["non_slice_gene"], out["gene"] = out["gene"], None
    out["c"] = normalize_c(text)
    out["p"] = normalize_p(text) or normalize_p(re.sub(r"(?<![A-Za-z0-9.])([a-z])(\d+)([a-z*])(?![A-Za-z0-9])", lambda m: m.group(0).upper(), text))
    out["cnv"] = bool(RE_CNV.search(text)) and not out["c"] and not out["p"]
    return out


def lookup(text: str, data: dict) -> dict:
    """Look a typed variant up in data/derived/variants.json (already loaded as `data`)."""
    genes = set(data["genes"])
    tx2gene = data["transcript_to_gene"]
    q = parse_query(text, genes, tx2gene)
    res = {"query": q, "status": None, "matches": [], "warnings": [], "fallback": None}
    if q["non_slice_gene"] and not q["gene"]:
        res["status"] = "gene_not_in_atlas"
        res["warnings"].append(f"{q['non_slice_gene']} is not one of the {len(genes)} genes in this atlas slice.")
        return res
    if not (q["c"] or q["p"] or q["cnv"]):
        res["status"] = "unparsed"
        return res
    search_genes = [q["gene"]] if q["gene"] else sorted(genes)
    idx = data["index"]

    def rows(gene, ids):
        g = data["genes"][gene]
        return [dict(zip(data["fields"], g["variants"][i]), gene=gene) for i in ids]

    hits, how = [], None
    for gene in search_genes:
        if q["c"] and f"c:{gene}:{q['c']}" in idx:
            hits += rows(gene, idx[f"c:{gene}:{q['c']}"]); how = "c"
    if not hits and q["p"]:
        for gene in search_genes:
            if f"p:{gene}:{q['p']}" in idx:
                hits += rows(gene, idx[f"p:{gene}:{q['p']}"]); how = "p"
    if not hits and q["p"]:
        for gene in search_genes:
            if f"iso:{gene}:{q['p']}" in idx:
                hits += rows(gene, idx[f"iso:{gene}:{q['p']}"]); how = "isoform"
    if hits:
        res["status"] = "clinvar_match"
        res["match_on"] = how
        res["matches"] = hits
        if how == "isoform":
            res["warnings"].append("Matched only through another isoform's amino-acid numbering in ClinVar; "
                                   "confirm the transcript with your genetic counsellor.")
        if not q["gene"]:
            res["warnings"].append("No gene was given; the gene was inferred from the match.")
        if q["c"] and q["p"] and how == "c":
            ps = {h["p"] for h in hits}
            if q["p"] not in ps:
                res["warnings"].append("The protein change you typed does not match the one ClinVar lists "
                                       "for this c. change; check the report.")
        if q["transcript"]:
            tx_rec = {h["hgvs"].split("(")[0] for h in hits if h["hgvs"].startswith("N")}
            if tx_rec and q["transcript"].split(".")[0] not in {t.split(".")[0] for t in tx_rec}:
                res["warnings"].append(f"Your report uses {q['transcript']}; ClinVar's record uses "
                                       f"{', '.join(sorted(tx_rec))}. Numbering can differ between transcripts, "
                                       "so confirm the match.")
        return res
    # fallback: classify the typed notation by pattern
    cls = classify_p(q["p"]) if q["p"] else None
    if (not cls or cls[1] == "unknown") and q["c"]:
        cls = classify_c(q["c"])
    if not cls and q["cnv"]:
        cls = ("cnv", "likely", "copy-number / whole-gene or exon-level change")
    consequence, certainty, note = cls
    slug = VG_SLUG.get("start_lost" if "start-lost" in note else consequence)
    if consequence == "cnv":
        slug = "whole-gene-deletion"
    vg = None
    if q["gene"] and slug and f"vg:{q['gene']}:{slug}" in data["variant_groups"]:
        vg = f"vg:{q['gene']}:{slug}"
    res["status"] = "not_in_clinvar_plp" if q["gene"] else "not_found_no_gene"
    res["fallback"] = {"consequence": consequence, "certainty": certainty, "note": note, "variant_group": vg}
    res["warnings"].append("Not among ClinVar's pathogenic/likely-pathogenic records for this gene (it may be "
                           "a VUS, benign, new, or written differently). The type shown is read from the "
                           "notation only.")
    return res
