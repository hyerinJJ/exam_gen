import json
import os
from docx import Document
from docx.shared import Pt, RGBColor
from docx.oxml.ns import qn
from tools.client import get_client, retry_call

FLASH_LITE = "gemini-2.5-flash-lite"

_FORMAT_PROMPT = """다음 시험지 요구사항 목록을 분석하여 포맷 지시사항 JSON을 반환하세요.
마크다운 기호(**,##,*,#,__)를 절대 사용하지 마시오.
다른 텍스트 없이 JSON만 출력하세요.

요구사항:
{reqs}

반환 형식:
{{
  "page_break_per_question": true 또는 false,
  "has_cover": true 또는 false,
  "cover_items": ["표지에 들어갈 텍스트 항목들 (제목, 정직서약문 전문 등)"],
  "header_notes": ["시험지 상단 안내사항들"]
}}"""

_format_cache: dict = {}


def _interpret_format_reqs(extra_reqs: list) -> dict:
    """기타요구사항을 LLM으로 해석해 포맷 결정 dict 반환. 동일 입력은 캐시 사용."""
    default = {"page_break_per_question": False, "has_cover": False, "cover_items": [], "header_notes": []}
    if not extra_reqs:
        return default

    cache_key = tuple(extra_reqs)
    if cache_key in _format_cache:
        return _format_cache[cache_key]

    reqs_text = "\n".join(f"- {r}" for r in extra_reqs)
    prompt = _FORMAT_PROMPT.format(reqs=reqs_text)
    client = get_client()
    response = retry_call(lambda: client.models.generate_content(model=FLASH_LITE, contents=prompt))
    raw = response.text.strip()
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    result = {**default, **json.loads(raw)}
    _format_cache[cache_key] = result
    return result


def _set_font(run, size: int = 12, bold: bool = False):
    run.font.name = "맑은 고딕"
    run.font.size = Pt(size)
    run.font.bold = bold
    rPr = run._r.get_or_add_rPr()
    rFonts = rPr.get_or_add_rFonts()
    rFonts.set(qn("w:eastAsia"), "맑은 고딕")


def _add_heading(doc: Document, text: str, size: int = 14):
    p = doc.add_paragraph()
    run = p.add_run(text)
    _set_font(run, size=size, bold=True)
    return p


def _add_body(doc: Document, text: str, size: int = 12):
    p = doc.add_paragraph()
    run = p.add_run(text)
    _set_font(run, size=size)
    return p


TYPE_KO = {"short": "단답형", "essay": "에세이형", "application": "응용형"}


def save_exam_docx(questions: list, output_path: str, extra_reqs: list = None) -> None:
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    fmt = _interpret_format_reqs(extra_reqs or [])
    doc = Document()

    # 표지
    if fmt["has_cover"]:
        for item in fmt["cover_items"]:
            _add_body(doc, item, size=12)
        doc.add_page_break()

    _add_heading(doc, "시험 문제", size=16)
    doc.add_paragraph()

    # 상단 안내사항
    for note in fmt["header_notes"]:
        _add_body(doc, note, size=11)
    if fmt["header_notes"]:
        doc.add_paragraph()

    page_break = fmt["page_break_per_question"]
    for i, q in enumerate(questions, start=1):
        q_type = TYPE_KO.get(q.get("type", ""), q.get("type", ""))
        _add_body(doc, f"[{i}] ({q_type})  {q['question']}")
        if page_break and i < len(questions):
            doc.add_page_break()
        else:
            doc.add_paragraph()

    doc.save(output_path)
    print(f"[file_writers] 시험지 저장: {output_path}")


def save_answer_key_docx(qa_pairs: list, output_path: str) -> None:
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    doc = Document()

    _add_heading(doc, "모범 답안", size=16)
    doc.add_paragraph()

    for i, qa in enumerate(qa_pairs, start=1):
        q_type = TYPE_KO.get(qa.get("type", ""), qa.get("type", ""))
        _add_body(doc, f"[{i}] ({q_type})  {qa['question']}", size=11)

        p = doc.add_paragraph()
        run = p.add_run(f"▶ 답안: {qa.get('answer', '')}")
        _set_font(run, size=11)
        run.font.color.rgb = RGBColor(0x1F, 0x49, 0x7D)

        rubric = qa.get("rubric", "")
        if rubric:
            p_label = doc.add_paragraph()
            run_label = p_label.add_run("채점 기준")
            _set_font(run_label, size=11, bold=True)

            p_rubric = doc.add_paragraph()
            run_rubric = p_rubric.add_run(rubric)
            _set_font(run_rubric, size=10)
            run_rubric.font.color.rgb = RGBColor(0x70, 0x30, 0xA0)

        doc.add_paragraph()

    doc.save(output_path)
    print(f"[file_writers] 답안지 저장: {output_path}")
