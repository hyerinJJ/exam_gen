import os
from docx import Document
from docx.shared import Pt, Cm, Mm
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.section import WD_SECTION

_PAGE_BREAK_KEYWORDS = ("1개", "한 페이지", "페이지당 1", "하나당", "1문제")

FONT_COVER = "HY견명조"
FONT_BODY  = "HY신명조"
_SPACING_BODY = -4  # twips ≈ 0.2pt narrower

# 출력 순서: tf → short → essay → application
_TYPE_ORDER = ["tf", "short", "essay", "application"]

TYPE_KO = {
    "short": "단답형", "essay": "에세이형", "application": "응용형",
    "tf": "진위형", "list": "나열형", "order": "순서형",
}

# 문제 헤더에 표시할 유형명
_TYPE_DISPLAY = {
    "tf":          "True/False",
    "short":       "단답형",
    "essay":       "",   # 유형 드러내지 않음
    "application": "",   # 유형 드러내지 않음
}

# 문제 헤더에 표시할 지시문
_TYPE_GUIDE = {
    "tf":          "(빈칸에 T 또는 F를 작성)",
    "short":       "",
    "essay":       "",
    "application": "",
}


# ── 폰트 / 공통 유틸 ──────────────────────────────────────────────────────────

def _set_font(run, size: int, bold: bool = False, font_name: str = FONT_BODY,
              italic: bool = False, underline: bool = False):
    run.font.name = font_name
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.underline = underline
    rPr = run._r.get_or_add_rPr()
    rFonts = rPr.get_or_add_rFonts()
    for attr in ("w:eastAsia", "w:hAnsi", "w:ascii"):
        rFonts.set(qn(attr), font_name)
    if font_name == FONT_BODY:
        sp_el = OxmlElement("w:spacing")
        sp_el.set(qn("w:val"), str(_SPACING_BODY))
        rPr.append(sp_el)



def _tf_blank_run(paragraph, size: int = 12):
    """TF 답란: 공백 + underline=True (FONT_BODY, underscore 이중선 없음)."""
    run = paragraph.add_run("       ")
    run.font.name = FONT_BODY
    run.font.size = Pt(size)
    run.font.underline = True
    rPr = run._r.get_or_add_rPr()
    rFonts = rPr.get_or_add_rFonts()
    for attr in ("w:eastAsia", "w:hAnsi", "w:ascii"):
        rFonts.set(qn(attr), FONT_BODY)
    sp_el = OxmlElement("w:spacing")
    sp_el.set(qn("w:val"), str(_SPACING_BODY))
    rPr.append(sp_el)


def _fld_run(fld_type: str):
    r = OxmlElement("w:r")
    fc = OxmlElement("w:fldChar")
    fc.set(qn("w:fldCharType"), fld_type)
    r.append(fc)
    return r


def _instr_run(text: str):
    r = OxmlElement("w:r")
    el = OxmlElement("w:instrText")
    el.set(qn("xml:space"), "preserve")
    el.text = text
    r.append(el)
    return r


def _cover_info_line(doc: Document, label: str, size: int = 16,
                     font_name: str = FONT_COVER, space_after: int = 8):
    """라벨 + 밑줄 한 줄 — 왼쪽 공백 4칸 들여쓰기."""
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(space_after)

    def _r(text, underline=False):
        run = p.add_run(text)
        run.font.name = font_name
        run.font.size = Pt(size)
        run.font.underline = underline
        rPr = run._r.get_or_add_rPr()
        rFonts = rPr.get_or_add_rFonts()
        for attr in ("w:eastAsia", "w:hAnsi", "w:ascii"):
            rFonts.set(qn(attr), font_name)

    _r(" " * 26)
    _r(label + " ")
    _r(" " * 22, underline=True)


def _page_break(doc: Document):
    p = doc.add_paragraph()
    r = OxmlElement("w:r")
    br = OxmlElement("w:br")
    br.set(qn("w:type"), "page")
    r.append(br)
    p._p.append(r)


