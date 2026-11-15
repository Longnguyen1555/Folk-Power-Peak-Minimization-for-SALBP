"""Download the official RoundingSAT executable and record its SHA-256.

Source: https://gitlab.com/MIAOresearch/software/roundingsat/-/raw/master/README.md
"""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force", action="store_true", help="Replace an existing local binary"
    )
    args = parser.parse_args()
    if sys.platform == "win32":
        name, job, signature = "roundingsat.exe", "build-windows", b"MZ"
    elif sys.platform.startswith("linux"):
        name, job, signature = "roundingsat", "build-linux", b"\x7fELF"
    else:
        parser.error(
            "Install RoundingSAT manually and set ROUNDINGSAT_BIN on this platform"
        )
    destination = ROOT / "tools/roundingsat" / name
    if destination.exists() and not args.force:
        print(f"Already installed: {destination}")
        return
    url = f"https://gitlab.com/MIAOresearch/software/roundingsat/-/jobs/artifacts/master/raw/build/{name}?job={job}"
    with urllib.request.urlopen(url, timeout=60) as response:
        binary = response.read(50_000_001)
    if len(binary) > 50_000_000 or not binary.startswith(signature):
        parser.error(
            "Downloaded artifact is not the expected executable; no file installed"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(binary)
    if sys.platform != "win32":
        destination.chmod(destination.stat().st_mode | 0o111)
    metadata = {
        "url": url,
        "sha256": hashlib.sha256(binary).hexdigest(),
        "bytes": len(binary),
    }
    destination.with_name("SOURCE.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf8"
    )
    print(f'Installed {destination}; SHA-256 {metadata["sha256"]}')


if __name__ == "__main__":
    main()
