"""
Sales Plan Service
Handles CRUD for sales plan inputs and Excel export (S1 Value / S2 Unit)
"""
import os
import json
from datetime import datetime
from typing import Optional
from sqlalchemy import select, delete, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.sales_plan import SalesPlan, SalesPlanHistory
import structlog

logger = structlog.get_logger()

EXPORT_DIR = "/tmp/sales_plan_exports"
os.makedirs(EXPORT_DIR, exist_ok=True)


class SalesPlanService:

    async def list_sales_plans(
        self,
        db: AsyncSession,
        plan_year: Optional[int] = None,
        department: Optional[str] = None,
        team_code: Optional[str] = None,
        plan_type: Optional[str] = None,
    ) -> dict:
        q = select(SalesPlan).order_by(SalesPlan.plan_year.desc(), SalesPlan.department, SalesPlan.team_code)
        if plan_year:
            q = q.where(SalesPlan.plan_year == plan_year)
        if department:
            q = q.where(SalesPlan.department == department)
        if team_code:
            q = q.where(SalesPlan.team_code == team_code)
        if plan_type:
            q = q.where(SalesPlan.plan_type == plan_type)
        result = await db.execute(q)
        rows = result.scalars().all()
        return {"success": True, "count": len(rows), "data": [self._to_dict(r) for r in rows]}

    async def get_sales_plan(self, db: AsyncSession, plan_id: int) -> dict:
        row = await db.get(SalesPlan, plan_id)
        if not row:
            return {"success": False, "error": "Not found"}
        return {"success": True, "data": self._to_dict(row)}

    async def upsert_sales_plan(self, db: AsyncSession, payload: dict, username: str) -> dict:
        plan_id = payload.get("id")
        row = None
        if plan_id:
            row = await db.get(SalesPlan, plan_id)
        if not row:
            q = select(SalesPlan).where(
                SalesPlan.plan_year  == payload.get("plan_year"),
                SalesPlan.department == payload.get("department", ""),
                SalesPlan.team_code  == payload.get("team_code", ""),
                SalesPlan.plan_type  == payload.get("plan_type", "value"),
            )
            result = await db.execute(q)
            row = result.scalar_one_or_none()
        if row:
            row.content   = payload.get("content", row.content)
            row.status    = payload.get("status",  row.status)
            row.updated_at = datetime.utcnow()
        else:
            row = SalesPlan(
                plan_year  = payload.get("plan_year", datetime.now().year),
                department = payload.get("department", ""),
                team_code  = payload.get("team_code", ""),
                team_name  = payload.get("team_name", ""),
                plan_type  = payload.get("plan_type", "value"),
                content    = payload.get("content", {}),
                status     = payload.get("status", "draft"),
                created_by = username,
            )
            db.add(row)
        await db.flush()
        await db.refresh(row)
        return {"success": True, "data": self._to_dict(row)}

    async def delete_sales_plan(self, db: AsyncSession, plan_id: int) -> dict:
        row = await db.get(SalesPlan, plan_id)
        if not row:
            return {"success": False, "error": "Not found"}
        await db.execute(delete(SalesPlan).where(SalesPlan.id == plan_id))
        return {"success": True, "message": f"Deleted sales plan #{plan_id}"}

    async def export_excel(self, db: AsyncSession, plan_id: int, plan_type: str, username: str) -> dict:
        row = await db.get(SalesPlan, plan_id)
        if not row:
            return {"success": False, "error": "Sales plan not found"}
        if row.plan_type != plan_type:
            return {"success": False, "error": f"Plan type mismatch: {row.plan_type} vs {plan_type}"}
        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        except ImportError:
            return {"success": False, "error": "openpyxl not installed"}

        content = row.content or {}
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = f"S{1 if plan_type == 'value' else 2} Sales Plan"

        # Styles
        header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True, size=11)
        sub_fill    = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
        sub_font    = Font(bold=True, size=10)
        thin_border = Border(
            left=Side(style='thin', color='000000'),
            right=Side(style='thin', color='000000'),
            top=Side(style='thin', color='000000'),
            bottom=Side(style='thin', color='000000'),
        )

        # Title
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=15)
        ws.cell(row=1, column=1, value=f"PT CKD OTTO Pharmaceuticals — Sales Plan {plan_type.title()} {row.plan_year}")
        ws.cell(row=1, column=1).font = Font(bold=True, size=14, color="1F4E78")
        ws.cell(row=1, column=1).alignment = Alignment(horizontal="center")

        ws.cell(row=2, column=1, value=f"Department: {row.department}  |  Team: {row.team_code} / {row.team_name}")
        ws.cell(row=2, column=1).font = Font(italic=True, size=10)
        ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=15)

        rows_data = content.get("rows", [])
        headers = content.get("headers", [
            "No", "Product / Description", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Total"
        ])

        # Header row
        for col_idx, hdr in enumerate(headers, 1):
            cell = ws.cell(row=4, column=col_idx, value=hdr)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = thin_border

        # Data rows
        for r_idx, row_data in enumerate(rows_data, 5):
            for c_idx, val in enumerate(row_data, 1):
                cell = ws.cell(row=r_idx, column=c_idx, value=val)
                cell.border = thin_border
                cell.alignment = Alignment(horizontal="center" if c_idx > 2 else "left", vertical="center")
                if c_idx > 2 and isinstance(val, (int, float)):
                    cell.number_format = '#,##0'

        # Auto-width
        for col in ws.columns:
            max_length = 0
            column = col[0].column_letter
            for cell in col:
                try:
                    if cell.value:
                        max_length = max(max_length, len(str(cell.value)))
                except:
                    pass
            ws.column_dimensions[column].width = min(max_length + 2, 30)

        filename = f"(S{1 if plan_type == 'value' else 2}) Sales Plan_{plan_type.title()}_{row.plan_year}_{row.team_code or 'ALL'}.xlsx"
        filepath = os.path.join(EXPORT_DIR, filename)
        wb.save(filepath)

        history = SalesPlanHistory(
            sales_plan_id = row.id,
            plan_type     = plan_type,
            filename      = filename,
            file_path     = filepath,
            generated_by  = username,
        )
        db.add(history)
        await db.commit()
        await db.refresh(history)

        return {
            "success": True,
            "filename": filename,
            "file_path": filepath,
            "history_id": history.id,
        }

    def _to_dict(self, row: SalesPlan) -> dict:
        return {
            "id":         row.id,
            "plan_year":  row.plan_year,
            "department": row.department,
            "team_code":  row.team_code,
            "team_name":  row.team_name,
            "plan_type":  row.plan_type,
            "content":    row.content,
            "status":     row.status,
            "created_by": row.created_by,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
