"""Generate the deterministic Stage 2B snapshot bundle attestation."""

from __future__ import annotations

import argparse
from pathlib import Path

from compute_stage2b_metrics import generate_snapshot_attestation


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    generate_snapshot_attestation(args.manifest, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
