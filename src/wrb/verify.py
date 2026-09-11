"""The human verification queue: rows to read against the page they came from.

Every accuracy figure this project has is measured on the FROZEN GOLD SET -
nine pages, triple-verified, deliberately excluded from the dataset. So there is
a number for the model and none for the published rows. `checks_pass` says a row
does not contradict itself; nothing says it matches the paper.

This module builds the queue a person reads to answer that, and scores it.

Two sampling rules, both load-bearing:

  * **only the usable tier** (`checks_pass` + `qc_clean`) and only day rows.
    The `flagged` rows are already known to need review; including them would
    misstate the accuracy of the tier a consumer will actually filter to.
  * **stratified by profile, and every profile gets at least one entry.** The
    profiles differ in what verifies them - real printed arithmetic for the
    1883 Annales, only a day-order check for the Revista - so a sample drawn
    from one publication would answer a question nobody asked.

`scripts/g4_verify_app.py` serves this as a small local web tool.
"""

from __future__ import annotations

import random


def entry_id(r: dict) -> str:
    return f"{r['profile']}/{r['item']}/{r['page']}/{r['row']}"


def build_queue(rows: list[dict], *, per_profile: int = 8, seed: int = 0) -> list[dict]:
    """A deterministic, stratified sample of the usable tier.

    `per_profile` is a ceiling, not a quota: a profile with fewer usable rows
    contributes all of them rather than being padded or dropped.
    """
    usable = [r for r in rows if r.get("verdict") in ("checks_pass", "qc_clean") and r.get("is_day_row")]
    by_profile: dict[str, list[dict]] = {}
    for r in usable:
        by_profile.setdefault(r["profile"], []).append(r)

    rng = random.Random(seed)
    queue: list[dict] = []
    for profile in sorted(by_profile):
        group = sorted(by_profile[profile], key=lambda r: (str(r.get("item")), int(r["page"]), int(r["row"])))
        picked = rng.sample(group, min(per_profile, len(group)))
        for r in sorted(picked, key=lambda r: (str(r.get("item")), int(r["page"]), int(r["row"]))):
            values = r.get("values") or {}
            queue.append({
                "id": entry_id(r),
                "profile": profile,
                "item": str(r.get("item")),
                "page": int(r["page"]),
                "row": int(r["row"]),
                "period": r.get("period"),
                "day": values.get("day", values.get("date", values.get("datas"))),
                "verdict": r["verdict"],
                "values": values,
            })
    return queue


def summarise_verdicts(judgements: list[dict]) -> dict:
    """Score a queue by ROWS, per profile and overall.

    `error_rate` is over rows answered, not over profiles - a profile with one
    wrong row and one correct one is at 50%, and averaging those percentages
    would let a small profile swing the headline.
    """
    by_profile: dict[str, dict] = {}
    for j in judgements:
        p = by_profile.setdefault(j["profile"], {"ok": 0, "wrong": 0, "total": 0})
        kind = "ok" if j.get("verdict") == "ok" else "wrong"
        p[kind] += 1
        p["total"] += 1
    total = len(judgements)
    wrong = sum(1 for j in judgements if j.get("verdict") != "ok")
    return {
        "total": total,
        "ok": total - wrong,
        "wrong": wrong,
        "error_rate": (wrong / total) if total else 0.0,
        "by_profile": by_profile,
    }
