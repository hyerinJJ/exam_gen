import json
import os
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.enum.text import WD_ALIGN_PARAGRAPH

_PAGE_BREAK_KEYWORDS = ("1개", "한 페이지", "페이지당 1", "하나당", "1문제")


def _interpret_format(plan: dict) -> dict:
    """planner 출력 JSON에서 표지 포맷 정보를 직접 추출. LLM 호출 없음."""
    if not plan:
        return {"title": None, "course_info": None, "professor": None, "page_break_per_question": False}

    layout = str(plan.get("레이아웃") or "").lower()
    page_break = any(kw in layout for kw in _PAGE_BREAK_KEYWORDS)

    return {
        "title": plan.get("시험제목") or None,
        "course_info": plan.get("시험종류") or None,
        "professor": plan.get("담당교수") or None,
        "page_break_per_question": page_break,
    }


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


def _add_center(doc: Document, text: str, size: int = 12, bold: bool = False):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(text)
    _set_font(run, size=size, bold=bold)
    return p


def _add_horizontal_line(doc: Document):
    p = doc.add_paragraph()
    pPr = p._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "6")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), "000000")
    pBdr.append(bottom)
    pPr.append(pBdr)
    return p


def _add_cover_page(doc: Document, fmt: dict):
    # 로고 자리 (빈 공간)
    for _ in range(5):
        doc.add_paragraph()

    # 시험지 제목
    title = fmt.get("title") or "시험지"
    _add_center(doc, title, size=24, bold=True)
    doc.add_paragraph()

    # 학수번호 / 학년도 학기 / 시험 종류
    course_info = fmt.get("course_info") or ""
    _add_center(doc, course_info, size=14)
    doc.add_paragraph()

    # 담당교수 / 날짜
    professor = fmt.get("professor") or ""
    prof_label = f"담당교수: {professor}" if professor else "담당교수:"
    _add_center(doc, f"{prof_label}                    날짜:", size=12)
    doc.add_paragraph()

    _add_horizontal_line(doc)
    doc.add_paragraph()

    # 성적 정직 서약
    _add_center(doc, "성적 정직 서약", size=14, bold=True)
    doc.add_paragraph()
    _add_center(doc, "본인은 이 시험에서 어떠한 부정행위도 하지 않을 것을 서약합니다.", size=12)
    doc.add_paragraph()

    _add_body(doc, "학번: _______________________", size=12)
    _add_body(doc, "이름: _______________________", size=12)
    _add_body(doc, "서명: _______________________", size=12)
    doc.add_paragraph()

    _add_horizontal_line(doc)
    doc.add_page_break()


TYPE_KO = {"short": "단답형", "essay": "에세이형", "application": "응용형"}


def _set_margins(doc: Document, cm: float = 2.5):
    section = doc.sections[0]
    for attr in ("top_margin", "bottom_margin", "left_margin", "right_margin"):
        setattr(section, attr, Cm(cm))


def save_exam_docx(questions: list, output_path: str, plan: dict = None) -> None:
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    fmt = _interpret_format(plan or {})
    doc = Document()
    _set_margins(doc)

    # 표지 (항상 추가)
    _add_cover_page(doc, fmt)

    _add_heading(doc, "시험 문제", size=16)
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
    _set_margins(doc)

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
