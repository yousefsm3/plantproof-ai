"""Stage 8 — Knowledge and investigation memory (Knowledge Engine).

Looks up earlier investigations and human-recorded outcomes. Only confirmed or ruled-out
outcomes count as knowledge; an earlier hypothesis that nobody confirmed stays unresolved
and is never used to support the present conclusion.
"""

from __future__ import annotations

from ..context import ClaimBuilder, RunContext
from ..types import ClaimKind, StageResult, StageStatus, frozen_map

STAGE_ID, NAME, DIVISION = "S8", "Knowledge and memory", "Knowledge Engine"


def signature(ctx: RunContext) -> tuple[str, ...]:
    """Observed indicators of this case: the key used to find similar investigations."""
    s3 = ctx.results.get("S3")
    if not s3 or "params" not in s3.data:
        return ()
    sig = [f"{p}:{v['status']}" for p, v in s3.data["params"].items() if v["status"] != "normal"]
    sig += [f"{p}:abnormal" for p, v in s3.data.get("conditions", {}).items() if v["status"] == "abnormal"]
    return tuple(sorted(sig))


def run(ctx: RunContext) -> StageResult:
    cb = ClaimBuilder(STAGE_ID)
    sig = signature(ctx)
    lead = ctx.results["S4"].data.get("leading") if "S4" in ctx.results else None
    if ctx.knowledge is None:
        cb.add(ClaimKind.UNCERTAINTY, "No knowledge store is connected, so earlier investigations were not consulted.",
               "لا يوجد مخزن معرفة متصل.")
        return StageResult(STAGE_ID, NAME, DIVISION, StageStatus.COMPLETED, "Knowledge store not connected.",
                           "مخزن المعرفة غير متصل.", cb.all(),
                           frozen_map({"signature": sig, "previous": (), "similar": (), "knowledge": {}}),
                           (), ("S3 signature",))
    previous = [i for i in ctx.knowledge.list_investigations(ctx.asset.asset_id)]
    know = ctx.knowledge.knowledge()
    similar = []
    for mech, k in know.items():
        for case in k["confirmed"]:
            shared = set(case["signature"]) & set(sig)
            if shared:
                similar.append({"mechanism": mech, "investigation": case["investigation"],
                                "asset_id": case["asset_id"], "shared": tuple(sorted(shared)),
                                "of": len(set(case["signature"]) | set(sig))})
    similar.sort(key=lambda s: (-len(s["shared"]), s["investigation"]))
    unresolved = [i for i in previous if not i["outcomes"]]

    cb.add(ClaimKind.FACT, f"{len(previous)} earlier investigation(s) of {ctx.asset.asset_id} in the knowledge "
           f"store; {len(unresolved)} have no recorded outcome.",
           f"{len(previous)} تحقيقات سابقة لهذه المعدة.")
    if lead and lead in know:
        k = know[lead]
        cb.add(ClaimKind.FACT, f"Recorded outcomes for this mechanism across assets: {len(k['confirmed'])} "
               f"confirmed, {len(k['ruled_out'])} ruled out (each traceable to its investigation).",
               "نتائج مسجلة لهذه الآلية.")
    for s in similar[:3]:
        cb.add(ClaimKind.FINDING, f"Confirmed {s['mechanism']} on {s['asset_id']} (investigation {s['investigation']}) "
               f"shared {len(s['shared'])} of {s['of']} indicators with this case. Similarity is a pointer for the "
               "engineer, not evidence for this case.", "حالة مؤكدة سابقة مشابهة.")
    if unresolved:
        cb.add(ClaimKind.UNCERTAINTY, f"{len(unresolved)} earlier conclusion(s) were never confirmed; they are "
               "kept as unresolved and are not used as knowledge.", "استنتاجات سابقة غير مؤكدة لا تُعتبر معرفة.")
    return StageResult(
        STAGE_ID, NAME, DIVISION, StageStatus.COMPLETED,
        f"{len(previous)} earlier investigation(s); {len(similar)} confirmed case(s) with shared indicators.",
        f"{len(previous)} تحقيقات سابقة.", cb.all(),
        frozen_map({"signature": sig, "previous": tuple((i["uid"], i["case_id"], i["leading"], i["risk"],
                                                         i["created_at"], len(i["outcomes"])) for i in previous),
                    "similar": tuple(similar), "knowledge": {m: {"confirmed": len(k["confirmed"]),
                                                                 "ruled_out": len(k["ruled_out"])}
                                                             for m, k in know.items()}}),
        ("Knowledge grows only from outcomes a person records; the demo store starts empty and may be wiped "
         "when the app restarts.",),
        ("knowledge store", "S3 signature", "S4 leading explanation"))
