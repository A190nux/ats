"""backend.parse.dedupe

Simple deduplication utility for parsed CV JSON files.

Behavior
- Identify duplicates by normalized email or normalized phone.
- When duplicates are found, keep the most recently-modified file and move
  older duplicates into a `duplicates/` subfolder under the parsed directory
  (safe rollback).
- Provide `run_dedupe(parsed_dir, recent_files=None, dry_run=False)` for programmatic use
  and a small CLI for manual runs.

This module is intentionally small and dependency-free so it works in the
existing environment without extra packages.
"""
from __future__ import annotations

from pathlib import Path
import json
import logging
import shutil
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def _normalize_phone(phone: Optional[str]) -> Optional[str]:
    if not phone:
        return None
    s = ''.join(ch for ch in phone if ch.isdigit() or ch == '+')
    return s if s else None


def _normalize_email(email: Optional[str]) -> Optional[str]:
    if not email:
        return None
    try:
        return email.strip().lower()
    except Exception:
        return None


def _read_parsed_file(path: Path) -> Optional[Dict]:
    try:
        with path.open('r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.debug("Failed to read parsed file %s: %s", path, e)
        return None


def _contact_keys_from_parsed(path: Path) -> Tuple[Optional[str], Optional[str]]:
    parsed = _read_parsed_file(path)
    if not parsed:
        return None, None

    # Prefer `normalized.contact` if present, then fallback to `contact`
    contact = None
    if isinstance(parsed.get('normalized'), dict):
        contact = parsed['normalized'].get('contact') or parsed.get('contact')
    else:
        contact = parsed.get('contact')

    if not isinstance(contact, dict):
        return None, None

    email = _normalize_email(contact.get('email'))
    phone = _normalize_phone(contact.get('phone'))
    return email, phone


def run_dedupe(parsed_dir: str | Path, recent_files: Optional[List[Path]] = None, dry_run: bool = False) -> Dict[str, List[str]]:
    """Run deduplication on parsed JSON files.

    Args:
        parsed_dir: directory containing `*.parsed.json` files.
        recent_files: optional list of Path objects (newly created parsed files) to prioritize.
        dry_run: if True, only log actions and do not move files.

    Returns:
        summary dict with keys `kept` and `removed` listing file paths.
    """
    parsed_path = Path(parsed_dir)
    if not parsed_path.exists():
        raise FileNotFoundError(f"Parsed dir not found: {parsed_path}")

    parsed_files = sorted([p for p in parsed_path.glob('*.parsed.json') if p.is_file()])

    # mapping from key -> list[Path]
    email_map: Dict[str, List[Path]] = {}
    phone_map: Dict[str, List[Path]] = {}

    for p in parsed_files:
        email, phone = _contact_keys_from_parsed(p)
        if email:
            email_map.setdefault(email, []).append(p)
        if phone:
            phone_map.setdefault(phone, []).append(p)

    removed: List[str] = []
    kept: List[str] = []

    def _process_groups(map_: Dict[str, List[Path]]):
        for key, paths in map_.items():
            if len(paths) <= 1:
                if paths:
                    kept.append(str(paths[0]))
                continue

            # Sort by file modification time (newest first) and keep the newest
            paths_sorted = sorted(paths, key=lambda p: p.stat().st_mtime, reverse=True)
            keeper = paths_sorted[0]
            to_remove = paths_sorted[1:]
            kept.append(str(keeper))

            dup_dir = parsed_path / 'duplicates'
            if not dry_run:
                dup_dir.mkdir(parents=True, exist_ok=True)

            for old in to_remove:
                target = dup_dir / old.name
                try:
                    if not dry_run:
                        # If target exists, add suffix to avoid overwrite
                        if target.exists():
                            target = dup_dir / f"{old.stem}--dup{old.suffix}"
                        shutil.move(str(old), str(target))
                    logger.info("Moved duplicate %s -> %s (key=%s)", old, target, key)
                    removed.append(str(old))
                except Exception as e:
                    logger.warning("Failed to move duplicate %s: %s", old, e)

    # Process email groups, then phone groups (phone groups may overlap)
    _process_groups(email_map)
    _process_groups(phone_map)

    # Remove duplicates from `kept` if they were moved
    kept = [p for p in kept if p not in removed]

    summary = {"kept": kept, "removed": removed}
    logger.info("Dedupe summary: kept=%d removed=%d", len(kept), len(removed))
    return summary


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Run dedupe on parsed CV JSON files')
    parser.add_argument('--parsed-dir', default='cv_uploads/parsed', help='Parsed JSON directory')
    parser.add_argument('--dry-run', action='store_true', help='Do not move files; only log')
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    try:
        res = run_dedupe(args.parsed_dir, dry_run=args.dry_run)
        print(res)
    except Exception as e:
        logger.exception('Dedupe failed: %s', e)
