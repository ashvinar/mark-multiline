"""Run the existing offline checks, keeping historical evidence unchanged."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
EXPECTED = "8bfce6857fd2c6e17aa30a94990660190d6dce53668df3b576ea22b76acc323c"
CHECKS = {
    "arm": 17,
    "preservation": 5,
    "camera": 8,
    "queue": 11,
    "motion": 15,
    "fonts": 54,
}


def main():
    payload = (ROOT / "ai-pen.capture-rewrite.experimental.bin").read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != EXPECTED:
        raise SystemExit("Payload differs from the accepted snapshot; review a new build separately.")
    counts = {}
    for name, expected in CHECKS.items():
        subprocess.run([sys.executable, str(ROOT / f"check_{name}.py")], check=True)
        result_name = "font" if name == "fonts" else name
        rows = json.loads((ROOT / f"{result_name}-checks.json").read_text())
        if len(rows) != expected:
            raise SystemExit(f"Unexpected {name} case count: {len(rows)}")
        if name == "fonts":
            passed = all(row["armed"] and row["lift_detected"] for row in rows)
        else:
            passed = all(row["passed"] for row in rows)
        if not passed:
            raise SystemExit(f"Failed {name} checks")
        counts[name] = len(rows)
    result = {
        "application_sha256": digest,
        "checks": counts,
        "total": sum(counts.values()),
        "hardware_contacted": False,
        "historical_evidence_modified": False,
    }
    (ROOT / "verification-local.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
