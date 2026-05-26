import re

_SUBQUESTION_RE = re.compile(r"(?=\([0-9]+\)\s*)")


def _count_subquestions(question_text: str) -> int:
    """Count (N)-prefixed subquestion parts. Returns at least 1."""
    cleaned = re.sub(r"\n{2,}", "\n", question_text or "").strip()
    if not cleaned:
        return 1
    parts = [p.strip() for p in _SUBQUESTION_RE.split(cleaned) if p.strip()]
    subq = [p for p in parts if re.match(r"^\([0-9]+\)", p)]
    return len(subq) if subq else 1


def _subpoints_for(n_sub: int, is_hard: bool, is_core: bool) -> list:
    """Return per-subquestion point list according to difficulty/importance rules."""
    if is_hard and is_core:
        return [15] * n_sub
    if is_hard or is_core:
        return [15] + ([10] * (n_sub - 1) if n_sub > 1 else [])
    return [10] * n_sub


def assign_points(questions: list, plan: dict | None = None) -> list:
    """Attach 'points' and 'subpoints' to each question using deterministic rules.

    Rules:
    - tf: 2pt/item
    - short: 5pt/item
    - essay/application: 10pt/subquestion; 15pt for first (or all) if hard/core
    - Minimum 100-pt correction: upgrade 10-pt essay/app subpoints to 15-pt (front-first).
    """
    for q in questions:
        if "points" in q:
            continue
        q_type = q.get("type", "short")
        if q_type == "tf":
            q["points"] = 2
            q["subpoints"] = [2]
        elif q_type == "short":
            q["points"] = 5
            q["subpoints"] = [5]
        else:
            diff = q.get("difficulty", "medium")
            topic_meta = q.get("topic_meta", {})
            importance = topic_meta.get("importance", "supporting")
            is_hard = diff == "hard"
            is_core = importance == "core"
            n_sub = _count_subquestions(q.get("question", ""))
            subpoints = _subpoints_for(n_sub, is_hard, is_core)
            q["subpoints"] = subpoints
            q["points"] = sum(subpoints)

    total = sum(q["points"] for q in questions)
    if total < 100:
        done = False
        for q in questions:
            if done:
                break
            if q.get("type") not in ("essay", "application"):
                continue
            subpoints = q["subpoints"]
            for i, sp in enumerate(subpoints):
                if sp == 10:
                    subpoints[i] = 15
                    q["points"] = sum(subpoints)
                    total += 5
                    if total >= 100:
                        done = True
                        break
        if total < 100:
            print(f"[scoring] 경고: 보정 후에도 {total}점으로 100점 미달.")

    return questions
