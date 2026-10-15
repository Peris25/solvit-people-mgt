"""Offline named manager verification using supplied PDFs, confirmations and JSON.

No database or network connection. Outputs must stay in ignored integrity-reports.
Optional pdfplumber dependency belongs to the local document-review environment.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.reconcile_staff_roster import read_team_reference
from utils.reporting_verification import verify_reporting


def read_solver_reference(path):
    import pdfplumber
    regions = ("Nairobi Metropolitan", "Central & Mt Kenya", "Lower Eastern", "Coast", "Rift Valley",
               "Western & Nyanza", "North Eastern", "Area to be confirmed")
    records, region = [], None
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            header = next(w["top"] for w in words if w["text"] == "Phone" and w["x0"] > 425)
            groups = []
            for word in sorted((w for w in words if header + 10 < w["top"] < 790), key=lambda w: (w["top"], w["x0"])):
                if not groups or abs(groups[-1][0] - word["top"]) > 2: groups.append((word["top"], []))
                groups[-1][1].append(word)
            for _, group in groups:
                group = sorted(group, key=lambda w: w["x0"])
                line = " ".join(w["text"] for w in group)
                heading = next((r for r in regions if line.startswith(r)), None)
                if heading: region = heading; continue
                name = " ".join(w["text"] for w in group if w["x0"] < 220)
                if name and region:
                    records.append({"full_name": name, "region": region,
                                    "area": " ".join(w["text"] for w in group if 220 <= w["x0"] < 425),
                                    "phone_present": any(w["x0"] >= 425 for w in group)})
    if not records or len({r["full_name"] for r in records}) != len(records):
        raise ValueError("Solver reference requires manual layout/duplicate review")
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--confirmations", type=Path, default=Path("docs/reference/hr-reporting-confirmations.json"))
    parser.add_argument("--reference-dir", type=Path, default=Path("docs/reference"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        allowed = (Path(__file__).resolve().parents[2] / "integrity-reports").resolve()
        target = args.output.resolve()
        if not target.is_relative_to(allowed) or target == allowed or target.exists():
            raise ValueError("Output must be a new private integrity-reports file")
        protected = [args.snapshot.resolve(), args.confirmations.resolve(), *(p.resolve() for p in args.reference_dir.glob("*"))]
        if target in protected: raise ValueError("Input/reference overwrite is prohibited")
        snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
        if not isinstance(snapshot, dict) or any(not isinstance(snapshot.get(k), list) or any(not isinstance(r, dict) for r in snapshot[k]) for k in ("employees", "solvers")):
            raise ValueError("Snapshot must contain employees and solvers record arrays")
        confirmations = json.loads(args.confirmations.read_text(encoding="utf-8"))
        if not isinstance(confirmations, dict) or any(not isinstance(confirmations.get(k, {}), dict) or any(
            not isinstance(key, str) or not isinstance(value, str) for key, value in confirmations.get(k, {}).items())
            for k in ("role_holders", "title_overrides")):
            raise ValueError("HR confirmations must use string role/name mappings")
        reference = read_team_reference(args.reference_dir / "Solvit Team Directory - 2026.pdf")
        solver_reference = read_solver_reference(args.reference_dir / "Solvit Solver Directory - September 2026.pdf")
        result = verify_reporting(snapshot["employees"], snapshot["solvers"], reference, solver_reference, confirmations)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf-8") as stream: json.dump(result, stream, indent=2)
        print("Private read-only reporting verification written. No records changed.")
    except (ValueError, OSError, ImportError, StopIteration, TypeError, KeyError):
        parser.exit(1, "Verification failed; review local inputs/reference layout. No records changed.\n")


if __name__ == "__main__":
    main()