def _set_margins(section, cm: float = 2.54):
    for attr in ("top_margin", "bottom_margin", "left_margin", "right_margin"):
        setattr(section, attr, Cm(cm))
    section.page_width  = Mm(210)
    section.page_height = Mm(297)


# ── 표지 ──────────────────────────────────────────────────────────────────────

def _add_cover_page(doc: Document, fmt: dict):
    """PDF 양식과 동일한 표지."""
    title        = fmt.get("title")        or "시험지"
    english_name = fmt.get("english_name") or ""
    course_info  = fmt.get("course_info")  or ""
    exam_date    = fmt.get("exam_date")    or ""
    time_limit   = fmt.get("time_limit")   or ""
    semester     = fmt.get("semester")     or ""

    # 시험종류 중복 체크
    def _norm(s: str) -> str:
        return s.replace(" ", "").lower()

    show_course_info = bool(
        course_info
        and _norm(course_info) not in _norm(title)
        and _norm(course_info) not in _norm(english_name)
    )

    for _ in range(5):
        doc.add_paragraph()

    # 과목명 한글 22pt center
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_title.paragraph_format.space_after = Pt(4)
    _set_font(p_title.add_run(title), size=22, font_name=FONT_COVER)

    # 과목명 영문 22pt center
    if english_name:
        p_eng = doc.add_paragraph()
        p_eng.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_eng.paragraph_format.space_after = Pt(6)
        _set_font(p_eng.add_run(english_name), size=22, font_name=FONT_COVER)

    # 학기
    if semester:
        p_sem = doc.add_paragraph()
        p_sem.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_sem.paragraph_format.space_after = Pt(4)
        _set_font(p_sem.add_run(semester), size=16, font_name=FONT_COVER)

    # 시험 종류 (중복 아닐 때만)
    if show_course_info:
        p_ci = doc.add_paragraph()
        p_ci.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_ci.paragraph_format.space_after = Pt(8)
        _set_font(p_ci.add_run(course_info), size=16, font_name=FONT_COVER)

    # 시험 일시
    if exam_date:
        doc.add_paragraph()
        p_dt = doc.add_paragraph()
        p_dt.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_dt.paragraph_format.space_after = Pt(4)
        _set_font(p_dt.add_run(f"시험 일시: {exam_date}"), size=16, font_name=FONT_COVER)

    # 제한시간 · 총점 (시험 일시 다음 줄)
    extra_parts = []
    if time_limit:
        extra_parts.append(f"제한시간: {time_limit}")
    if fmt.get("total_score"):
        extra_parts.append(f"총점: {fmt['total_score']}점")
    if extra_parts:
        if not exam_date:
            doc.add_paragraph()
        p_extra = doc.add_paragraph()
        p_extra.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_extra.paragraph_format.space_after = Pt(4)
        _set_font(p_extra.add_run("  /  ".join(extra_parts)), size=16, font_name=FONT_COVER)

    for _ in range(2):
        doc.add_paragraph()

    # ── ※인적 사항 ──────────────────────────────────────────────────
    p_hdr1 = doc.add_paragraph()
    p_hdr1.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_hdr1.paragraph_format.space_after = Pt(6)
    _set_font(p_hdr1.add_run("※인적 사항"), size=16, font_name=FONT_COVER)

    _cover_info_line(doc, "학번:", size=16, font_name=FONT_COVER, space_after=4)
    _cover_info_line(doc, "이름:", size=16, font_name=FONT_COVER, space_after=10)

    doc.add_paragraph()

    # ── ※정직 서약 ──────────────────────────────────────────────────
    p_hdr2 = doc.add_paragraph()
    p_hdr2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_hdr2.paragraph_format.space_after = Pt(8)
    _set_font(p_hdr2.add_run("※정직 서약"), size=16, font_name=FONT_COVER)

    p_oath = doc.add_paragraph()
    p_oath.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_oath.paragraph_format.space_after = Pt(10)
    _set_font(
        p_oath.add_run(
            "본인은 이 시험에서 어떠한 부정행위도 하지 않을 것을 서약하며, "
            "부정행위 적발 시 이에 따른 모든 책임을 감수할 것에 동의합니다."
        ),
        size=16, font_name=FONT_COVER,
    )

    _cover_info_line(doc, "서명:", size=16, font_name=FONT_COVER, space_after=0)


