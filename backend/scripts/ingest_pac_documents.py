"""
Import a PAC document folder (e.g. "01.Loan") into the Knowledge Base, so
CoChat's Company Rules assistant can answer from it — PDFs (OCR for scanned
pages), xlsx and txt, one document per unique file, tagged PAC. See
app/services/pac_documents_kb.py for naming, formats and why.

Resumable: a file whose (source, title) is already in the Knowledge Base is
skipped, so an interrupted run (OCR of a few hundred scanned pages takes a
while) just continues when started again. --replace re-imports those too;
--prune also removes documents under this label whose file is gone.

Copy the folder into the backend container, then run (in the background —
an SSH drop must not kill it, and never from the Server Control terminal,
which lives inside ckdo_backend):

    docker cp "01.Loan" ckdo_backend:/tmp/pac_loan
    docker exec ckdo_backend python scripts/ingest_pac_documents.py /tmp/pac_loan --label Loan --dry-run
    docker exec -d ckdo_backend sh -c 'python scripts/ingest_pac_documents.py /tmp/pac_loan --label Loan > /tmp/pac_loan.log 2>&1'
    docker exec ckdo_backend tail -f /tmp/pac_loan.log

Only callers whose EBS Chat Access row includes the PAC knowledge tag can
retrieve these documents.
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from app.services import pac_documents_kb, rag_service  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", help="Folder to import")
    ap.add_argument("--label", required=True, help='Name used in the source, e.g. "Loan"')
    ap.add_argument("--department", default="PAC", choices=rag_service.DEPARTMENTS)
    ap.add_argument("--created-by", default="pac-documents-import")
    ap.add_argument("--dry-run", action="store_true", help="Scan and report only; no OCR, writes nothing")
    ap.add_argument("--out", help="With --dry-run: also extract (no OCR) and write the text here for review")
    ap.add_argument("--replace", action="store_true", help="Re-import files already in the Knowledge Base")
    ap.add_argument("--prune", action="store_true", help="Remove documents under this label whose file is gone")
    args = ap.parse_args()

    files, skipped = pac_documents_kb.scan_folder(args.folder)
    copies = sum(len(f["copies"]) for f in files)
    print(f"== {args.folder}: {len(files)} unique file(s) to import, {copies} duplicate copies, "
          f"{len(skipped)} skipped", flush=True)
    for rel in skipped:
        print(f"   skip  {rel}")

    label_prefix = pac_documents_kb.SOURCE_PREFIX + args.label
    planned = {pac_documents_kb.source_and_title(args.label, f["rel"]) for f in files}

    if args.dry_run:
        for src in sorted({s for s, _ in planned}):
            print(f"   source '{src}': {sum(1 for s, _ in planned if s == src)} file(s)")
        if args.out:
            os.makedirs(args.out, exist_ok=True)
            out = os.path.join(args.out, f"pac_doc_{args.label}.md")
            with open(out, "w", encoding="utf-8") as fh:
                for f in files:
                    d = pac_documents_kb.file_document(args.label, f, ocr=False)
                    fh.write(f"\n\n######## {d['source']} :: {d['title']}  "
                             f"({d['kind']}, {d['pages']} pg, {len(d['text']):,} chars)\n\n{d['text']}")
            print(f"   written {out}")
        return 0

    existing = {(d["source"], d["title"]) for d in rag_service.list_documents()
                if d["source"] == label_prefix or d["source"].startswith(label_prefix + " - ")}

    if args.prune:
        for source, title in sorted(existing - planned):
            n = rag_service.delete_document(source, title)
            print(f"   - pruned {source} :: {title} ({n} chunks)", flush=True)

    done = skipped_existing = empty = failed = chunks = 0
    started = time.time()
    for i, f in enumerate(files, 1):
        source, title = pac_documents_kb.source_and_title(args.label, f["rel"])
        if (source, title) in existing and not args.replace:
            skipped_existing += 1
            continue
        t = time.time()
        try:
            d = pac_documents_kb.file_document(args.label, f, ocr=True)
            if not d["text"]:
                empty += 1
                print(f"[{i}/{len(files)}] ! no text: {f['rel']}", flush=True)
                continue
            if (source, title) in existing:
                rag_service.delete_document(source, title)
            # OCR output loses paragraph structure — same chunking as the
            # Knowledge Base upload uses for scanned PDFs.
            kw = {"chunk_size": 1500, "overlap": 200, "line_aware": True} if d["ocr_pages"] else {}
            ids = rag_service.ingest_text(source, title, d["text"], args.created_by,
                                          department=args.department, from_file=True,
                                          file_name=os.path.basename(f["rel"]), **kw)
            chunks += len(ids)
            done += 1
            ocr = f", OCR {d['ocr_pages']}/{d['pages']} pg" if d["ocr_pages"] else ""
            print(f"[{i}/{len(files)}] + {f['rel']}: {len(ids)} chunks{ocr} ({time.time() - t:.0f}s)", flush=True)
        except Exception as e:
            failed += 1
            print(f"[{i}/{len(files)}] !! {f['rel']}: {type(e).__name__}: {e}", flush=True)

    print(f"== done in {(time.time() - started) / 60:.1f} min: {done} imported ({chunks} chunks), "
          f"{skipped_existing} already present, {empty} without text, {failed} failed", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
