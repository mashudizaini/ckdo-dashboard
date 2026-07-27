"""
Meeting Notes Service
─────────────────────────────────────────
Transcription runs on the remote GPU Whisper service on the "ai-engine" VM
(172.21.2.27:9500 — faster-whisper large-v3, systemd unit
whisper-server.service) instead of running faster-whisper in-process on the
backend's CPU — ~17x realtime on that box's RTX 5060 Ti, so a 1-2 hour
meeting transcribes in a few minutes instead of potentially longer than the
meeting itself. See app/config.py's whisper_api_url comment. Transcription
itself has no Claude alternative — the Anthropic API has no audio input
capability — so it always runs on-premise regardless of provider choice.

MOM generation is dual-provider like CV Screening / JD Generator / AP
Invoice OCR: "onprem" (default, local Ollama qwen2.5 — free) or "anthropic"
(opt-in, Claude — see app/config.py's anthropic_api_key comment).

MOM schema (departments -> topics -> discussion_points + action_plans) and
the rendered DOCX layout match the company's previous meeting-notes tool
(sumber/CKDO_DASHBOARD/apps/meeting_notes_app) for continuity with the
format staff are already used to — see build_mom_docx().
"""
import json
import re
import io
import httpx
import anthropic
from docx import Document
from docx.shared import Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from app.config import get_settings
import structlog

logger = structlog.get_logger()
settings = get_settings()

OLLAMA_MOM_TIMEOUT_SECONDS = 120.0

# Generous margin — ~17x realtime measured on the ai-engine GPU means a 2h
# meeting takes ~7 minutes to transcribe, but a large upload + network hop
# deserves headroom over the bare compute time.
TRANSCRIBE_TIMEOUT_SECONDS = 1800.0

MOM_PROMPT_TEMPLATE = """Analisis transkrip rapat berikut dan buatkan ringkasan terstruktur dalam format JSON.

{meta}Transkrip rapat:
\"\"\"
{transcript}
\"\"\"

ATURAN:
- Organisasikan berdasarkan departemen/topik utama yang benar-benar dibahas dalam transkrip (misal: IT, HR, Finance, Marketing, Produksi, dst — jangan mengarang departemen yang tidak disebut).
- Setiap topik punya discussion_points (poin pembahasan) dan action_plans (rencana tindakan). Untuk action_plans, sertakan PIC dan deadline jika disebutkan, format: "tindakan - oleh Nama (deadline)". Kalau tidak ada rencana tindakan untuk topik itu, kembalikan array kosong.
- Gunakan bahasa formal, abaikan basa-basi/obrolan yang tidak substantif.
- Balas dalam bahasa yang SAMA dengan bahasa dominan transkrip (transkrip Bahasa Indonesia → JSON Bahasa Indonesia; transkrip Bahasa Inggris → JSON Bahasa Inggris).
- Jangan mengarang informasi yang tidak ada di transkrip.

Balas HANYA dengan JSON valid (tanpa markdown code fence, tanpa teks lain), struktur PERSIS seperti ini:
{{
  "departments": [
    {{
      "name": "Nama Departemen/Topik",
      "topics": [
        {{
          "title": "Judul topik",
          "discussion_points": ["poin 1", "poin 2"],
          "action_plans": ["tindakan - oleh Nama (deadline)"]
        }}
      ]
    }}
  ]
}}
"""