# ── 섹션 설정 ─────────────────────────────────────────────────────────────────

def _configure_cover_section(section):
    """표지 섹션: 헤더/푸터 없음."""
    section.different_first_page_header_footer = True
    for hdr_ftr in (section.header, section.footer,
                    section.first_page_header, section.first_page_footer):
        try:
            hdr_ftr.is_linked_to_previous = False
            if hdr_ftr.paragraphs:
                hdr_ftr.paragraphs[0].clear()
        except Exception:
            pass


def _page_num_run(fld_type: str | None, instr: str | None = None, size_pt: int = 16):
    """PAGE 필드용 런에 폰트 크기를 직접 지정."""
    r = OxmlElement("w:r")
    rPr = OxmlElement("w:rPr")
    for tag in ("w:sz", "w:szCs"):
        el = OxmlElement(tag)
        el.set(qn("w:val"), str(size_pt * 2))  # half-points
        rPr.append(el)
    r.append(rPr)
    if instr is not None:
        el = OxmlElement("w:instrText")
        el.set(qn("xml:space"), "preserve")
        el.text = instr
        r.append(el)
    else:
        fc = OxmlElement("w:fldChar")
        fc.set(qn("w:fldCharType"), fld_type)
        r.append(fc)
    return r


def _add_body_section(doc: Document):
    """표지 다음 새 섹션: 우상단 PAGE 번호(1부터), 푸터/라인 없음."""
    sec = doc.add_section(WD_SECTION.NEW_PAGE)
    _set_margins(sec)

    sectPr = sec._sectPr
    pgNumType = OxmlElement("w:pgNumType")
    pgNumType.set(qn("w:fmt"), "decimal")
    pgNumType.set(qn("w:start"), "1")
    sectPr.append(pgNumType)

    sec.different_first_page_header_footer = False
    hdr = sec.header
    hdr.is_linked_to_previous = False
    p = hdr.paragraphs[0] if hdr.paragraphs else hdr.add_paragraph()
    p.clear()
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p.paragraph_format.space_after = Pt(4)
    for node in (_page_num_run("begin"), _page_num_run(None, " PAGE "),
                 _page_num_run("separate"), _page_num_run("end")):
        p._p.append(node)

    ftr = sec.footer
    ftr.is_linked_to_previous = False
    if ftr.paragraphs:
        ftr.paragraphs[0].clear()


# ── 본문 유틸 ─────────────────────────────────────────────────────────────────

def _add_writing_space(doc: Document, count: int = 8):
    """빈 쓰기 공간 (라인 없음)."""
    for _ in range(count):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after  = Pt(0)
        run = p.add_run(" ")
        run.font.size = Pt(18)


def _group_by_type(questions: list) -> list:
    """
    그룹 규칙:
    - tf / short  : 동일 유형 전체를 하나의 그룹으로 (한 페이지 내)
    - essay / application : 각 문제가 독립 그룹 (문제당 한 페이지)
    순서: tf → short → essay → application
    """
    buckets: dict = {}
    for q in questions:
        t = q.get("type", "short")
        buckets.setdefault(t, []).append(q)

    result = []
    for t in _TYPE_ORDER:
        if t not in buckets:
            continue
        if t in ("tf", "short"):
            result.append((t, buckets[t]))
        else:
            for q in buckets[t]:
                result.append((t, [q]))
    # 알 수 없는 타입
    for t, qs in buckets.items():
        if t not in _TYPE_ORDER:
            result.append((t, qs))
    return result


# ── 입력 해석 ─────────────────────────────────────────────────────────────────

