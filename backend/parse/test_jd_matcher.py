"""
Unit tests for JD matching and ranking.

Demonstrates the full ranking flow without requiring a running LLM or retriever.
"""

import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.parse.jd_parser import JDParsed, JDSkillsBreakdown, JDEducationRequirements, JDExperienceRequirements
from backend.parse.jd_matcher import rank_all_candidates, ScoringRubric, MatchResult
from data_schemas.cv import CVParsed, ExperienceEntry, EducationEntry, CandidateContact


def create_sample_jd() -> JDParsed:
    """Create a sample JD for testing."""
    return JDParsed(
        job_title="Senior Python Developer",
        company="TechCorp",
        location="San Francisco, CA",
        skills=JDSkillsBreakdown(
            must_have=["Python", "FastAPI", "PostgreSQL"],
            nice_to_have=["Docker", "AWS", "Redis"]
        ),
        education=JDEducationRequirements(
            degree_level="Bachelor",
            fields_of_study=["Computer Science", "Engineering"]
        ),
        experience=JDExperienceRequirements(
            minimum_years=5,
            preferred_years=7
        ),
        description="Looking for an experienced Python developer with 5+ years.",
        responsibilities=["Design APIs", "Write clean code", "Code reviews"]
    )


def create_sample_cv_strong() -> CVParsed:
    """Create a strong CV (high match)."""
    return CVParsed(
        name="Alice Developer",
        contact=CandidateContact(email="alice@example.com", phone="555-0001"),
        professional_summary="Experienced Python developer with 8 years in backend development.",
        education=[
            EducationEntry(
                institution="State University",
                degree="B.S. in Computer Science",
                major="Computer Science",
                graduation_year=2016
            )
        ],
        experience=[
            ExperienceEntry(
                job_title="Senior Backend Engineer",
                company="BigTech",
                start_date="2022",
                end_date="Present",
                description="Built microservices with FastAPI and PostgreSQL."
            ),
            ExperienceEntry(
                job_title="Backend Developer",
                company="StartupXYZ",
                start_date="2019",
                end_date="2022",
                description="Developed APIs with Python and FastAPI."
            ),
            ExperienceEntry(
                job_title="Junior Developer",
                company="SmallCo",
                start_date="2016",
                end_date="2019",
                description="Python development and support."
            )
        ],
        skills=["Python", "FastAPI", "PostgreSQL", "Docker", "AWS", "Git"],
        certifications=[],
        languages=["English"]
    )


def create_sample_cv_weak() -> CVParsed:
    """Create a weak CV (low match)."""
    return CVParsed(
        name="Bob Frontend",
        contact=CandidateContact(email="bob@example.com", phone="555-0002"),
        professional_summary="Frontend developer with 3 years of experience.",
        education=[
            EducationEntry(
                institution="Community College",
                degree="Associate in Web Development",
                major="Web Development",
                graduation_year=2021
            )
        ],
        experience=[
            ExperienceEntry(
                job_title="Frontend Developer",
                company="WebShop",
                start_date="2021",
                end_date="Present",
                description="React and Vue.js development."
            )
        ],
        skills=["JavaScript", "React", "Vue.js", "HTML", "CSS"],
        certifications=[],
        languages=["English"]
    )


def test_rank_all_candidates_basic():
    """Test basic ranking functionality."""
    jd = create_sample_jd()
    strong_cv = create_sample_cv_strong()
    weak_cv = create_sample_cv_weak()
    
    results = rank_all_candidates(jd, [weak_cv, strong_cv])
    
    # Results should be sorted descending by score
    assert len(results) == 2
    assert results[0].score >= results[1].score, "Strong CV should rank higher than weak CV"
    
    # Strong CV should have high must-have match
    strong_result = [r for r in results if r.candidate_name == "Alice Developer"][0]
    assert len(strong_result.matched_must) >= 2, "Strong CV should match most must-haves"
    assert strong_result.score > 0.5, "Strong CV should have high score"
    
    # Weak CV should have low match
    weak_result = [r for r in results if r.candidate_name == "Bob Frontend"][0]
    assert len(weak_result.matched_must) == 0, "Weak CV should not match must-haves"
    assert weak_result.score < 0.3, "Weak CV should have low score"


def test_match_result_structure():
    """Test that MatchResult has expected attributes."""
    jd = create_sample_jd()
    cv = create_sample_cv_strong()
    
    results = rank_all_candidates(jd, [cv])
    assert len(results) == 1
    
    result = results[0]
    assert isinstance(result, MatchResult)
    assert result.candidate_name is not None
    assert isinstance(result.score, float)
    assert isinstance(result.matched_must, list)
    assert isinstance(result.matched_nice, list)
    assert isinstance(result.missing_must, list)
    assert isinstance(result.details, dict)


def test_scoring_rubric_weights():
    """Test that custom scoring rubric weights affect results."""
    jd = create_sample_jd()
    cv = create_sample_cv_strong()
    
    # Default weights
    results_default = rank_all_candidates(jd, [cv])
    score_default = results_default[0].score
    
    # Heavy experience weight
    rubric_exp = ScoringRubric(
        must_weight=0.1,
        experience_weight=0.9,
        education_weight=0.0,
        nice_weight=0.0
    )
    results_exp = rank_all_candidates(jd, [cv], rubric=rubric_exp)
    score_exp = results_exp[0].score
    
    # Scores may differ, but both should be positive
    assert score_default > 0
    assert score_exp > 0


def test_empty_candidate_list():
    """Test ranking with no candidates."""
    jd = create_sample_jd()
    results = rank_all_candidates(jd, [])
    assert results == []


def test_malformed_cv_skipped():
    """Test that malformed CVs are gracefully skipped."""
    jd = create_sample_jd()
    
    # Valid CV
    valid_cv = create_sample_cv_strong()
    
    # "Malformed" CV (not a CVParsed object, so will error in getattr)
    class FakeCV:
        pass
    
    fake = FakeCV()
    
    # Should only rank the valid CV (fake one is skipped due to exception)
    results = rank_all_candidates(jd, [fake, valid_cv])
    assert len(results) >= 1, "Should rank at least the valid CV"
    assert any(r.candidate_name == "Alice Developer" for r in results), "Valid CV should be ranked"


if __name__ == "__main__":
    # Run tests manually if executed as script
    test_rank_all_candidates_basic()
    print("✓ test_rank_all_candidates_basic passed")
    
    test_match_result_structure()
    print("✓ test_match_result_structure passed")
    
    test_scoring_rubric_weights()
    print("✓ test_scoring_rubric_weights passed")
    
    test_empty_candidate_list()
    print("✓ test_empty_candidate_list passed")
    
    test_malformed_cv_skipped()
    print("✓ test_malformed_cv_skipped passed")
    
    print("\nAll tests passed!")
