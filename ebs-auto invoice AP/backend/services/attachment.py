"""
attachment.py
Attach PDF file to AP Invoice in Oracle EBS via FND tables.
"""

import oracledb
from config import EBS_USER_ID


def attach_pdf_to_invoice(conn: oracledb.Connection, ap_invoice_id: int, pdf_path: str, filename: str):
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    with conn.cursor() as cur:
        # 1. Get category_id "From Supplier"
        try:
            cur.execute("""
                SELECT category_id FROM fnd_document_categories_tl
                WHERE user_name = 'From Supplier' AND language = USERENV('LANG') AND ROWNUM = 1
            """)
            row = cur.fetchone()
            category_id = row[0] if row else None
        except Exception:
            category_id = None

        if not category_id:
            cur.execute("SELECT category_id FROM fnd_document_categories WHERE name = 'Miscellaneous' AND ROWNUM = 1")
            category_id = cur.fetchone()[0]

        # 2. Get sequences
        cur.execute("SELECT fnd_lobs_s.NEXTVAL FROM DUAL")
        media_id = cur.fetchone()[0]

        cur.execute("SELECT fnd_documents_s.NEXTVAL FROM DUAL")
        document_id = cur.fetchone()[0]

        cur.execute("SELECT fnd_attached_documents_s.NEXTVAL FROM DUAL")
        attached_doc_id = cur.fetchone()[0]

        cur.execute("""
            SELECT NVL(MAX(seq_num), 0) + 10
            FROM fnd_attached_documents
            WHERE entity_name = 'AP_INVOICES' AND pk1_value = :pk1
        """, {"pk1": str(ap_invoice_id)})
        seq_num = cur.fetchone()[0]

        # 3. Insert FND_LOBS — use temporary LOB for reliable BLOB write
        lob = conn.createlob(oracledb.DB_TYPE_BLOB)
        lob.write(pdf_bytes)

        cur.execute("""
            INSERT INTO fnd_lobs (
                file_id, file_name, file_content_type, file_data,
                upload_date, file_format, language, oracle_charset,
                program_name
            ) VALUES (
                :media_id, :filename, 'application/pdf', :file_data,
                SYSDATE, 'binary', 'US', 'UTF8',
                'FNDATTCH'
            )
        """, {
            "media_id":  media_id,
            "filename":  filename,
            "file_data": lob,
        })

        # 4. Insert FND_DOCUMENTS
        cur.execute("""
            INSERT INTO fnd_documents (
                document_id, creation_date, created_by,
                last_update_date, last_updated_by,
                datatype_id, category_id, security_type,
                publish_flag, media_id, usage_type,
                file_name
            ) VALUES (
                :doc_id, SYSDATE, :user_id,
                SYSDATE, :user_id,
                6, :cat_id, 1,
                'Y', :media_id, 'O',
                :filename
            )
        """, {
            "doc_id":   document_id,
            "user_id":  EBS_USER_ID,
            "cat_id":   category_id,
            "media_id": media_id,
            "filename": filename,
        })

        # 5. Insert FND_DOCUMENTS_TL
        cur.execute("""
            INSERT INTO fnd_documents_tl (
                document_id, creation_date, created_by,
                last_update_date, last_updated_by,
                language, source_lang,
                description, file_name, media_id
            ) VALUES (
                :doc_id, SYSDATE, :user_id,
                SYSDATE, :user_id,
                'US', 'US',
                :descr, :filename, :media_id
            )
        """, {
            "doc_id":   document_id,
            "user_id":  EBS_USER_ID,
            "descr":    filename,
            "filename": filename,
            "media_id": media_id,
        })

        # 6. Insert FND_ATTACHED_DOCUMENTS
        cur.execute("""
            INSERT INTO fnd_attached_documents (
                attached_document_id, document_id,
                creation_date, created_by,
                last_update_date, last_updated_by,
                seq_num, entity_name, pk1_value,
                automatically_added_flag
            ) VALUES (
                :att_id, :doc_id,
                SYSDATE, :user_id,
                SYSDATE, :user_id,
                :seq, 'AP_INVOICES', :pk1,
                'N'
            )
        """, {
            "att_id":  attached_doc_id,
            "doc_id":  document_id,
            "user_id": EBS_USER_ID,
            "seq":     seq_num,
            "pk1":     str(ap_invoice_id),
        })

    conn.commit()
