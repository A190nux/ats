#!/usr/bin/env python3
"""
Demo script showing JD parsing, persistence, and ranking end-to-end.

Usage:
  python demo_jd_ranking.py

This script:
1. Creates a sample JD and saves it
2. Creates sample CVs
3. Ranks candidates against the JD
4. Displays results
"""

import sys
import json
from pathlib import Path
from datetime import datetime

# Setup path
sys.path.insert(0, str(Path(__file__).parent))

from backend.parse.jd_parser import (
    JDParsed,
    JDSkillsBreakdown,
    JDEducationRequirements,
    JDExperienceRequirements,
    save_jd_with_original,
    load_jd_with_original,
)
from backend.parse.jd_matcher import rank_all_candidates, ScoringRubric
from data_schemas.cv import CVParsed, ExperienceEntry, EducationEntry, CandidateContact


def create_sample_jd() -> tuple[JDParsed, str]:
    """Create a sample JD."""
    jd_text = """
    Senior Python Developer - TechCorp
    
    Location: San Francisco, CA
    
    We are looking for a Senior Python Developer with 5+ years of experience to join our backend team.
    
    Requirements:
    Must Have:
    - 5+ years Python experience
    - FastAPI or Django expertise
    - PostgreSQL knowledge
    - Git proficiency
    
    Nice to Have:
    - Docker experience
    - AWS or GCP knowledge
    - Redis experience
    - Kubernetes basics
    
    Education:
    - Bachelor's degree in Computer Science or related field
    
    Responsibilities:
    - Design and implement scalable APIs
    - Write maintainable, tested code
    - Collaborate with data science team
    - Code review and mentoring
    - Participate in architecture decisions
    
    Benefits:
    - Competitive salary ($150k-$180k)
    - Health insurance
    - Flexible remote work
    - Professional development budget
    """
    
    jd_parsed = JDParsed(
        job_title="Senior Python Developer",
        company="TechCorp",
        location="San Francisco, CA",
        skills=JDSkillsBreakdown(
            must_have=["Python", "FastAPI", "PostgreSQL", "Git"],
            nice_to_have=["Docker", "AWS", "Redis", "Kubernetes"]
        ),
        education=JDEducationRequirements(
            degree_level="Bachelor",
            fields_of_study=["Computer Science", "Engineering"]
        ),
        experience=JDExperienceRequirements(
            minimum_years=5,
            preferred_years=8
        ),
        description=jd_text[:500],
        responsibilities=[
            "Design and implement scalable APIs",
            "Write maintainable, tested code",
            "Collaborate with data science team",
            "Code review and mentoring",
            "Participate in architecture decisions"
        ],
        benefits="Competitive salary ($150k-$180k), health insurance, flexible remote work",
        salary_range="$150k-$180k"
    )
    
    return jd_parsed, jd_text


def create_sample_cvs() -> list[CVParsed]:
    """Create sample CVs for ranking."""
    cvs = [
        CVParsed(
            name="Alice Chen",
            contact=CandidateContact(email="alice.chen@example.com", phone="555-0001"),
            professional_summary="Backend engineer with 8 years Python experience and strong FastAPI skills.",
            education=[
                EducationEntry(
                    institution="University of California",
                    degree="B.S. in Computer Science",
                    major="Computer Science",
                    graduation_year=2016
                )
            ],
            experience=[
                ExperienceEntry(
                    job_title="Senior Backend Engineer",
                    company="CloudTech Inc",
                    start_date="2021",
                    end_date="Present",
                    description="Led backend team building microservices with FastAPI and PostgreSQL."
                ),
                ExperienceEntry(
                    job_title="Backend Developer",
                    company="DataFlow Systems",
                    start_date="2019",
                    end_date="2021",
                    description="Developed APIs with Python, FastAPI, and PostgreSQL."
                ),
                ExperienceEntry(
                    job_title="Junior Python Developer",
                    company="StartupXYZ",
                    start_date="2016",
                    end_date="2019",
                    description="Early-stage startup, built full backend infrastructure."
                )
            ],
            skills=["Python", "FastAPI", "PostgreSQL", "Docker", "AWS", "Git", "Redis", "Kubernetes"],
            certifications=[],
            languages=["English", "Mandarin"]
        ),
        CVParsed(
            name="Bob Johnson",
            contact=CandidateContact(email="bob.johnson@example.com", phone="555-0002"),
            professional_summary="Python developer with 6 years experience in web development.",
            education=[
                EducationEntry(
                    institution="State Technical University",
                    degree="B.S. in Software Engineering",
                    major="Software Engineering",
                    graduation_year=2018
                )
            ],
            experience=[
                ExperienceEntry(
                    job_title="Python Developer",
                    company="WebServices LLC",
                    start_date="2022",
                    end_date="Present",
                    description="Building REST APIs with Django."
                ),
                ExperienceEntry(
                    job_title="Web Developer",
                    company="E-Commerce Corp",
                    start_date="2018",
                    end_date="2022",
                    description="Python and Django development for e-commerce platform."
                )
            ],
            skills=["Python", "Django", "PostgreSQL", "Git", "JavaScript", "React"],
            certifications=[],
            languages=["English"]
        ),
        CVParsed(
            name="Carol Smith",
            contact=CandidateContact(email="carol.smith@example.com", phone="555-0003"),
            professional_summary="Frontend developer transitioning to full-stack.",
            education=[
                EducationEntry(
                    institution="Community College",
                    degree="Associate in Web Development",
                    major="Web Development",
                    graduation_year=2020
                )
            ],
            experience=[
                ExperienceEntry(
                    job_title="Frontend Developer",
                    company="UI Design Studio",
                    start_date="2020",
                    end_date="Present",
                    description="React and Vue.js development."
                )
            ],
            skills=["JavaScript", "React", "Vue.js", "HTML", "CSS", "Python (beginner)"],
            certifications=[],
            languages=["English", "Spanish"]
        ),
    ]
    return cvs