class MeetingNotesService:

    async def transcribe(self, file_bytes: bytes, filename: str, language: str | None = None) -> dict:
        """Upload audio to the remote GPU Whisper service, return the
        transcript + segments. Raises httpx.HTTPStatusError / TimeoutException
        on failure — the router translates these into a clean error response."""
        url = f"{settings.whisper_api_url.rstrip('/')}/transcribe"
        files = {"file": (filename, file_bytes)}
        data = {"language": language} if language else {}
        async with httpx.AsyncClient(timeout=TRANSCRIBE_TIMEOUT_SECONDS) as client:
            resp = await client.post(url, files=files, data=data)
            resp.raise_for_status()
            return resp.json()

    def generate_mom(self, transcript: str, meeting_title: str = "", participants: str = "", provider: str = "onprem") -> dict:
        """Transcript -> {"departments": [...]}. provider: "onprem" (default, local Ollama) or "anthropic" (Claude)."""
        meta_lines = []
        if meeting_title:
            meta_lines.append(f"Judul rapat: {meeting_title}")
        if participants:
            meta_lines.append(f"Peserta: {participants}")
        meta = ("\n".join(meta_lines) + "\n\n") if meta_lines else ""

        prompt = MOM_PROMPT_TEMPLATE.format(meta=meta, transcript=transcript)

        if provider == "anthropic":
            client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
            response = client.messages.create(
                model="claude-opus-4-8",
                max_tokens=4000,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text.strip()
        else:
            resp = httpx.post(
                f"{settings.ollama_api_url.rstrip('/')}/api/chat",
                json={"model": settings.ollama_chat_model, "messages": [{"role": "user", "content": prompt}], "stream": False},
                timeout=OLLAMA_MOM_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            raw = resp.json()["message"]["content"].strip()

        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        return json.loads(raw)

    def build_mom_docx(self, mom_json: dict, meeting_title: str, participants: str, meta: dict) -> bytes:
        """Renders the (possibly user-edited) MOM structure into a .docx,
        matching sumber/CKDO_DASHBOARD's layout: centered bold underlined
        header, Date/Time/Venue lines, a numbered participants table, Agenda,
        then per-department numbered topics with bold "Discussion Points" /
        "Action Plan" sub-headers and bullet lists."""
        doc = Document()

        section = doc.sections[0]
        section.top_margin = Cm(2)
        section.bottom_margin = Cm(2)
        section.left_margin = Cm(2.5)
        section.right_margin = Cm(2.5)

        style = doc.styles["Normal"]
        style.font.name = "Arial"
        style.font.size = Pt(11)

        header = doc.add_paragraph()
        header.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = header.add_run(f"PT CKD OTTO Pharmaceuticals Minutes of Meeting - {meeting_title or 'Meeting'}")
        run.bold = True
        run.underline = True
        run.font.size = Pt(12)

        doc.add_paragraph(f"Date : {meta.get('date', '')}")
        doc.add_paragraph(f"Time : {meta.get('time', '')}")
        doc.add_paragraph(f"Venue : {meta.get('venue', '')}")

        names = [n.strip() for n in (participants or "").split(",") if n.strip()]
        if names:
            doc.add_paragraph("Participants :")
            rows = (len(names) + 1) // 2
            table = doc.add_table(rows=rows, cols=2)
            for i, name in enumerate(names):
                cell = table.cell(i // 2, i % 2)
                cell.text = f"{i + 1}. {name}"

        if meta.get("agenda"):
            doc.add_paragraph(f"Agenda : {meta['agenda']}")

        doc.add_paragraph()
        marker = doc.add_paragraph()
        marker.alignment = WD_ALIGN_PARAGRAPH.CENTER
        marker.add_run("[ Discussed matters ]").bold = True
        doc.add_paragraph()

        for dept in mom_json.get("departments", []):
            dept_p = doc.add_paragraph()
            dept_p.add_run((dept.get("name") or "").upper()).bold = True

            for i, topic in enumerate(dept.get("topics", []), start=1):
                topic_p = doc.add_paragraph()
                topic_p.add_run(f"{i}. {topic.get('title', '')}").bold = True

                points = topic.get("discussion_points") or []
                if points:
                    doc.add_paragraph("Discussion Points").runs[0].bold = True
                    for point in points:
                        doc.add_paragraph(point, style="List Bullet")

                actions = topic.get("action_plans") or []
                if actions:
                    doc.add_paragraph("Action Plan").runs[0].bold = True
                    for action in actions:
                        doc.add_paragraph(action, style="List Bullet")

            doc.add_paragraph()

        buf = io.BytesIO()
        doc.save(buf)
        return buf.getvalue()
