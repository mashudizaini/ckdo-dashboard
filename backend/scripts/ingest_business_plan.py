"""
Import PAC's "<year> Business plan.xlsx" into the Knowledge Base, so CoChat's
Company Rules assistant (search_company_documents) can answer from it.

Each body sheet (before "Appendix→") becomes one document under source
"Business Plan <year>", tagged PAC — see app/services/business_plan_kb.py for
the conversion and why. Re-running for a year replaces that year's documents
(all existing "Business Plan <year>" entries are deleted first), so a revised
workbook can simply be imported again.

Copy the workbook into the backend container, then run:

    docker cp "2026 Business plan.xlsx" ckdo_backend:/tmp/
    docker exec ckdo_backend python scripts/ingest_business_plan.py "/tmp/2026 Business plan.xlsx" --dry-run
    docker exec ckdo_backend python scripts/ingest_business_plan.py "/tmp/2026 Business plan.xlsx"

The year comes from the file name; pass --year when it doesn't contain one.
Only callers whose EBS Chat Access row includes the PAC knowledge tag can
retrieve these documents.
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from app.services import business_plan_kb, rag_service  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", help="Business plan .xlsx file(s)")
    ap.add_argument("--year", type=int, help="Plan year (default: taken from the file name)")
    ap.add_argument("--department", default="PAC", choices=rag_service.DEPARTMENTS)
    ap.add_argument("--created-by", default="business-plan-import")
    ap.add_argument("--dry-run", action="store_true", help="Convert and report only; write nothing")
    ap.add_argument("--out", help="With --dry-run: write each year's converted text to this folder for review")
    args = ap.parse_args()

    if args.year and len(args.files) > 1:
        ap.error("--year only makes sense with a single file")

    for path in args.files:
        name = os.path.basename(path)
        year = args.year or business_plan_kb.year_from_filename(name)
        if not year:
            print(f"!! {name}: no year in the file name — pass --year")
            return 2
        source = business_plan_kb.source_for_year(year)
        docs = business_plan_kb.workbook_documents(path, year)
        print(f"== {name} -> source '{source}', {len(docs)} sheet(s), tag {args.department}")
        for d in docs:
            print(f"   {d['sheet']:<34} {len(d['text']):>7,} chars  {d['title']}")

        if args.dry_run:
            if args.out:
                os.makedirs(args.out, exist_ok=True)
                out = os.path.join(args.out, f"business_plan_{year}.md")
                with open(out, "w", encoding="utf-8") as f:
                    for d in docs:
                        f.write(f"\n\n######## {d['title']}  [{d['sheet']}]\n\n{d['text']}")
                print(f"   written {out}")
            continue

        existing = [d for d in rag_service.list_documents() if d["source"] == source]
        for d in existing:
            n = rag_service.delete_document(d["source"], d["title"])
            print(f"   - removed old '{d['title']}' ({n} chunks)")

        total = 0
        for d in docs:
            t = time.time()
            ids = rag_service.ingest_text(source, d["title"], d["text"], args.created_by,
                                          department=args.department, from_file=True, file_name=name)
            total += len(ids)
            print(f"   + {d['title']}: {len(ids)} chunks ({time.time() - t:.0f}s)")
        print(f"   done: {total} chunks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
