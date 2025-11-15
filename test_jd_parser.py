#!/usr/bin/env python3
"""
Test JD Parser Module

Quick test to verify JD parsing works end-to-end with sample JDs.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from backend.parse.jd_parser import parse_jd_text, save_jd_parsed, load_jd_parsed
from datetime import datetime


def test_sample_jd():
    """Test parsing with a realistic sample JD."""
    
    sample_jd = """
    Senior Machine Learning Engineer
    
    Company: TechAI Solutions
    Location: San Francisco, CA (Remote)
    
    About the Role:
    We're looking for a Senior Machine Learning Engineer to lead our AI/ML initiative.
    You'll work on cutting-edge deep learning models for computer vision and NLP applications.
    
    Key Responsibilities:
    - Design and implement machine learning pipelines using TensorFlow and PyTorch
    - Develop and optimize deep learning models for production
    - Collaborate with data scientists and backend engineers
    - Conduct code reviews and mentor junior engineers
    - Deploy models using Docker and Kubernetes
    - Work with AWS and cloud infrastructure
    
    Required Qualifications:
    - 7+ years of experience in machine learning or deep learning
    - Expert knowledge of Python, TensorFlow, and PyTorch
    - Strong background in computer vision or NLP
    - Proficiency with SQL and data processing (Pandas, NumPy, Spark)
    - Experience with Docker and Kubernetes
    - Git version control expertise
    - Master's degree in Computer Science, Mathematics, or related field
    
    Preferred Qualifications:
    - Experience with YOLO or other real-time detection models
    - Knowledge of FastAPI for model serving
    - AWS certification
    - Published research or open-source contributions
    - Experience with model optimization and deployment
    
    Benefits:
    - Competitive salary: $180k-$220k
    - Health, dental, vision insurance
    - 401(k) matching
    - Unlimited PTO
    - Remote work flexibility
    """
    
    print("=" * 80)
    print("Testing JD Parser")
    print("=" * 80)
    
    try:
        print("\n1. Parsing sample JD text...")
        jd_parsed = parse_jd_text(sample_jd)
        
        print("✓ JD parsed successfully\n")
        
        print("Extracted Data:")
        print(f"  Job Title: {jd_parsed.job_title}")
        print(f"  Company: {jd_parsed.company}")
        print(f"  Location: {jd_parsed.location}")
        print(f"  Salary: {jd_parsed.salary_range}")
        print(f"  Min Years Exp: {jd_parsed.experience.minimum_years}")
        print(f"  Preferred Years Exp: {jd_parsed.experience.preferred_years}")
        print(f"  Education Level: {jd_parsed.education.degree_level}")
        print(f"  Education Fields: {jd_parsed.education.fields_of_study}")
        
        print(f"\n  Must-Have Skills ({len(jd_parsed.skills.must_have)}):")
        for skill in jd_parsed.skills.must_have:
            print(f"    - {skill}")
        
        print(f"\n  Nice-to-Have Skills ({len(jd_parsed.skills.nice_to_have)}):")
        for skill in jd_parsed.skills.nice_to_have:
            print(f"    - {skill}")
        
        print(f"\n  Responsibilities ({len(jd_parsed.responsibilities)}):")
        for i, resp in enumerate(jd_parsed.responsibilities, 1):
            print(f"    {i}. {resp[:60]}...")
        
        print(f"\n  Benefits: {jd_parsed.benefits[:100] if jd_parsed.benefits else 'N/A'}...")
        
        # Test saving
        print("\n2. Saving parsed JD to JSON...")
        output_dir = Path(__file__).parent / "backend" / "data" / "jds"
        output_path = save_jd_parsed(jd_parsed, output_dir)
        print(f"✓ Saved to: {output_path}")
        
        # Test loading
        print("\n3. Loading parsed JD from JSON...")
        loaded_jd = load_jd_parsed(output_path)
        print(f"✓ Loaded successfully")
        print(f"  Loaded title: {loaded_jd.job_title}")
        print(f"  Loaded skills (must-have): {len(loaded_jd.skills.must_have)} items")
        print(f"  Loaded skills (nice-to-have): {len(loaded_jd.skills.nice_to_have)} items")
        
        # Verify round-trip
        if loaded_jd.job_title == jd_parsed.job_title:
            print("\n✓ Round-trip serialization successful!")
        else:
            print("\n✗ Round-trip serialization FAILED!")
            return False
        
        print("\n" + "=" * 80)
        print("All tests passed! ✓")
        print("=" * 80)
        return True
        
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_sample_jd()
    sys.exit(0 if success else 1)
