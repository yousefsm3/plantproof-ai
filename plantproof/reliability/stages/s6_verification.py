"""Stage 6 — Trust and independent verification (Trust & Verification).

The Brain examines its own earlier claims:
1. every cited record exists in the case;
2. every cited Evidence Engine finding exists;
3. machine-checkable claims are re-evaluated against the cited records;
4. claims with no evidence are never marked verified;
5. hypotheses stay hypotheses; a High label is downgraded while required evidence is
   missing;
6. every contradiction the engine found must be addressed by some claim;
7. key statements are re-checked by the platform's own fact checker, an independent
   method that knows nothing of the Brain.
Any rejected key claim fails the stage.
"""

from __future__ import annotations

import operator

from .. import adapter
from ..context import ClaimBuilder, RunContext
from ..types import Claim, ClaimKind, StageResult, StageStatus, Verification, frozen_map

STAGE_ID, NAME, DIVISION = "S6", "Independent verification", "Trust & Verification"
OPS = {">": operator.gt, "<": operator.lt, ">=": operator.ge, "<=": operator.le}
NO_EVIDENCE_KINDS = (ClaimKind.ASSUMPTION, ClaimKind.UNCERTAINTY, ClaimKind.MISSING, ClaimKind.RECOMMENDATION)


def evaluate_check(claim: Claim, by_id: dict) -> tuple[bool, str]:
    chk = claim.check
    rows = [by_id[i] for i in claim.evidence if i in by_id and by_id[i].parameter == chk.parameter
            and by_id[i].value is not None]
    if not rows:
        return False, f"none of the cited records measures {chk.parameter}"
    if chk.mode == "latest":
        rows = [max(rows, key=lambda r: r.timestamp)]
    results = [OPS[chk.op](r.value, chk.threshold) for r in rows]
    ok = all(results) if chk.mode in ("all", "latest") else any(results)
    shown = ", ".join(f"{r.record_id}={r.value:g}" for r in rows[:4])
    return ok, f"re-checked {chk.parameter} {chk.op} {chk.threshold:g} on {shown}"


