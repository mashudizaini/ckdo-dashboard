"""
Business Plan Setup Service — PAC module.
Stores and retrieves Business Plan Setup documents (Schedule, Guideline, Outlook) in PostgreSQL.
"""
import io
import re
from datetime import datetime, date, timedelta
from typing import Optional
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.responses import StreamingResponse
from app.models.business_plan_setup import PACBusinessPlanSetup
import structlog

logger = structlog.get_logger()

SCHEDULE_DEPTS = [
    ("sales",       "Sales & Marketing"),
    ("development", "Strategic Development"),
    ("plant",        "Plant"),
    ("admin",        "Admin"),
    ("director",     "P. Director"),
]


class BusinessPlanSetupService:

    # ── List ─────────────────────────────────────────────────────────────────

    async def list_setup(
        self,
        db: AsyncSession,
        setup_module: Optional[str] = None,
        plan_year: Optional[int] = None,
    ) -> dict:
        q = select(PACBusinessPlanSetup).order_by(
            PACBusinessPlanSetup.plan_year.desc(),
            PACBusinessPlanSetup.setup_module,
        )
        if setup_module:
            q = q.where(PACBusinessPlanSetup.setup_module == setup_module)
        if plan_year:
            q = q.where(PACBusinessPlanSetup.plan_year == plan_year)

        result = await db.execute(q)
        rows = result.scalars().all()
        return {"success": True, "count": len(rows), "data": [self._to_dict(r) for r in rows]}

    # ── Get single ────────────────────────────────────────────────────────────

    async def get_setup(self, db: AsyncSession, setup_id: int) -> dict:
        row = await db.get(PACBusinessPlanSetup, setup_id)
        if not row:
            return {"success": False, "error": "Not found"}
        return {"success": True, "data": self._to_dict(row)}

    # ── Upsert ───────────────────────────────────────────────────────────────

    async def upsert_setup(self, db: AsyncSession, payload: dict, username: str) -> dict:
        """
        Create or update a Setup document.
        Unique key: setup_module + plan_year.
        """
        setup_id = payload.get("id")
        row = None

        if setup_id:
            row = await db.get(PACBusinessPlanSetup, setup_id)

        if not row:
            q = select(PACBusinessPlanSetup).where(
                PACBusinessPlanSetup.setup_module == payload.get("setup_module"),
                PACBusinessPlanSetup.plan_year  == payload.get("plan_year"),
            )
            result = await db.execute(q)
            row = result.scalar_one_or_none()

        if row:
            row.content    = payload.get("content", row.content)
            row.status     = payload.get("status",     row.status)
            row.updated_at = datetime.utcnow()
        else:
            row = PACBusinessPlanSetup(
                setup_module = payload.get("setup_module", "schedule"),
                plan_year    = payload.get("plan_year", datetime.now().year),
                content      = payload.get("content", {}),
                status       = payload.get("status", "draft"),
                created_by   = username,
            )
            db.add(row)

        await db.flush()
        await db.refresh(row)
        return {"success": True, "data": self._to_dict(row)}

    # ── Export Schedule to Excel ────────────────────────────────────────────────

    async def export_schedule_excel(self, db: AsyncSession, plan_year: int):
        """Build the Business Plan Schedule Excel, mirroring the layout of
        Business plan schedule.xlsx: title block, a 2-row grouped header
        (Submission Date From/To, Actual Date From/To, PIC per department),
        one row per activity with consecutive-run merging on the date
        columns, and green fill for department cells marked "O"."""
        import openpyxl
        from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
        from openpyxl.utils import get_column_letter

        q = select(PACBusinessPlanSetup).where(
            PACBusinessPlanSetup.setup_module == "schedule",
            PACBusinessPlanSetup.plan_year == plan_year,
        )
        result = await db.execute(q)
        row = result.scalar_one_or_none()
        activities = (row.content or {}).get("activities", []) if row else []

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "BP Schedule"

        thin = Side(style="thin", color="000000")
        border = Border(left=thin, right=thin, top=thin, bottom=thin)
        bold = Font(bold=True)
        center = Alignment(horizontal="center", vertical="center", wrap_text=True)
        left_wrap = Alignment(horizontal="left", vertical="center", wrap_text=True)
        green_fill = PatternFill("solid", fgColor="C6EFCE")
        red_fill = PatternFill("solid", fgColor="FFC7CE")
        hdr_fill = PatternFill("solid", fgColor="D9D9D9")
        red_font = Font(color="9C0006", bold=True)

        N_DEPT = len(SCHEDULE_DEPTS)
        COL_NO, COL_ACT = 1, 2
        COL_PRIOR = 3
        COL_SUB_FROM, COL_SUB_TO = 4, 5
        COL_ACT_FROM, COL_ACT_TO = 6, 7
        COL_DAY = 8
        COL_PIC_START = 9
        COL_PIC_END = COL_PIC_START + N_DEPT - 1
        COL_REQ = COL_PIC_END + 1
        COL_NOTES = COL_REQ + 1
        LAST_COL = COL_NOTES

        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=LAST_COL)
        c = ws.cell(row=1, column=1, value="PT CKD OTTO Pharmaceuticals")
        c.font = Font(bold=True, size=12)
        c.alignment = Alignment(horizontal="left")

        ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=LAST_COL - 2)
        c = ws.cell(row=2, column=1, value=f"Timeline & Schedule / Business Plan {plan_year}")
        c.font = bold
        c.alignment = Alignment(horizontal="left")
        ws.merge_cells(start_row=2, start_column=LAST_COL - 1, end_row=2, end_column=LAST_COL)
        c = ws.cell(row=2, column=LAST_COL - 1, value=date.today().strftime("%b %d, %Y"))
        c.alignment = Alignment(horizontal="right")

        HR1, HR2 = 4, 5

        def merge_hdr(c1, c2, value):
            if c1 == c2:
                ws.merge_cells(start_row=HR1, start_column=c1, end_row=HR2, end_column=c2)
            else:
                ws.merge_cells(start_row=HR1, start_column=c1, end_row=HR1, end_column=c2)
            cell = ws.cell(row=HR1, column=c1, value=value)
            cell.font = bold
            cell.alignment = center
            cell.fill = hdr_fill

        merge_hdr(COL_NO, COL_NO, "No")
        merge_hdr(COL_ACT, COL_ACT, "Schedule")
        merge_hdr(COL_PRIOR, COL_PRIOR, f"Submission Date of {plan_year - 1} BP (in {plan_year - 2})")
        merge_hdr(COL_SUB_FROM, COL_SUB_TO, f"Submission Date of {plan_year} BP (in {plan_year - 1})")
        merge_hdr(COL_ACT_FROM, COL_ACT_TO, "Actual Submission Date")
        merge_hdr(COL_DAY, COL_DAY, "Day")
        merge_hdr(COL_PIC_START, COL_PIC_END, "PIC")
        merge_hdr(COL_REQ, COL_REQ, "Requirement (Form)")
        merge_hdr(COL_NOTES, COL_NOTES, "Notes")

        ws.cell(row=HR2, column=COL_SUB_FROM, value="From").font = bold
        ws.cell(row=HR2, column=COL_SUB_TO, value="To").font = bold
        ws.cell(row=HR2, column=COL_ACT_FROM, value="From").font = bold
        ws.cell(row=HR2, column=COL_ACT_TO, value="To").font = bold
        for i, (_, label) in enumerate(SCHEDULE_DEPTS):
            ws.cell(row=HR2, column=COL_PIC_START + i, value=label).font = bold

        for r in (HR1, HR2):
            for col in range(1, LAST_COL + 1):
                cell = ws.cell(row=r, column=col)
                cell.border = border
                cell.fill = hdr_fill
                if cell.alignment.horizontal is None:
                    cell.alignment = center

        def fmt_date(iso):
            if not iso:
                return None
            try:
                return datetime.strptime(iso, "%Y-%m-%d").date()
            except (ValueError, TypeError):
                return None

        def actual_range(departments):
            dates = sorted(
                d.get("date") for d in (departments or {}).values()
                if d.get("status") == "O" and d.get("date")
            )
            return (dates[0] if dates else None, dates[-1] if dates else None)

        def working_days_diff(d1, d2):
            """Signed working-day count over the range (d1, d2]."""
            if not d1 or not d2:
                return None
            sign = 1
            start, end = d1, d2
            if d2 < d1:
                sign, start, end = -1, d2, d1
            count = 0
            cur = start + timedelta(days=1)
            while cur <= end:
                if cur.weekday() < 5:
                    count += 1
                cur += timedelta(days=1)
            return count * sign

        r0 = HR2 + 1
        rows_data = []
        prev_act_to = None
        for act in activities:
            actual_from, actual_to = actual_range(act.get("departments"))
            act_from_d, act_to_d = fmt_date(actual_from), fmt_date(actual_to)
            note = working_days_diff(prev_act_to, act_from_d) if prev_act_to and act_from_d else None
            prev_act_to = act_to_d
            rows_data.append({
                "no": act.get("no"),
                "activity": act.get("activity", ""),
                "prior": fmt_date(act.get("prior_date")),
                "sub_from": fmt_date(act.get("submission_from")),
                "sub_to": fmt_date(act.get("submission_to")),
                "sub_to_iso": act.get("submission_to"),
                "act_from": act_from_d,
                "act_to": act_to_d,
                "act_to_iso": actual_to,
                "day": act.get("day", ""),
                "departments": act.get("departments") or {},
                "remarks": act.get("remarks", ""),
                "notes": note,
            })

        # Merge consecutive rows sharing the same value, mirroring the
        # source file's boxed grouping on the date columns.
        def merge_run(col, keyfn):
            i = 0
            while i < len(rows_data):
                j = i
                while j + 1 < len(rows_data) and keyfn(rows_data[j + 1]) == keyfn(rows_data[i]) and keyfn(rows_data[i]) is not None:
                    j += 1
                if j > i:
                    ws.merge_cells(start_row=r0 + i, start_column=col, end_row=r0 + j, end_column=col)
                i = j + 1

        merge_run(COL_PRIOR, lambda r: r["prior"])

        for r_idx, rd in enumerate(rows_data, start=r0):
            ws.cell(row=r_idx, column=COL_NO, value=rd["no"])
            ws.cell(row=r_idx, column=COL_ACT, value=rd["activity"])
            ws.cell(row=r_idx, column=COL_PRIOR, value=rd["prior"])
            ws.cell(row=r_idx, column=COL_SUB_FROM, value=rd["sub_from"])
            ws.cell(row=r_idx, column=COL_SUB_TO, value=rd["sub_to"])
            ws.cell(row=r_idx, column=COL_ACT_FROM, value=rd["act_from"])
            ws.cell(row=r_idx, column=COL_ACT_TO, value=rd["act_to"])
            ws.cell(row=r_idx, column=COL_DAY, value=rd["day"])
            ws.cell(row=r_idx, column=COL_REQ, value=rd["remarks"])
            ws.cell(row=r_idx, column=COL_NOTES, value=rd["notes"])

            for col in (COL_PRIOR, COL_SUB_FROM, COL_SUB_TO, COL_ACT_FROM, COL_ACT_TO):
                ws.cell(row=r_idx, column=col).number_format = "dd-mmm-yy"

            act_to_cell = ws.cell(row=r_idx, column=COL_ACT_TO)
            if rd["act_to_iso"] and rd["sub_to_iso"] and rd["act_to_iso"] > rd["sub_to_iso"]:
                act_to_cell.font = red_font

            for i, (key, _) in enumerate(SCHEDULE_DEPTS):
                dept = rd["departments"].get(key, {})
                col = COL_PIC_START + i
                cell = ws.cell(row=r_idx, column=col)
                dept_date_iso = dept.get("date")
                is_late = dept.get("status") == "O" and dept_date_iso and rd["sub_to_iso"] and dept_date_iso > rd["sub_to_iso"]
                if dept.get("status") == "O":
                    if dept_date_iso:
                        cell.value = fmt_date(dept_date_iso)
                        cell.number_format = "dd-mmm-yy"
                    else:
                        cell.value = "O"
                    cell.fill = red_fill if is_late else green_fill
                else:
                    cell.value = "X"

            for col in range(1, LAST_COL + 1):
                cell = ws.cell(row=r_idx, column=col)
                cell.border = border
                cell.alignment = left_wrap if col == COL_ACT else center

        widths = {COL_NO: 5, COL_ACT: 42, COL_PRIOR: 13, COL_SUB_FROM: 12, COL_SUB_TO: 12,
                  COL_ACT_FROM: 12, COL_ACT_TO: 12, COL_DAY: 12, COL_REQ: 14, COL_NOTES: 9}
        for i in range(N_DEPT):
            widths[COL_PIC_START + i] = 12
        for col, w in widths.items():
            ws.column_dimensions[get_column_letter(col)].width = w

        ws.page_setup.orientation = "landscape"
        ws.page_setup.fitToWidth = 1
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.freeze_panes = ws.cell(row=r0, column=COL_ACT + 1)

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        filename = f"Business plan schedule {plan_year}.xlsx"
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    # ── Export Guideline to PowerPoint ──────────────────────────────────────────

    async def export_guideline_ppt(self, db: AsyncSession, plan_year: int):
        """Build the Business Plan Guideline as a PPTX, mirroring Business
        plan guideline.xlsx: a title slide, then one table slide per
        section with Current Year ({plan_year}) / Previous Year
        ({plan_year - 1}) columns."""
        from pptx import Presentation
        from pptx.util import Inches, Pt
        from pptx.dml.color import RGBColor
        from pptx.enum.text import PP_ALIGN

        q = select(PACBusinessPlanSetup).where(
            PACBusinessPlanSetup.setup_module == "guideline",
            PACBusinessPlanSetup.plan_year == plan_year,
        )
        result = await db.execute(q)
        row = result.scalar_one_or_none()
        sections = (row.content or {}).get("sections", []) if row else []

        NAVY = RGBColor(0x1F, 0x2A, 0x44)
        TEAL = RGBColor(0x0D, 0x94, 0x88)
        WHITE = RGBColor(0xFF, 0xFF, 0xFF)
        HDR_GREY = RGBColor(0xD9, 0xD9, 0xD9)

        prs = Presentation()
        prs.slide_width = Inches(13.333)
        prs.slide_height = Inches(7.5)
        blank = prs.slide_layouts[6]

        # ── Title slide ──────────────────────────────────────────────────
        slide = prs.slides.add_slide(blank)
        bg = slide.shapes.add_shape(1, 0, 0, prs.slide_width, prs.slide_height)
        bg.fill.solid()
        bg.fill.fore_color.rgb = NAVY
        bg.line.fill.background()
        bg.shadow.inherit = False

        title_box = slide.shapes.add_textbox(Inches(0.8), Inches(2.6), Inches(11.7), Inches(1.2))
        tf = title_box.text_frame
        tf.text = "Business Plan Guideline"
        tf.paragraphs[0].font.size = Pt(40)
        tf.paragraphs[0].font.bold = True
        tf.paragraphs[0].font.color.rgb = WHITE

        sub_box = slide.shapes.add_textbox(Inches(0.8), Inches(3.7), Inches(11.7), Inches(0.8))
        tf = sub_box.text_frame
        tf.text = f"{plan_year} vs {plan_year - 1}"
        tf.paragraphs[0].font.size = Pt(22)
        tf.paragraphs[0].font.color.rgb = TEAL

        company_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.5), Inches(8), Inches(0.6))
        tf = company_box.text_frame
        tf.text = "PT CKD OTTO Pharmaceuticals"
        tf.paragraphs[0].font.size = Pt(16)
        tf.paragraphs[0].font.bold = True
        tf.paragraphs[0].font.color.rgb = WHITE

        # ── One table slide per section ─────────────────────────────────
        for section in sections:
            slide = prs.slides.add_slide(blank)

            head = slide.shapes.add_textbox(Inches(0.5), Inches(0.3), Inches(12.3), Inches(0.7))
            tf = head.text_frame
            tf.text = f"{section.get('icon', '')}  {section.get('title', '')}".strip()
            tf.paragraphs[0].font.size = Pt(26)
            tf.paragraphs[0].font.bold = True
            tf.paragraphs[0].font.color.rgb = NAVY

            items = section.get("items", [])
            n_rows = len(items) + 1
            table_shape = slide.shapes.add_table(n_rows, 3, Inches(0.5), Inches(1.2), Inches(12.3), Inches(5.7))
            table = table_shape.table
            table.columns[0].width = Inches(6.3)
            table.columns[1].width = Inches(3.0)
            table.columns[2].width = Inches(3.0)

            headers = ["", f"Current Year ({plan_year})", f"Previous Year ({plan_year - 1})"]
            for c, htext in enumerate(headers):
                cell = table.cell(0, c)
                cell.text = htext
                cell.fill.solid()
                cell.fill.fore_color.rgb = HDR_GREY
                p = cell.text_frame.paragraphs[0]
                p.font.bold = True
                p.font.size = Pt(14)
                p.alignment = PP_ALIGN.CENTER if c else PP_ALIGN.LEFT

            for r, item in enumerate(items, start=1):
                table.cell(r, 0).text = str(item.get("label", ""))
                table.cell(r, 1).text = str(item.get("current", ""))
                table.cell(r, 2).text = str(item.get("previous", ""))
                for c in range(3):
                    p = table.cell(r, c).text_frame.paragraphs[0]
                    p.font.size = Pt(13)
                    if c:
                        p.alignment = PP_ALIGN.CENTER

        buf = io.BytesIO()
        prs.save(buf)
        buf.seek(0)
        filename = f"Business plan guideline {plan_year}.pptx"
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    async def export_outlook_ppt(self, db: AsyncSession, plan_year: int):
        """Build the Business Plan Outlook as a PPTX — a title slide plus
        one slide per section (Global Economic / Indonesia Economic /
        Pharmaceutical Industry), rendered from each section's free-text
        Markdown content (bullet list, **bold** key terms)."""
        from pptx import Presentation
        from pptx.util import Inches, Pt
        from pptx.dml.color import RGBColor

        q = select(PACBusinessPlanSetup).where(
            PACBusinessPlanSetup.setup_module == "outlook",
            PACBusinessPlanSetup.plan_year == plan_year,
        )
        result = await db.execute(q)
        row = result.scalar_one_or_none()
        content = (row.content or {}) if row else {}

        NAVY = RGBColor(0x1F, 0x2A, 0x44)
        TEAL = RGBColor(0x0D, 0x94, 0x88)
        WHITE = RGBColor(0xFF, 0xFF, 0xFF)

        prs = Presentation()
        prs.slide_width = Inches(13.333)
        prs.slide_height = Inches(7.5)
        blank = prs.slide_layouts[6]

        # ── Title slide ──────────────────────────────────────────────────
        slide = prs.slides.add_slide(blank)
        bg = slide.shapes.add_shape(1, 0, 0, prs.slide_width, prs.slide_height)
        bg.fill.solid()
        bg.fill.fore_color.rgb = NAVY
        bg.line.fill.background()
        bg.shadow.inherit = False

        title_box = slide.shapes.add_textbox(Inches(0.8), Inches(2.6), Inches(11.7), Inches(1.2))
        tf = title_box.text_frame
        tf.text = "Business Plan Outlook"
        tf.paragraphs[0].font.size = Pt(40)
        tf.paragraphs[0].font.bold = True
        tf.paragraphs[0].font.color.rgb = WHITE

        sub_box = slide.shapes.add_textbox(Inches(0.8), Inches(3.7), Inches(11.7), Inches(0.8))
        tf = sub_box.text_frame
        tf.text = f"Economic & Industry Outlook {plan_year}"
        tf.paragraphs[0].font.size = Pt(22)
        tf.paragraphs[0].font.color.rgb = TEAL

        company_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.5), Inches(8), Inches(0.6))
        tf = company_box.text_frame
        tf.text = "PT CKD OTTO Pharmaceuticals"
        tf.paragraphs[0].font.size = Pt(16)
        tf.paragraphs[0].font.bold = True
        tf.paragraphs[0].font.color.rgb = WHITE

        # ── One slide per section ───────────────────────────────────────
        for sec_key in ("global_economic", "indonesia_economic", "pharmaceutical"):
            section = content.get(sec_key) or {}
            slide = prs.slides.add_slide(blank)

            head = slide.shapes.add_textbox(Inches(0.5), Inches(0.3), Inches(12.3), Inches(0.7))
            tf = head.text_frame
            tf.text = section.get("title", "")
            tf.paragraphs[0].font.size = Pt(26)
            tf.paragraphs[0].font.bold = True
            tf.paragraphs[0].font.color.rgb = NAVY

            body_box = slide.shapes.add_textbox(Inches(0.7), Inches(1.3), Inches(11.9), Inches(5.8))
            body_tf = body_box.text_frame
            body_tf.word_wrap = True

            lines = [ln.strip() for ln in (section.get("text") or "").split("\n") if ln.strip()]
            for i, line in enumerate(lines):
                bullet_text = re.sub(r"^[-*]\s+", "", line)
                p = body_tf.paragraphs[0] if i == 0 else body_tf.add_paragraph()
                p.space_after = Pt(8)
                parts = re.split(r"(\*\*[^*]+\*\*)", bullet_text)
                first_run = True
                for part in parts:
                    if not part:
                        continue
                    is_bold = part.startswith("**") and part.endswith("**")
                    run_text = part[2:-2] if is_bold else part
                    if first_run:
                        run_text = "•  " + run_text
                        first_run = False
                    run = p.add_run()
                    run.text = run_text
                    run.font.size = Pt(16)
                    run.font.bold = is_bold
                    run.font.color.rgb = NAVY

        buf = io.BytesIO()
        prs.save(buf)
        buf.seek(0)
        filename = f"Business plan outlook {plan_year}.pptx"
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    # ── Delete ────────────────────────────────────────────────────────────────

    async def delete_setup(self, db: AsyncSession, setup_id: int) -> dict:
        row = await db.get(PACBusinessPlanSetup, setup_id)
        if not row:
            return {"success": False, "error": "Not found"}
        await db.execute(delete(PACBusinessPlanSetup).where(PACBusinessPlanSetup.id == setup_id))
        return {"success": True, "message": f"Deleted setup #{setup_id}"}

    # ── Helper ────────────────────────────────────────────────────────────────

    def _to_dict(self, row: PACBusinessPlanSetup) -> dict:
        return {
            "id":          row.id,
            "setup_module": row.setup_module,
            "plan_year":   row.plan_year,
            "content":     row.content,
            "status":      row.status,
            "created_at":  row.created_at.isoformat() if row.created_at else None,
            "updated_at":  row.updated_at.isoformat() if row.updated_at else None,
            "created_by":  row.created_by,
        }
