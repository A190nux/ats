from pydantic import BaseModel, Field
from typing import List, Optional

# --- 1. Nested Classes (for clean data structure) ---

class CandidateContact(BaseModel):
    """Structured contact information for the candidate."""
    email: Optional[str] = Field(None, description="Candidate's primary email address.")
    phone: Optional[str] = Field(None, description="Candidate's primary phone number.")
    linkedin: Optional[str] = Field(None, description="URL to the candidate's LinkedIn profile, if found.")

class EducationEntry(BaseModel):
    """A single educational qualification."""
    institution: str = Field(description="The name of the university or institution.")
    degree: Optional[str] = Field(None, description="The degree obtained (e.g., 'B.S. in Computer Science', 'Master of Business Administration').")
    major: Optional[str] = Field(None, description="The field of study (e.g., 'Computer Science').")
    graduation_year: Optional[int] = Field(None, description="The year of graduation.")

class ExperienceEntry(BaseModel):
    """A single professional work experience entry."""
    job_title: str = Field(description="The job title held (e.g., 'Senior Software Engineer').")
    company: str = Field(description="The name of the company.")
    start_date: Optional[str] = Field(None, description="Start date (e.g., 'Jan 2020', '2020').")
    end_date: Optional[str] = Field(None, description="End date (e.g., 'Jan 2022', 'Present').")
    description: Optional[str] = Field(None, description="A brief summary of responsibilities, achievements, or skills used.")

class CertificationEntry(BaseModel):
    """A single professional certification."""
    name: str = Field(description="The name of the certification (e.g., 'AWS Certified Solutions Architect').")
    issuer: Optional[str] = Field(None, description="The organization that issued the certification (e.g., 'Amazon Web Services').")
    year: Optional[int] = Field(None, description="The year the certification was obtained.")

# --- 2. The Main CV Parsing Class ---

class CVParsed(BaseModel):
    """
    The complete structured data extracted from a single CV document.
    This schema is based on the project requirements .
    """
    
    name: str = Field(description="The full name of the candidate.")
    
    contact: CandidateContact = Field(description="Candidate's contact information.")
    
    professional_summary: Optional[str] = Field(None, description="A brief professional summary from the CV, if present.")

    education: List[EducationEntry] = Field(
        default_factory=list, 
        description="A list of the candidate's educational qualifications."
    )
    
    experience: List[ExperienceEntry] = Field(
        default_factory=list, 
        description="A list of the candidate's professional work experience."
    )
    
    skills: List[str] = Field(
        default_factory=list, 
        description="A list of all extracted technical skills, programming languages, software, and tools."
    )
    
    certifications: List[CertificationEntry] = Field(
        default_factory=list, 
        description="A list of the candidate's professional certifications."
    )
    
    languages: List[str] = Field(
        default_factory=list, 
        description="A list of human languages spoken by the candidate (e.g., 'English', 'Spanish')."
    )