import os
import re
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.enum.text import WD_ALIGN_PARAGRAPH

_PAGE_BREAK_KEYWORDS = ("1개", "한 페이지", "페이지당 1", "하나당", "1문제")


def _interpret_format(plan: dict) -> dict:
    """planner 출력 JSON에서 표지 포맷 정보를 직접 추출. LLM 호출 없음."""
    if not plan:
        return {"title": None, "course_info": None, "professor": None,
                "page_break_per_question": False, "school": None}
    layout = str(plan.get("레이아웃") or "").lower()
    page_break = any(kw in layout for kw in _PAGE_BREAK_KEYWORDS)
    return {
        "title": plan.get("시험제목") or None,
        "course_info": plan.get("시험종류") or None,
        "professor": plan.get("담당교수") or None,
        "page_break_per_question": page_break,
        "school": plan.get("학교") or None,
    }


def _set_font(run, size: int = 12, bold: bool = False, color: RGBColor = None):
    run.font.name = "맑은 고딕"
    run.font.size = Pt(size)
    run.font.bold = bold
    if color:
        run.font.color.rgb = color
    rPr = run._r.get_or_add_rPr()
    rFonts = rPr.get_or_add_rFonts()
    rFonts.set(qn("w:eastAsia"), "맑은 고딕")


def _para(doc, text="", size=12, bold=False, align=None, color=None, space_after=None):
    p = doc.add_paragraph()
    if align:
        p.alignment = align
    if space_after is not None:
        p.paragraph_format.space_after = Pt(space_after)
    if text:
        run = p.add_run(text)
        _set_font(run, size=size, bold=bold, color=color)
    return p


def _add_center(doc, text, size=12, bold=False, color=None, space_after=None):
    return _para(doc, text, size=size, bold=bold, align=WD_ALIGN_PARAGRAPH.CENTER,
                 color=color, space_after=space_after)


def _add_horizontal_line(doc, sz="6"):
    p = doc.add_paragraph()
    pPr = p._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), sz)
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), "000000")
    pBdr.append(bottom)
    pPr.append(pBdr)
    return p


def _add_shading(p, fill="EEEEEE"):
    """문단 배경 음영 추가"""
    pPr = p._p.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    pPr.append(shd)


def _add_title_with_borders(doc, text, size=32):
    """제목 위아래 굵은 수평선"""
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(10)
    pPr = p._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    for side in ("top", "bottom"):
        border = OxmlElement(f"w:{side}")
        border.set(qn("w:val"), "single")
        border.set(qn("w:sz"), "18")
        border.set(qn("w:space"), "6")
        border.set(qn("w:color"), "000000")
        pBdr.append(border)
    pPr.append(pBdr)
    run = p.add_run(text)
    _set_font(run, size=size, bold=True)
    return p


def _add_underline_field(doc, label: str, size=12):
    """학번/이름/서명 입력칸 — 레이블 + 밑줄"""
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(8)
    run_label = p.add_run(f"{label}: ")
    _set_font(run_label, size=size, bold=True)
    run_line = p.add_run(" " * 38)
    _set_font(run_line, size=size)
    run_line.underline = True
    return p