def _interpret_format(plan: dict) -> dict:
    if not plan:
        return {
            "title": None, "course_info": None, "professor": None,
            "page_break_per_question": False, "school": None,
            "department": None, "english_name": None,
            "exam_date": None, "time_limit": None, "total_score": None, "semester": None,
        }
    layout = str(plan.get("레이아웃") or "").lower()
    page_break = any(kw in layout for kw in _PAGE_BREAK_KEYWORDS)
    return {
        "title":       plan.get("시험제목") or plan.get("과목명") or None,
        "course_info": plan.get("시험종류") or None,
        "professor":   plan.get("담당교수") or None,
        "page_break_per_question": page_break,
        "school":      plan.get("학교") or None,
        "department":  plan.get("학과") or None,
        "english_name": plan.get("영문명") or None,
        "exam_date":    plan.get("시험일시") or None,
        "time_limit":   plan.get("제한시간") or None,
        "total_score":  plan.get("총점") or None,
        "semester":     plan.get("학기") or None,
    }


# ── 메인 함수 ─────────────────────────────────────────────────────────────────

def save_exam_docx(questions: list, output_path: str, plan: dict = None) -> None:
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    fmt = _interpret_format(plan or {})

    doc = Document()
    sec0 = doc.sections[0]
    _set_margins(sec0)
    _configure_cover_section(sec0)

    _add_cover_page(doc, fmt)
    _add_body_section(doc)

    n = len(questions)
    points_per_q = round(100 / n) if n > 0 else 10

    grouped = _group_by_type(questions)
    total_groups = len(grouped)

    for group_idx, (q_type, q_list) in enumerate(grouped):
        group_num   = group_idx + 1
        is_last     = group_idx == total_groups - 1
        group_points = points_per_q * len(q_list)
        type_display = _TYPE_DISPLAY.get(q_type, TYPE_KO.get(q_type, q_type))
        type_guide   = _TYPE_GUIDE.get(q_type, "")

        if q_type in ("tf", "short"):
            # ── TF / 단답형: 그룹 헤더 + 소문항 목록 ────────────────
            p_hdr = doc.add_paragraph()
            p_hdr.paragraph_format.space_before = Pt(16)
            p_hdr.paragraph_format.space_after  = Pt(8)
            _set_font(p_hdr.add_run(f"문제 {group_num}"), size=12, bold=True)
            suffix = f" ({group_points}점) {type_display}"
            if type_guide:
                suffix += f" {type_guide}"
            _set_font(p_hdr.add_run(suffix), size=12)

            for sub_num, q in enumerate(q_list, start=1):
                q_text = q.get("question", "")

                if q_type == "tf":
                    p_q = doc.add_paragraph()
                    p_q.paragraph_format.space_before = Pt(4)
                    p_q.paragraph_format.space_after  = Pt(8)
                    _set_font(p_q.add_run(f"({sub_num}) "), size=12)
                    _tf_blank_run(p_q, size=12)
                    _set_font(p_q.add_run(" "), size=12)
                    _set_font(p_q.add_run(q_text), size=12)

                else:  # short
                    p_q = doc.add_paragraph()
                    p_q.paragraph_format.space_before = Pt(4)
                    p_q.paragraph_format.space_after  = Pt(4)
                    _set_font(p_q.add_run(f"({sub_num}) "), size=12)
                    _set_font(p_q.add_run(q_text), size=12)

                    p_ans = doc.add_paragraph()
                    p_ans.paragraph_format.left_indent = Cm(1.0)
                    p_ans.paragraph_format.space_after = Pt(10)
                    _set_font(p_ans.add_run("답: (                         )"), size=12)

        else:
            # ── 에세이 / 응용형: 질문 텍스트를 헤더에 인라인 ────────
            q_text = q_list[0].get("question", "")

            p_hdr = doc.add_paragraph()
            p_hdr.paragraph_format.space_before = Pt(16)
            p_hdr.paragraph_format.space_after  = Pt(10)
            _set_font(p_hdr.add_run(f"문제 {group_num}"), size=12, bold=True)
            _set_font(p_hdr.add_run(f" ({group_points}점) {q_text}"), size=12)

            p_ans_label = doc.add_paragraph()
            p_ans_label.paragraph_format.space_before = Pt(4)
            p_ans_label.paragraph_format.space_after  = Pt(4)
            _set_font(p_ans_label.add_run("답:"), size=12)

            blank_count = 12 if q_type == "application" else 8
            _add_writing_space(doc, blank_count)
            doc.add_paragraph()

        if not is_last:
            _page_break(doc)

    # (끝) — 텍스트 영역(여백 안쪽) 기준 하단 중앙 고정
    p_end = doc.add_paragraph()
    p_end.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_font(p_end.add_run("(끝)"), size=12)
    pPr = p_end._p.get_or_add_pPr()
    frame = OxmlElement("w:framePr")
    frame.set(qn("w:wrap"),    "notBeside")
    frame.set(qn("w:vAnchor"), "margin")   # 텍스트 영역 기준 (여백 안쪽)
    frame.set(qn("w:hAnchor"), "margin")
    frame.set(qn("w:xAlign"),  "center")
    frame.set(qn("w:yAlign"),  "bottom")
    frame.set(qn("w:w"),       "9024")     # A4 텍스트 폭 ≈ 9024 twips
    pPr.append(frame)

    doc.save(output_path)
    print(f"[file_writers] 시험지 저장: {output_path}")