def run(ctx: RunContext) -> StageResult:
    cb = ClaimBuilder(STAGE_ID)
    by_id = {}
    for r in ctx.records:
        by_id.setdefault(r.record_id, r)
    usable = ctx.usable_ids()
    full, used = ctx.engine(), ctx.engine(usable)
    known_findings = set()
    for ev in (full, used):
        known_findings |= {f.finding_id for f in ev.contradictions + ev.missing}
        for h in ev.hypotheses:
            known_findings |= {f.finding_id for f in h.supporting + h.refuting + h.missing}

    verdicts: dict[str, tuple[str, str]] = {}
    overrides: dict[str, str] = {}
    prior = [c for sid in ("S1", "S2", "S3", "S4", "S5") if sid in ctx.results for c in ctx.results[sid].claims]

    for c in prior:
        missing_ids = [i for i in c.evidence if i not in by_id]
        bad_refs = [f for f in c.finding_refs if f not in known_findings]
        if missing_ids or bad_refs:
            verdicts[c.claim_id] = (Verification.REJECTED.value,
                                    "cites unknown " + ", ".join(missing_ids + bad_refs))
            continue
        if c.kind in NO_EVIDENCE_KINDS:
            verdicts[c.claim_id] = (Verification.NOT_APPLICABLE.value, f"{c.kind.value}: stated openly, not a conclusion")
            continue
        if c.check is not None:
            ok, note = evaluate_check(c, by_id)
            verdicts[c.claim_id] = ((Verification.VERIFIED if ok else Verification.REJECTED).value, note)
            continue
        if c.kind is ClaimKind.HYPOTHESIS:
            stage4 = ctx.results["S4"].data["ranking"]
            r = next((x for x in stage4 if x.get("claim_id") == c.claim_id), None)
            note, verdict = "hypothesis with cited evidence; remains a hypothesis", Verification.SUPPORTED
            if r and r["label"] == "High" and r["missing"]:
                verdict = Verification.DOWNGRADED
                overrides[r["hypothesis_id"]] = "Medium"
                note = (f"High confidence not justified while required evidence is missing "
                        f"({'; '.join(t for _, t in r['missing'])}); treated as Medium")
            elif r and r["contested_factor"] < 1:
                note += "; contested by contradictions"
            if not c.evidence and r and r["label"] != "Low":
                verdict, note = Verification.REJECTED, "no supporting record cited"
            verdicts[c.claim_id] = (verdict.value, note)
            continue
        if c.evidence or c.finding_refs:
            verdicts[c.claim_id] = (Verification.SUPPORTED.value, "cited records exist; no numeric re-check defined")
        else:
            verdicts[c.claim_id] = (Verification.SUPPORTED.value,
                                    "derived from this stage's computation; no single source record")

    # every engine contradiction must have been considered
    referenced = {f for c in prior for f in c.finding_refs}
    for f in full.contradictions:
        if f.finding_id not in referenced:
            cb.add(ClaimKind.FINDING, f"Contradiction {f.finding_id} ({f.title}) was not addressed by any finding.",
                   "تناقض لم يُعالج.", finding_refs=(f.finding_id,), key=True,
                   verification=Verification.REJECTED)

    # independent cross-check with the platform's fact checker
    sentences: list[tuple[str, str]] = []
    if "S3" in ctx.results and ctx.results["S3"].status is StageStatus.COMPLETED:
        params = ctx.results["S3"].data["params"]
        for c in ctx.results["S3"].claims:
            if c.kind is not ClaimKind.MEASURED or not c.check or c.check.parameter not in params:
                continue
            v = params[c.check.parameter]
            if v["alarm"] is None:
                continue
            word = ("high" if v["direction"] == "high" else "low") if v["status"].startswith("alarm") else \
                   "normal" if v["status"] == "normal" else None
            if word:
                sentences.append((c.claim_id, f"{adapter.plain_label(c.check.parameter).capitalize()} was {word}."))
    lead = ctx.results["S4"].data.get("leading") if "S4" in ctx.results else None
    if lead:
        name = next(h.name for h in used.hypotheses if h.hypothesis_id == lead)
        lead_claim = next(c.claim_id for c in ctx.results["S4"].claims if c.kind is ClaimKind.HYPOTHESIS)
        sentences.append((lead_claim, f"The root cause is {name.lower()}."))
    fc_rows = []
    if sentences:
        checked = adapter.fact_check_sentences(ctx.data, "\n".join(s for _, s in sentences), usable)
        for (cid, sent), res in zip(sentences, checked):
            fc_rows.append((cid, sent, res.verdict, res.reasons[0][0] if res.reasons else ""))
            if res.verdict == "contradicted":
                verdicts[cid] = (Verification.REJECTED.value, f"independent fact check disagrees: {res.reasons[0][0]}")
        agree = sum(r[2] == "supported" for r in fc_rows)
        cb.add(ClaimKind.FINDING, f"Independent fact check: {agree} of {len(fc_rows)} key statements confirmed by "
               "the platform's fact checker.", f"التدقيق المستقل أكد {agree} من {len(fc_rows)}.")

    key_ids = {c.claim_id for c in prior if c.key}
    rejected = [cid for cid, (v, _) in verdicts.items() if v == Verification.REJECTED.value]
    key_rejected = [cid for cid in rejected if cid in key_ids] + \
                   [c.claim_id for c in cb.items if c.verification is Verification.REJECTED]
    counts = {v.value: 0 for v in Verification}
    for v, _ in verdicts.values():
        counts[v] += 1
    cb.add(ClaimKind.FINDING,
           f"{len(verdicts)} claims examined: {counts['verified']} verified against records, {counts['supported']} "
           f"supported, {counts['downgraded']} downgraded, {counts['rejected']} rejected, "
           f"{counts['not_applicable']} stated as assumptions, uncertainties or gaps.",
           f"فُحص {len(verdicts)} ادعاءً: {counts['verified']} مؤكد، {counts['rejected']} مرفوض.", key=True)
    status = StageStatus.VERIFICATION_REJECTED if key_rejected else StageStatus.COMPLETED
    return StageResult(
        STAGE_ID, NAME, DIVISION, status,
        (f"{len(key_rejected)} key claim(s) rejected." if key_rejected else
         f"All key claims passed; {counts['downgraded']} confidence label(s) downgraded."),
        ("رُفضت ادعاءات أساسية." if key_rejected else "اجتازت الادعاءات الأساسية التحقق."),
        cb.all(),
        frozen_map({"verdicts": verdicts, "counts": counts, "label_overrides": overrides,
                    "key_rejected": tuple(key_rejected), "fact_check": tuple(fc_rows)}),
        ("Verification can show that a claim matches its records; it cannot show the records are true.",
         "Hypotheses are never marked verified: only a physical inspection can confirm a cause."),
        ("claims of S1–S5", "records", "Evidence Engine findings", "platform fact checker"))