def _add_oath_box(doc):
    """성적 정직 서약 — 박스(테이블 1×1)로 강조"""
    table = doc.add_table(rows=1, cols=1)
    tbl = table._tbl
    tblPr = tbl.find(qn("w:tblPr"))
    if tblPr is None:
        tblPr = OxmlElement("w:tblPr")
        tbl.insert(0, tblPr)
    tblBorders = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right"):
        border = OxmlElement(f"w:{side}")
        border.set(qn("w:val"), "single")
        border.set(qn("w:sz"), "8")
        border.set(qn("w:space"), "0")
        border.set(qn("w:color"), "000000")
        tblBorders.append(border)
    tblPr.append(tblBorders)

    cell = table.cell(0, 0)
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = OxmlElement("w:tcMar")
    for side, val in (("top", "120"), ("bottom", "120"), ("left", "180"), ("right", "180")):
        mar = OxmlElement(f"w:{side}")
        mar.set(qn("w:w"), val)
        mar.set(qn("w:type"), "dxa")
        tcMar.append(mar)
    tcPr.append(tcMar)

    p1 = cell.paragraphs[0]
    p1.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p1.paragraph_format.space_after = Pt(6)
    run1 = p1.add_run("성적 정직 서약")
    _set_font(run1, size=13, bold=True)

    p2 = cell.add_paragraph()
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p2.paragraph_format.space_before = Pt(2)
    p2.paragraph_format.space_after = Pt(2)
    run2 = p2.add_run("본인은 이 시험에서 어떠한 부정행위도 하지 않을 것을 서약합니다.")
    _set_font(run2, size=11)
    return table


def _detect_list_count(question_text: str) -> int:
    """문제 텍스트에서 나열 개수 추출. 기본 3개."""
    m = re.search(r'(\d+)\s*(?:가지|개|단계|항목|종류)', question_text)
    if m:
        return min(int(m.group(1)), 8)
    return 3


def _add_answer_space(doc, question: dict):
    """유형별 답란"""
    q_type = question.get("type", "short")

    if q_type == "short":
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(6)
        run_label = p.add_run("답: ")
        _set_font(run_label, size=12, bold=True)
        run_line = p.add_run(" " * 52)
        _set_font(run_line, size=12)
        run_line.underline = True

    elif q_type in ("list", "order"):
        count = question.get("count") or _detect_list_count(question.get("question", ""))
        for idx in range(1, count + 1):
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(4)
            run_num = p.add_run(f"{idx}. ")
            _set_font(run_num, size=12, bold=True)
            run_line = p.add_run(" " * 48)
            _set_font(run_line, size=12)
            run_line.underline = True

    else:
        # 에세이/응용형: 밑줄 7줄 (진한 회색 888888)
        for _ in range(7):
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(14)
            pPr = p._p.get_or_add_pPr()
            pBdr = OxmlElement("w:pBdr")
            bottom = OxmlElement("w:bottom")
            bottom.set(qn("w:val"), "single")
            bottom.set(qn("w:sz"), "4")
            bottom.set(qn("w:space"), "1")
            bottom.set(qn("w:color"), "888888")
            pBdr.append(bottom)
            pPr.append(pBdr)
            run = p.add_run(" ")
            _set_font(run, size=14)

    doc.add_paragraph()


def _add_page_numbers(doc: Document):
    """하단 가운데 페이지 번호 (- N -)"""
    section = doc.sections[0]
    footer = section.footer
    footer.is_linked_to_previous = False
    p = footer.paragraphs[0]
    p.clear()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    run_pre = p.add_run("- ")
    _set_font(run_pre, size=10)

    def _fld_char(fld_type):
        r = OxmlElement("w:r")
        fc = OxmlElement("w:fldChar")
        fc.set(qn("w:fldCharType"), fld_type)
        r.append(fc)
        return r

    def _instr(text):
        r = OxmlElement("w:r")
        el = OxmlElement("w:instrText")
        el.set(qn("xml:space"), "preserve")
        el.text = text
        r.append(el)
        return r

    for node in (_fld_char("begin"), _instr(" PAGE "), _fld_char("separate"), _fld_char("end")):
        p._p.append(node)

    run_suf = p.add_run(" -")
    _set_font(run_suf, size=10)


def _set_margins(doc: Document, cm: float = 2.5):
    section = doc.sections[0]
    for attr in ("top_margin", "bottom_margin", "left_margin", "right_margin"):
        setattr(section, attr, Cm(cm))


TYPE_KO = {"short": "단답형", "essay": "에세이형", "application": "응용형",
           "list": "나열형", "order": "순서형"}


