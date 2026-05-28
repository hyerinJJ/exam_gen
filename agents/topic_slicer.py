import re


_FILE_RE = re.compile(r"^===\s*(.+?)\s*===\s*$", re.MULTILINE)
_UNIT_RE = re.compile(r"^\[(?:페이지|슬라이드)\s*([0-9]+)\]\s*$", re.MULTILINE)


def _terms(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        parts = re.split(r"[\s,;/|()·\-]+", value)
        return [p.strip().lower() for p in parts if len(p.strip()) >= 2]
    if isinstance(value, list):
        terms = []
        for item in value:
            terms.extend(_terms(item))
        return terms
    return []


def split_raw_text(raw_text: str) -> list[dict]:
    """Collector raw_text를 파일/페이지/슬라이드 단위 chunk로 나눈다."""
    chunks = []
    file_matches = list(_FILE_RE.finditer(raw_text or ""))
    if not file_matches:
        return [{"source_file": "unknown", "unit": "", "text": (raw_text or "").strip(), "index": 0}]

    for idx, match in enumerate(file_matches):
        filename = match.group(1).strip()
        start = match.end()
        end = file_matches[idx + 1].start() if idx + 1 < len(file_matches) else len(raw_text)
        body = raw_text[start:end].strip()
        unit_matches = list(_UNIT_RE.finditer(body))
        if not unit_matches:
            if body:
                chunks.append({"source_file": filename, "unit": "", "text": body, "index": len(chunks)})
            continue
        for uidx, unit in enumerate(unit_matches):
            u_start = unit.end()
            u_end = unit_matches[uidx + 1].start() if uidx + 1 < len(unit_matches) else len(body)
            text = body[u_start:u_end].strip()
            if text:
                chunks.append({"source_file": filename, "unit": unit.group(0), "text": text, "index": len(chunks)})
    return chunks


def _score_chunk(topic: dict, chunk: dict) -> float:
    text = chunk.get("text", "").lower()
    score = 0.0
    source_file = topic.get("source_file", "")
    if source_file and source_file != "unknown" and chunk.get("source_file") == source_file:
        score += 6.0
    for term in _terms(topic.get("name")):
        if term in text:
            score += 3.0
    for term in _terms(topic.get("concept_group")):
        if term != "unknown" and term in text:
            score += 1.5
    for term in _terms(topic.get("reason")):
        if term in text:
            score += 0.5
    return score


def attach_topic_evidence(raw_text: str, topics: list[dict],
                          max_chunks: int = 4, max_chars: int = 2400) -> list[dict]:
    """각 topic에 강의 원문 evidence_text와 source_refs를 붙인다."""
    chunks = split_raw_text(raw_text)
    enriched = []
    for idx, topic in enumerate(topics, start=1):
        topic_copy = dict(topic)
        ranked = sorted(
            chunks,
            key=lambda c: (-_score_chunk(topic_copy, c), c.get("index", 0)),
        )
        selected = [c for c in ranked if _score_chunk(topic_copy, c) > 0][:max_chunks]
        if not selected and chunks:
            selected = chunks[:1]

        evidence_parts = []
        refs = []
        used = 0
        for chunk in selected:
            label = " ".join(p for p in [chunk.get("source_file", ""), chunk.get("unit", "")] if p)
            text = re.sub(r"\s+", " ", chunk.get("text", "")).strip()
            remaining = max_chars - used
            if remaining <= 0:
                break
            clipped = text[:remaining].strip()
            if clipped:
                evidence_parts.append(f"[{label}]\n{clipped}" if label else clipped)
                refs.append(label or chunk.get("source_file", "unknown"))
                used += len(clipped)

        topic_copy["topic_id"] = topic_copy.get("topic_id") or f"topic_{idx}"
        topic_copy["evidence_text"] = "\n\n".join(evidence_parts)
        topic_copy["source_refs"] = refs
        enriched.append(topic_copy)
    return enriched
