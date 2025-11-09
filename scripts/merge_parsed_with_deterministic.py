#!/usr/bin/env python3
"""Merge deterministic extractions into existing parsed JSON for a CV.

Usage: run from repository root; it will read
  cv_uploads/aly.txt
  cv_uploads/parsed/aly.txt.parsed.json
and write
  cv_uploads/parsed/aly.txt.parsed.auto.json

This is intentionally small and dependency-free.
"""
import json
from pathlib import Path
import sys

# Ensure repository root is in sys.path so imports work when running the script directly
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data_schemas.parse_utils import extract_contacts, split_sections, extract_skills_from_section


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'cv_uploads' / 'aly.txt'
PARSED = ROOT / 'cv_uploads' / 'parsed' / 'aly.txt.parsed.json'
OUT = ROOT / 'cv_uploads' / 'parsed' / 'aly.txt.parsed.auto.json'


def load_text(p: Path) -> str:
    return p.read_text(encoding='utf-8', errors='replace')


def main():
    raw = load_text(RAW)
    parsed = json.loads(PARSED.read_text(encoding='utf-8'))

    contacts = extract_contacts(raw)
    sections = split_sections(raw)

    # Merge contacts
    parsed_contact = parsed.get('contact') or {}
    for k in ('email', 'phone', 'linkedin'):
        if not parsed_contact.get(k) and contacts.get(k):
            parsed_contact[k] = contacts[k]
    # keep github under additional place if not present
    if contacts.get('github'):
        parsed_contact.setdefault('github', contacts['github'])
    parsed['contact'] = parsed_contact

    # Summary
    if not parsed.get('professional_summary'):
        for key in ('SUMMARY', 'PROFESSIONAL SUMMARY'):
            if key in sections and sections[key].strip():
                # take first paragraph
                para = sections[key].split('\n\n')[0].strip()
                parsed['professional_summary'] = para
                break

    # Skills
    if (not parsed.get('skills')) or len(parsed.get('skills', [])) == 0:
        if 'SKILLS' in sections:
            parsed['skills'] = extract_skills_from_section(sections['SKILLS'])

    # Education/Experience placeholders: keep raw section text if the structured arrays are empty
    if (not parsed.get('education')) or len(parsed.get('education', [])) == 0:
        if 'EDUCATION' in sections:
            parsed['education_raw'] = sections['EDUCATION']

    if (not parsed.get('experience')) or len(parsed.get('experience', [])) == 0:
        if 'EXPERIENCE' in sections:
            parsed['experience_raw'] = sections['EXPERIENCE']

    # Write merged file
    OUT.write_text(json.dumps(parsed, indent=2, ensure_ascii=False))
    print(f'Wrote merged parsed file to: {OUT}')


if __name__ == '__main__':
    main()