def _add_cover_page(doc: Document, fmt: dict):
    for _ in range(3):
        doc.add_paragraph()

    # 학교명
    school = fmt.get("school") or "○○대학교"
    _add_center(doc, school, size=14, space_after=16)

    # 시험 제목 (위아래 굵은 선, 32pt)
    title = fmt.get("title") or "시험지"
    _add_title_with_borders(doc, title, size=32)
    doc.add_paragraph()

    # 시험 종류
    course_info = fmt.get("course_info") or ""
    if course_info:
        _add_center(doc, course_info, size=14, space_after=4)

    # 담당교수
    professor = fmt.get("professor") or ""
    prof_text = f"담당교수: {professor}" if professor else "담당교수:"
    _add_center(doc, prof_text, size=12, space_after=16)

    _add_horizontal_line(doc)
    doc.add_paragraph()

    _add_oath_box(doc)
    doc.add_paragraph()

    _add_underline_field(doc, "학번")
    _add_underline_field(doc, "이름")
    _add_underline_field(doc, "서명")
    doc.add_paragraph()

    _add_horizontal_line(doc)
    doc.add_page_break()


def save_exam_docx(questions: list, output_path: str, plan: dict = None) -> None:
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    fmt = _interpret_format(plan or {})
    doc = Document()
    _set_margins(doc)
    _add_page_numbers(doc)
    _add_cover_page(doc, fmt)

    n = len(questions)
    points_per_q = round(100 / n) if n > 0 else 10

    page_break = fmt["page_break_per_question"]
    for i, q in enumerate(questions, start=1):
        q_type = q.get("type", "")
        q_type_ko = TYPE_KO.get(q_type, q_type)

        # 문제 번호 (18pt 굵게, 연한 회색 배경) + 배점
        p_num = doc.add_paragraph()
        p_num.paragraph_format.space_before = Pt(12)
        p_num.paragraph_format.space_after = Pt(6)
        _add_shading(p_num, fill="EEEEEE")
        run_num = p_num.add_run(f"문제 {i}.")
        _set_font(run_num, size=18, bold=True)
        run_type = p_num.add_run(f"  [{q_type_ko} / {points_per_q}점]")
        _set_font(run_type, size=11)

        # 문제 본문
        p_q = doc.add_paragraph()
        p_q.paragraph_format.space_after = Pt(10)
        run_q = p_q.add_run(q["question"])
        _set_font(run_q, size=12)

        # 답란
        _add_answer_space(doc, q)

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

    p_title = doc.add_paragraph()
    run_title = p_title.add_run("모범 답안")
    _set_font(run_title, size=16, bold=True)
    doc.add_paragraph()

    for i, qa in enumerate(qa_pairs, start=1):
        q_type = qa.get("type", "")
        q_type_ko = TYPE_KO.get(q_type, q_type)

        p_num = doc.add_paragraph()
        p_num.paragraph_format.space_before = Pt(12)
        run_num = p_num.add_run(f"[{i}]")
        _set_font(run_num, size=13, bold=True)
        run_type = p_num.add_run(f"  ({q_type_ko})  ")
        _set_font(run_type, size=11)
        run_q = p_num.add_run(qa["question"])
        _set_font(run_q, size=11)

        p_ans = doc.add_paragraph()
        run_ans = p_ans.add_run(f"▶ 답안: {qa.get('answer', '')}")
        _set_font(run_ans, size=11, color=RGBColor(0x1F, 0x49, 0x7D))

        rubric = qa.get("rubric", "")
        if rubric:
            p_label = doc.add_paragraph()
            run_label = p_label.add_run("채점 기준")
            _set_font(run_label, size=11, bold=True)

            p_rubric = doc.add_paragraph()
            run_rubric = p_rubric.add_run(rubric)
            _set_font(run_rubric, size=10, color=RGBColor(0x70, 0x30, 0xA0))

        doc.add_paragraph()

    doc.save(output_path)
    print(f"[file_writers] 답안지 저장: {output_path}")
