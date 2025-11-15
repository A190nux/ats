"""
Simple JD → CV scoring engine (minimal implementation).

Provides:
- ScoringRubric: configurable weights for rule-based scoring
- MatchResult: lightweight result object consumed by `backend/api.py`
- rank_all_candidates: rank CVParsed objects against a JDParsed

This is intentionally conservative (no external deps) and uses the
normalization helpers from `jd_parser.py` so behavior is consistent.
"""
from dataclasses import dataclass
from typing import List, Optional, Any
from pydantic import BaseModel
from backend.parse.jd_parser import load_skills_map, normalize_skills


class ScoringRubric(BaseModel):
    must_weight: float = 0.5
    nice_weight: float = 0.2
    experience_weight: float = 0.2
    education_weight: float = 0.1
    require_all_must: bool = False


@dataclass
class MatchResult:
    candidate_name: Optional[str]
    resume_id: Optional[str]
    score: float
    matched_must: List[str]
    matched_nice: List[str]
    missing_must: List[str]
    details: dict


def _normalize_list(items: List[str], skills_map: dict) -> List[str]:
    """Normalize a list of skill strings using the skills map."""
    if not items:
        return []
    return normalize_skills(items, skills_map)


def _estimate_experience_years(cv_parsed: Any) -> float:
    """Best-effort estimate of years of experience from CVParsed.

    This minimal implementation uses the number of experience entries
    as a proxy (1 entry ~= 2 years) so we have a numeric value to use
    in scoring. A more advanced implementation should parse dates.
    """
    try:
        entries = getattr(cv_parsed, 'experience', []) or []
        return float(max(0, len(entries) * 2))
    except Exception:
        return 0.0


def rank_all_candidates(jd: Any, cvs: List[Any], rubric: Optional[ScoringRubric] = None) -> List[MatchResult]:
    """Rank CVParsed objects against JDParsed using a simple rule-based rubric.

    Args:
        jd: JDParsed object
        cvs: List of CVParsed objects
        rubric: optional ScoringRubric

    Returns:
        List[MatchResult] sorted by `score` descending
    """
    if rubric is None:
        rubric = ScoringRubric()

    skills_map = load_skills_map()

    jd_must = _normalize_list(getattr(jd, 'skills').must_have if getattr(jd, 'skills', None) else [], skills_map)
    jd_nice = _normalize_list(getattr(jd, 'skills').nice_to_have if getattr(jd, 'skills', None) else [], skills_map)

    results: List[MatchResult] = []

    for cv in cvs:
        try:
            cv_skills_raw = getattr(cv, 'skills', []) or []
            cv_skills = normalize_skills(cv_skills_raw, skills_map)

            matched_must = [s for s in jd_must if s in cv_skills]
            matched_nice = [s for s in jd_nice if s in cv_skills]
            missing_must = [s for s in jd_must if s not in cv_skills]

            # Must-have enforcement
            if rubric.require_all_must and jd_must and missing_must:
                # give zero score if required must-haves are missing
                score = 0.0
            else:
                must_score = (len(matched_must) / max(1, len(jd_must))) if jd_must else 0.0
                nice_score = (len(matched_nice) / max(1, len(jd_nice))) if jd_nice else 0.0

                # Experience: compare estimated years to JD minimum (if provided)
                cv_years = _estimate_experience_years(cv)
                jd_min = getattr(getattr(jd, 'experience', None), 'minimum_years', None) or 0
                exp_score = 0.0
                if jd_min and jd_min > 0:
                    exp_score = min(1.0, cv_years / float(jd_min))
                else:
                    # if JD doesn't specify, neutral score
                    exp_score = 0.5 if cv_years > 0 else 0.0

                # Education match (very simple): check degree level string equality
                edu_score = 0.0
                jd_degree = getattr(getattr(jd, 'education', None), 'degree_level', None)
                if jd_degree:
                    cv_degrees = [getattr(e, 'degree', '').lower() for e in getattr(cv, 'education', []) or [] if getattr(e, 'degree', None)]
                    if any(jd_degree.lower() in d for d in cv_degrees):
                        edu_score = 1.0

                # Weighted sum
                score = (
                    rubric.must_weight * must_score +
                    rubric.nice_weight * nice_score +
                    rubric.experience_weight * exp_score +
                    rubric.education_weight * edu_score
                )

            result = MatchResult(
                candidate_name=getattr(cv, 'name', None) or (getattr(cv, 'contact', None).email if getattr(cv, 'contact', None) else None),
                resume_id=getattr(cv, 'resume_id', None) or None,
                score=round(float(score), 4),
                matched_must=matched_must,
                matched_nice=matched_nice,
                missing_must=missing_must,
                details={
                    'cv_skills': cv_skills,
                    'cv_years_est': _estimate_experience_years(cv)
                }
            )
            results.append(result)
        except Exception:
            # In case a CV is malformed, skip but continue
            continue

    # sort descending
    results.sort(key=lambda r: r.score, reverse=True)
    return results
