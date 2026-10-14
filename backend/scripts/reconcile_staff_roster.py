"""Offline inputs only: no database, network, credentials, or write API.

Usage (from repository root):
  python backend/scripts/reconcile_staff_roster.py --snapshot PATH --output PATH
Requires pdfplumber in the operator's local document-review environment only.
Snapshot is an already authorized local JSON list (or {"employees": [...]});
it is not exported by this tool. Output deliberately omits names/emails/phones.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.roster_reconciliation import reconcile_roster


def read_team_reference(path):
    import pdfplumber
    headings = {"Leadership": "Leadership", "Valuation": "Valuation", "Account": "Account Management",
                "Operations": "Operations", "IT": "IT Support", "Human": "Human Resources"}
    entries, department = [], None
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages[:2]:
            words = page.extract_words()
            headers = [(w["top"], headings[w["text"]]) for w in words
                       if 55 <= w["x0"] < 60 and w["text"] in headings]
            emails = sorted((w for w in words if 250 <= w["x0"] < 455 and "@" in w["text"]), key=lambda w: w["top"])
            for index, word in enumerate(emails):
                top = word["top"] - 0.5
                prior = [(y, d) for y, d in headers if y <= top]
                if prior: department = max(prior)[1]
                end = emails[index + 1]["top"] - 0.5 if index + 1 < len(emails) else (780 if page.page_number == 1 else 515)
                end = min([end] + [y for y, _ in headers if y > top])
                cells = [w for w in words if top <= w["top"] < end]
                name = " ".join(w["text"] for w in cells if 55 <= w["x0"] < 155)
                role = " ".join(w["text"] for w in cells if 155 <= w["x0"] < 251)
                entries.append({"full_name": name, "role_title": role, "department": department,
                                "work_emails": word["text"].split("/")})
    if len(entries) != 21 or any(not e["full_name"] or not e["department"] for e in entries):
        raise ValueError("Reference layout/count not recognized; obtain an HR-reviewed reference JSON instead")
    return entries


def read_brief_review_flags(path):
    import pdfplumber
    with pdfplumber.open(path) as pdf:
        text = " ".join((pdf.pages[-1].extract_text() or "").split())
    demo = re.search(r"record \(do not delete\)\. (.*?) [—-] remove as demo data", text)
    exited = re.search(r"In the live system but not in the directory: (.*?) \(", text)
    if not demo or not exited:
        raise ValueError("Brief reconciliation flags need manual review")
    return re.split(r",\s*|\s+and\s+", demo.group(1)), [exited.group(1)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reference-dir", type=Path, default=Path("docs/reference"))
    args = parser.parse_args()
    briefs = list(args.reference_dir.glob("*Developer Brief*v1.pdf"))
    if len(briefs) != 1: parser.error("One Developer Brief v1 PDF is required")
    try:
        reference = read_team_reference(args.reference_dir / "Solvit Team Directory - 2026.pdf")
        demo, exited = read_brief_review_flags(briefs[0])
        snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
        records = snapshot.get("employees") if isinstance(snapshot, dict) else snapshot
        if not isinstance(records, list) or any(not isinstance(r, dict) for r in records):
            raise ValueError("Snapshot must be a JSON employee list")
        protected = [args.snapshot.resolve(), *(p.resolve() for p in args.reference_dir.glob("*"))]
        if args.output.resolve() in protected or args.output.exists():
            raise ValueError("Output must be a new file; input/reference files cannot be overwritten")
        departments = ["Leadership", "Valuation", "Account Management", "Operations", "IT Support", "Human Resources"]
        report = reconcile_roster(records, reference, departments, demo, exited)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2)
        print("Read-only reconciliation report written; no records were changed.")
    except (ValueError, OSError, ImportError):
        parser.exit(1, "Reconciliation failed. Verify local inputs, PDF layout and optional pdfplumber availability; no records changed.\n")


if __name__ == "__main__":
    main()