def save_answer_key_docx(qa_pairs: list, output_path: str) -> None:
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    doc = Document()
    sec = doc.sections[0]
    _set_margins(sec)

    hdr = sec.header
    hdr.is_linked_to_previous = False
    p_hdr = hdr.paragraphs[0] if hdr.paragraphs else hdr.add_paragraph()
    p_hdr.clear()
    p_hdr.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _set_font(p_hdr.add_run("모범답안 및 채점기준 — 배포 금지"), size=9)

    ftr = sec.footer
    ftr.is_linked_to_previous = False
    if ftr.paragraphs:
        ftr.paragraphs[0].clear()

    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_title.paragraph_format.space_before = Pt(12)
    p_title.paragraph_format.space_after  = Pt(16)
    _set_font(p_title.add_run("모범답안 및 채점기준"), size=16, bold=True)

    for i, qa in enumerate(qa_pairs, start=1):
        q_type    = qa.get("type", "")
        q_type_ko = TYPE_KO.get(q_type, q_type)
        question  = qa.get("question", "")
        answer    = qa.get("answer",   "")
        rubric    = qa.get("rubric",   "")

        p_num = doc.add_paragraph()
        p_num.paragraph_format.space_before = Pt(16)
        p_num.paragraph_format.space_after  = Pt(4)
        _set_font(p_num.add_run(f"문제 {i}"), size=12, bold=True)
        _set_font(p_num.add_run(f"  ({q_type_ko})"), size=11)

        p_q = doc.add_paragraph()
        p_q.paragraph_format.space_after = Pt(4)
        _set_font(p_q.add_run(question), size=11)

        p_al = doc.add_paragraph()
        p_al.paragraph_format.space_before = Pt(4)
        p_al.paragraph_format.space_after  = Pt(2)
        _set_font(p_al.add_run("▶ 모범답안"), size=11, bold=True)

        p_ans = doc.add_paragraph()
        p_ans.paragraph_format.left_indent = Cm(0.5)
        p_ans.paragraph_format.space_after = Pt(4)
        _set_font(p_ans.add_run(answer), size=11)

        if rubric:
            p_rl = doc.add_paragraph()
            p_rl.paragraph_format.space_before = Pt(4)
            p_rl.paragraph_format.space_after  = Pt(2)
            _set_font(p_rl.add_run("▶ 채점기준"), size=11, bold=True)

            p_rub = doc.add_paragraph()
            p_rub.paragraph_format.left_indent = Cm(0.5)
            p_rub.paragraph_format.space_after = Pt(6)
            _set_font(p_rub.add_run(rubric), size=11)

    doc.save(output_path)
    print(f"[file_writers] 답안지 저장: {output_path}")