def main():
    """Run the demo."""
    print("=" * 70)
    print("JD Ranking Demo: End-to-End Pipeline")
    print("=" * 70)
    
    # Step 1: Create and save JD
    print("\n[Step 1] Creating and saving sample JD...")
    jd_parsed, jd_text = create_sample_jd()
    
    jds_dir = Path("backend/data/jds")
    jds_dir.mkdir(parents=True, exist_ok=True)
    
    jd_id, jd_folder = save_jd_with_original(jd_parsed, jd_text, jds_dir)
    print(f"  ✓ JD saved with ID: {jd_id}")
    print(f"  ✓ Location: {jd_folder}")
    
    # Step 2: Load JD back from disk
    print("\n[Step 2] Loading JD from disk...")
    loaded_jd, loaded_text = load_jd_with_original(jd_id, jds_dir)
    print(f"  ✓ Loaded JD: {loaded_jd.job_title}")
    print(f"  ✓ Must-have skills: {loaded_jd.skills.must_have}")
    print(f"  ✓ Nice-to-have skills: {loaded_jd.skills.nice_to_have}")
    
    # Step 3: Create sample CVs
    print("\n[Step 3] Creating sample CVs...")
    cvs = create_sample_cvs()
    print(f"  ✓ Created {len(cvs)} sample CVs:")
    for cv in cvs:
        print(f"    - {cv.name}: {', '.join(cv.skills[:3])}...")
    
    # Step 4: Rank candidates
    print("\n[Step 4] Ranking candidates against JD...")
    results = rank_all_candidates(loaded_jd, cvs)
    print(f"  ✓ Ranked {len(results)} candidates")
    
    # Step 5: Display results
    print("\n" + "=" * 70)
    print("RANKING RESULTS")
    print("=" * 70)
    
    for rank, result in enumerate(results, 1):
        print(f"\n#{rank} - {result.candidate_name}")
        print(f"  Score: {result.score:.4f}")
        print(f"  Must-have matches: {len(result.matched_must)}/{len(loaded_jd.skills.must_have)}")
        print(f"    Matched: {', '.join(result.matched_must)}")
        print(f"    Missing: {', '.join(result.missing_must)}")
        print(f"  Nice-to-have matches: {len(result.matched_nice)}")
        print(f"  Experience (est. years): {result.details.get('cv_years_est', 0)}")
    
    # Step 6: Show scoring breakdown
    print("\n" + "=" * 70)
    print("SCORING ANALYSIS")
    print("=" * 70)
    top_result = results[0]
    print(f"\nTop Candidate: {top_result.candidate_name}")
    print(f"  Final Score: {top_result.score:.4f}")
    print(f"  Details: {json.dumps(top_result.details, indent=2)}")
    
    # Step 7: Cleanup (optional - keep for manual inspection)
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"✓ JD saved to: {jd_folder}")
    print(f"✓ Best match: {results[0].candidate_name} (score: {results[0].score:.4f})")
    print(f"✓ You can load this JD later using jd_id: {jd_id}")
    print(f"\nTo rank candidates via API:")
    print(f"  curl -X POST http://localhost:8000/jd/{jd_id}/rank \\")
    print(f"    -H 'X-API-Key: test-key-123'")
    print("\n" + "=" * 70)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n✗ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
