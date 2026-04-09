#!/usr/bin/env python3
"""Pre-commit hook: Sacred Zone Integrity Check
Ensures sacred zones in genesis-managed files are not accidentally modified.
"""
import subprocess
import sys
from pathlib import Path

# Add repo root to path so we can import genesis
_REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT))

SACRED_ZONE_OPEN = "# <<<SACRED_ZONE_BEGIN>>>"
GENESIS_MANAGED_PATTERN = "# genesis-managed: true"


def get_staged_content(filepath: str) -> str:
    result = subprocess.run(
        ["git", "show", f":{filepath}"],
        capture_output=True, text=True
    )
    return result.stdout


def get_head_content(filepath: str) -> str:
    result = subprocess.run(
        ["git", "show", f"HEAD:{filepath}"],
        capture_output=True, text=True
    )
    return result.stdout


def check_file(filepath: str) -> bool:
    staged = get_staged_content(filepath)
    if GENESIS_MANAGED_PATTERN not in staged:
        return True  # Not a genesis-managed file, skip

    head = get_head_content(filepath)
    if not head:
        return True  # New file, nothing to compare

    from genesis import SacredZonePreserver
    preserver = SacredZonePreserver()
    head_zones = preserver.extract(head)
    staged_zones = preserver.extract(staged)

    violations = []
    for zone_name, zone_content in head_zones.items():
        if zone_name in staged_zones:
            if staged_zones[zone_name].strip() != zone_content.strip():
                violations.append(zone_name)

    if violations:
        print(f"\u274c Sacred zone violation in {filepath}:")
        for v in violations:
            print(f"   Zone '{v}' has been modified")
        print("   Use 'python genesis.py regen' to update generated sections.")
        return False

    return True


def main():
    files = sys.argv[1:]
    failed = False
    for f in files:
        if not check_file(f):
            failed = True
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
