"""
Streamlit Web UI for ATS (Applicant Tracking System)

Features:
- Drag-and-drop file uploads
- Real-time job status tracking
- Interactive chat interface for RAG queries
- Dashboard with queue statistics
- File browser and management

Run: streamlit run web/app.py
"""

import streamlit as st
import requests
import json
import time
from datetime import datetime
from pathlib import Path
import pandas as pd

# Configuration
API_BASE_URL = st.secrets.get("api_url", "http://localhost:8000")
API_KEY = st.secrets.get("api_key", "test-key-123")

# Page configuration
st.set_page_config(
    page_title="ATS - CV Search & Ranking",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .main { padding: 2rem; }
    .stTabs [data-baseweb="tab-list"] button { font-size: 1.1rem; font-weight: 500; }
    .upload-box { border: 2px dashed #4CAF50; border-radius: 8px; padding: 2rem; text-align: center; background-color: #f0f8f0; }
    .job-card { border-left: 4px solid #4CAF50; padding: 1rem; margin: 0.5rem 0; background-color: #f9f9f9; border-radius: 4px; }
    .status-pending { background-color: #fff3cd; color: #856404; }
    .status-processing { background-color: #d1ecf1; color: #0c5460; }
    .status-completed { background-color: #d4edda; color: #155724; }
    .status-failed { background-color: #f8d7da; color: #721c24; }
</style>
""", unsafe_allow_html=True)


# ==================== Helper Functions ====================

@st.cache_resource
def get_session_state():
    """Get or create session state."""
    if 'last_upload_time' not in st.session_state:
        st.session_state.last_upload_time = 0
    if 'refresh_key' not in st.session_state:
        st.session_state.refresh_key = 0
    return st.session_state


# Simple role -> permissions mapping used by the UI (mirrors backend)
ROLE_PERMISSIONS = {
    "admin": [
        "upload_cv",
        "search_cv",
        "parse_jd",
        "rank_candidates",
        "export_results",
        "view_analytics",
        "manage_users",
        "manage_settings",
    ],
    "recruiter": [
        "upload_cv",
        "search_cv",
        "parse_jd",
        "rank_candidates",
        "export_results",
        "view_analytics",
    ],
    "viewer": [
        "search_cv",
        "view_analytics",
    ],
}


def has_permission_ui(permission: str) -> bool:
    """Check current UI user's permissions (simple client-side check).

    This mirrors backend roles but does not replace server-side authorization.
    """
    user = st.session_state.get("current_user")
    if not user:
        return False
    role = user.get("role", "viewer")
    perms = ROLE_PERMISSIONS.get(role, [])
    return permission in perms



def make_api_call(method, endpoint, **kwargs):
    """Make API call with error handling."""
    try:
        headers = kwargs.pop("headers", {})
        headers["X-API-Key"] = API_KEY
        # If we have a user token in session, send it as Bearer authorization
        try:
            auth_token = st.session_state.get("auth_token")
        except Exception:
            auth_token = None
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"
        url = f"{API_BASE_URL}{endpoint}"
        # Increase request timeout to allow longer LLM/RAG processing on the server.
        # This avoids premature frontend "timed out" errors when the backend
        # is waiting on the LLM or GPU resources. 300s should be sufficient
        # for typical RAG responses; adjust if you expect longer jobs.
        response = requests.request(method, url, headers=headers, timeout=300, **kwargs)
        
        if response.status_code == 401:
            st.error("❌ API Key Error: Invalid or missing API key")
            return None
        elif response.status_code == 403:
            st.error("❌ Permission Denied: Check your API key")
            return None
        elif response.status_code >= 400:
            # Try to parse error JSON, otherwise return raw text
            try:
                error_data = response.json()
                return error_data
            except:
                return {"error": f"HTTP {response.status_code}: {response.text[:200]}"}
        
        return response.json() if response.text else {}
    
    except requests.exceptions.ConnectionError:
        st.error(f"❌ Cannot connect to API at {API_BASE_URL}\n\nMake sure the API is running:\n`python3 backend/api.py`")
        return None
    except requests.exceptions.Timeout:
        st.warning("⚠️ Request timed out. This may happen if Ollama is processing a large JD.")
        return None
    except Exception as e:
        st.error(f"❌ API Error: {str(e)}")
        return None


def upload_files(uploaded_files):
    """Upload files to API."""
    if not uploaded_files:
        return None
    
    try:
        files = [("files", (file.name, file.getbuffer(), file.type)) for file in uploaded_files]
        
        with st.spinner(f"Uploading {len(uploaded_files)} file(s)..."):
            response = make_api_call(
                "POST",
                "/upload-bulk",
                files=files
            )
        
        if response and "results" in response:
            st.session_state.last_upload_time = time.time()
            return response
        return None
    
    except Exception as e:
        st.error(f"Upload error: {str(e)}")
        return None


def get_mime_type(format_str):
    """Get MIME type for export format."""
    mime_types = {
        "csv": "text/csv",
        "json": "application/json",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "pdf": "application/pdf"
    }
    return mime_types.get(format_str.lower(), "application/octet-stream")


def get_job_status(job_id):
    """Get status of a job."""
    response = make_api_call("GET", f"/status/{job_id}")
    return response if response else {}


def get_queue_stats():
    """Get queue statistics."""
    response = make_api_call("GET", "/stats")
    return response if response else {}


def list_jobs(status=None, limit=50):
    """List jobs from queue."""
    params = {"limit": limit}
    if status:
        params["status"] = status
    
    response = make_api_call("GET", "/jobs", params=params)
    return response.get("jobs", []) if response else []


def check_health():
    """Check API health."""
    response = make_api_call("GET", "/health")
    return response is not None


# ==================== UI Components ====================

def render_status_badge(status):
    """Render status badge with color."""
    status_map = {
        "pending": ("⏳ Pending", "#fff3cd"),
        "processing": ("⚙️ Processing", "#d1ecf1"),
        "completed": ("✅ Completed", "#d4edda"),
        "failed": ("❌ Failed", "#f8d7da")
    }
    
    label, color = status_map.get(status, ("❓ Unknown", "#e2e3e5"))
    return f'<span style="background-color: {color}; padding: 0.25rem 0.75rem; border-radius: 20px; font-size: 0.9rem;">{label}</span>'


def render_upload_section():
    """Render file upload section."""
    st.markdown("### 📤 Upload CVs")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        uploaded_files = st.file_uploader(
            "Drop your CV files here or click to browse",
            type=["pdf", "docx", "doc", "txt", "jpg", "jpeg", "png", "tiff"],
            accept_multiple_files=True,
            help="Supported: PDF, DOCX, DOC, TXT, JPG, PNG, TIFF"
        )
    
    with col2:
        max_retries = st.number_input("Max Retries", min_value=1, max_value=10, value=3)
    
    if uploaded_files:
        st.info(f"📁 {len(uploaded_files)} file(s) selected")
        
        col1, col2 = st.columns(2)
        with col1:
            if has_permission_ui("upload_cv"):
                if st.button("✅ Upload Files", key="upload_btn", type="primary"):
                    result = upload_files(uploaded_files)
                    if result:
                        successful = result.get("successful", 0)
                        failed = result.get("failed", 0)
                        st.success(f"✅ Uploaded {successful} file(s)")
                        if failed > 0:
                            st.warning(f"⚠️ Failed to upload {failed} file(s)")
            else:
                st.info("🔒 You don't have permission to upload files. Please login as a recruiter or admin.")
        
        with col2:
            if st.button("🔄 Clear Files"):
                st.rerun()


def render_dashboard_section():
    """Render dashboard with statistics."""
    st.markdown("### 📊 Dashboard")
    
    stats = get_queue_stats()
    
    if stats:
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                "⏳ Pending",
                stats.get("pending", 0),
                delta=None,
                help="Jobs waiting to be processed"
            )
        
        with col2:
            st.metric(
                "⚙️ Processing",
                stats.get("processing", 0),
                delta=None,
                help="Jobs currently being processed"
            )
        
        with col3:
            st.metric(
                "✅ Completed",
                stats.get("completed", 0),
                delta=None,
                help="Successfully processed jobs"
            )
        
        with col4:
            st.metric(
                "❌ Failed",
                stats.get("failed", 0),
                delta=None,
                help="Jobs that failed after max retries"
            )


def render_jobs_section():
    """Render jobs listing section."""
    st.markdown("### 📋 Job History")
    
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        status_filter = st.selectbox(
            "Filter by Status",
            ["all", "pending", "processing", "completed", "failed"],
            key="status_filter"
        )
    
    with col2:
        limit = st.number_input("Limit", min_value=5, max_value=100, value=20)
    
    with col3:
        if st.button("🔄 Refresh", key="refresh_jobs_btn"):
            st.rerun()
    
    status_param = None if status_filter == "all" else status_filter
    jobs = list_jobs(status=status_param, limit=limit)
    
    if jobs:
        for job in jobs:
            with st.container(border=True):
                col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
                
                with col1:
                    st.markdown(f"**{Path(job['file_path']).name}**")
                    st.caption(f"ID: `{job['job_id'][:8]}...`")
                
                with col2:
                    st.markdown(render_status_badge(job['status']), unsafe_allow_html=True)
                
                with col3:
                    if job.get("result"):
                        st.markdown(f"✅ {job['result'].get('documents_loaded', 0)} docs")
                    if job.get("error_message"):
                        st.markdown(f"⚠️ Error")
                
                with col4:
                    col_a, col_b = st.columns(2)
                    with col_a:
                        if st.button("📊", key=f"view_{job['job_id']}", help="View details"):
                            st.session_state[f"expand_{job['job_id']}"] = True
                    with col_b:
                        if st.button("🔄", key=f"retry_{job['job_id']}", help="Re-ingest"):
                            result = make_api_call("POST", f"/re-ingest/{job['job_id']}")
                            if result and "job_id" in result:
                                st.success(f"✅ Re-ingestion started")
                                st.rerun()
                
                # Expandable details
                if st.session_state.get(f"expand_{job['job_id']}", False):
                    with st.expander("📖 Details", expanded=True):
                        st.json({
                            "job_id": job["job_id"],
                            "status": job["status"],
                            "file_path": job["file_path"],
                            "retries": f"{job['retries']}/{job['max_retries']}",
                            "created_at": job["created_at"],
                            "updated_at": job["updated_at"],
                            "error": job.get("error_message"),
                            "result": job.get("result")
                        })
    else:
        st.info("No jobs found")


def render_jd_matching_section():
    """Render JD matching and ranking interface."""
    st.markdown("### 🎯 JD Matching & Ranking")
    st.markdown("Upload a Job Description or paste job details to match and rank candidates.")
    
    # Initialize session state for JD section
    if 'jd_id' not in st.session_state:
        st.session_state.jd_id = None
    if 'jd_data' not in st.session_state:
        st.session_state.jd_data = None
    
    # JD Input Section
    st.markdown("#### 1️⃣ Input Job Description")
    
    col1, col2 = st.columns(2)
    with col1:
        input_method = st.radio("Choose input method", ["Paste Text", "Upload File"], horizontal=True)
    
    jd_text = None
    
    if input_method == "Paste Text":
        jd_text = st.text_area(
            "Paste job description (JD) here",
            height=200,
            placeholder="Senior Python Developer with 5+ years experience...",
            label_visibility="collapsed"
        )
    else:
        uploaded_file = st.file_uploader(
            "Upload JD file (TXT, PDF, DOCX)",
            type=["txt", "pdf", "docx"],
            label_visibility="collapsed"
        )
        if uploaded_file:
            st.success(f"✓ File loaded: {uploaded_file.name}")
            jd_text = f"[File: {uploaded_file.name}]"  # Placeholder, actual text would come from API
    
    # Parse JD Button
    if st.button("📋 Parse Job Description", use_container_width=True, type="primary"):
        if jd_text:
            with st.spinner("🔄 Parsing JD with AI (this may take 10-30 seconds)..."):
                result = make_api_call(
                    "POST",
                    "/jd/parse",
                    json={"jd_text": jd_text}
                )
                
                if result and "jd_id" in result:
                    st.session_state.jd_id = result["jd_id"]
                    st.session_state.jd_data = result.get("jd_parsed")
                    st.success(f"✓ JD parsed successfully! ID: {result['jd_id'][:8]}...")
                    st.rerun()
                elif result and "error" in result:
                    st.error(f"❌ API Error: {result.get('error', 'Unknown error')}")
                elif result:
                    st.error(f"❌ Failed to parse JD: {result.get('detail', 'Unknown error')}")
                else:
                    st.error("❌ Failed to parse JD: No response from API")
        else:
            st.warning("⚠️ Please enter or upload a job description")
    
    # Display Parsed JD
    if st.session_state.jd_id and st.session_state.jd_data:
        jd = st.session_state.jd_data
        
        st.markdown("#### 2️⃣ Parsed JD Details")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Job Title", jd.get("job_title", "N/A"))
        with col2:
            st.metric("Company", jd.get("company", "N/A"))
        with col3:
            st.metric("Location", jd.get("location", "N/A"))
        
        # Skills breakdown
        st.markdown("##### Required Skills")
        skills_col1, skills_col2 = st.columns(2)
        
        with skills_col1:
            must_have = jd.get("skills", {}).get("must_have", [])
            if must_have:
                st.markdown("**Must-Have:**")
                for skill in must_have:
                    st.write(f"• {skill}")
            else:
                st.info("No must-have skills identified")
        
        with skills_col2:
            nice_to_have = jd.get("skills", {}).get("nice_to_have", [])
            if nice_to_have:
                st.markdown("**Nice-to-Have:**")
                for skill in nice_to_have:
                    st.write(f"• {skill}")
            else:
                st.info("No nice-to-have skills identified")
        
        # Experience & Education
        exp_col1, edu_col1 = st.columns(2)
        with exp_col1:
            min_years = jd.get("experience", {}).get("minimum_years")
            if min_years:
                st.write(f"**Experience:** {min_years}+ years")
        
        with edu_col1:
            degree = jd.get("education", {}).get("degree_level")
            if degree:
                st.write(f"**Education:** {degree} degree")
        
        # Ranking Section
        st.markdown("#### 3️⃣ Rank Candidates")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            semantic_weight = st.slider(
                "Semantic Weight (0=rule-based only, 1=semantic only)",
                min_value=0.0,
                max_value=1.0,
                value=0.4,
                step=0.1
            )
        with col2:
            top_k = st.number_input(
                "Number of candidates to rank",
                min_value=1,
                max_value=200,
                value=20
            )
        with col3:
            st.write("")  # Spacer
            rank_button = st.button("🚀 Rank Candidates", use_container_width=True, type="primary")
        
        if rank_button:
            with st.spinner("🔄 Ranking candidates..."):
                result = make_api_call(
                    "POST",
                    f"/jd/{st.session_state.jd_id}/rank",
                    params={
                        "semantic_weight": semantic_weight,
                        "top_k": top_k
                    }
                )
                
                if result and "rankings" in result:
                    rankings = result["rankings"]
                    st.success(f"✓ Ranked {len(rankings)} candidates")
                    
                    # Display rankings
                    st.markdown("##### Ranking Results")
                    
                    for rank, candidate in enumerate(rankings, 1):
                        # Create expandable card for each candidate
                        with st.expander(
                            f"#{rank} - {candidate['candidate_name']} (Score: {candidate['final_score']:.4f})",
                            expanded=rank <= 3
                        ):
                            col1, col2, col3, col4 = st.columns(4)
                            
                            with col1:
                                st.metric("Final Score", f"{candidate['final_score']:.4f}")
                            with col2:
                                st.metric("Rule-Based", f"{candidate['rule_score']:.4f}")
                            with col3:
                                st.metric("Semantic", f"{candidate['semantic_score']:.4f}")
                            with col4:
                                st.metric("Resume ID", candidate.get("resume_id", "N/A")[:8] if candidate.get("resume_id") else "N/A")
                            
                            # Skills matching
                            st.markdown("**Skills Matching:**")
                            skills_col1, skills_col2, skills_col3 = st.columns(3)
                            
                            with skills_col1:
                                matched_must = candidate.get("matched_must", [])
                                st.write(f"✅ **Must-Have Matched:** {len(matched_must)}")
                                if matched_must:
                                    for skill in matched_must:
                                        st.write(f"  • {skill}")
                            
                            with skills_col2:
                                matched_nice = candidate.get("matched_nice", [])
                                st.write(f"⭐ **Nice-to-Have Matched:** {len(matched_nice)}")
                                if matched_nice:
                                    for skill in matched_nice[:5]:
                                        st.write(f"  • {skill}")
                                    if len(matched_nice) > 5:
                                        st.write(f"  ... and {len(matched_nice) - 5} more")
                            
                            with skills_col3:
                                missing_must = candidate.get("missing_must", [])
                                st.write(f"❌ **Must-Have Missing:** {len(missing_must)}")
                                if missing_must:
                                    for skill in missing_must[:5]:
                                        st.write(f"  • {skill}")
                                    if len(missing_must) > 5:
                                        st.write(f"  ... and {len(missing_must) - 5} more")
                            
                            # Additional details
                            details = candidate.get("details", {})
                            if details:
                                st.markdown("**Details:**")
                                col_exp, col_skills = st.columns(2)
                                with col_exp:
                                    cv_years = details.get("cv_years_est", 0)
                                    st.write(f"Estimated Experience: {cv_years} years")
                                with col_skills:
                                    cv_skills = details.get("cv_skills", [])
                                    st.write(f"Total Skills: {len(cv_skills)}")
                    
                    # Export option
                    st.divider()
                    st.markdown("**📋 Export & Report Generation**")
                    
                    # Generate PDF Report button (prominent placement)
                    col_report1, col_report2, col_report3 = st.columns([2, 2, 1])
                    with col_report1:
                        report_top_k = st.number_input(
                            "Top candidates to include in report",
                            min_value=1,
                            max_value=min(50, len(rankings)),
                            value=min(10, len(rankings))
                        )
                    with col_report2:
                        if has_permission_ui("export_results"):
                            generate_report = st.button(
                                "📄 Generate PDF Report",
                                use_container_width=True,
                                type="primary",
                                key="gen_pdf_report"
                            )
                        else:
                            st.info("🔒 Report generation: insufficient permissions")
                            generate_report = False
                    
                    if generate_report:
                        with st.spinner("📄 Generating professional PDF report..."):
                            try:
                                # Call the report generation endpoint
                                report_response = make_api_call(
                                    "POST",
                                    f"/jd/{st.session_state.jd_id}/rank/report",
                                    params={
                                        "semantic_weight": semantic_weight,
                                        "top_k": top_k,
                                        "report_top_k": report_top_k
                                    }
                                )
                                
                                # Debug: show response if available
                                if not report_response:
                                    st.error("❌ No response from API. Check if API is running: `python3 backend/api.py`")
                                elif "error" in report_response and "pdf_path" not in report_response:
                                    st.error(f"❌ Report generation failed: {report_response.get('error', 'Unknown error')}")
                                elif "pdf_path" in report_response:
                                    pdf_path = report_response["pdf_path"]
                                    st.success(f"✅ PDF Report Generated!")
                                    
                                    # Show download link
                                    import os
                                    if os.path.exists(pdf_path):
                                        with open(pdf_path, 'rb') as f:
                                            pdf_content = f.read()
                                            st.download_button(
                                                label=f"⬇️ Download PDF Report ({len(pdf_content)/1024:.1f} KB)",
                                                data=pdf_content,
                                                file_name=os.path.basename(pdf_path),
                                                mime="application/pdf",
                                                key=f"pdf_download_{st.session_state.jd_id}"
                                            )
                                        st.caption(f"📁 File: {os.path.basename(pdf_path)}")
                                    else:
                                        st.error(f"❌ PDF file not found on disk: {pdf_path}")
                                    
                                    # Show report preview info
                                    st.info(f"📊 Report includes top {report_top_k} candidates with detailed match analysis")
                                else:
                                    st.warning(f"⚠️ Unexpected response from API: {report_response}")
                            
                            except Exception as e:
                                import traceback
                                st.error(f"❌ Report error: {str(e)}")
                                with st.expander("Debug: Show error details"):
                                    st.code(traceback.format_exc())
                    
                    # Standard Export Options
                    st.markdown("---")
                    st.markdown("**💾 Export Rankings**")
                    
                    # Format selection
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        export_format = st.selectbox(
                            "Export Format",
                            ["CSV", "XLSX", "JSON", "PDF"],
                            label_visibility="collapsed"
                        )
                    
                    # Export button (permission checked)
                    export_clicked = False
                    with col2:
                        if has_permission_ui("export_results"):
                            export_clicked = st.button("💾 Export Now", use_container_width=True, type="secondary")
                        else:
                            st.info("🔒 Export disabled: insufficient permissions")
                            export_clicked = False
                    
                    if export_clicked:
                        with st.spinner(f"📤 Exporting as {export_format}..."):
                            try:
                                # Prepare results for export
                                export_payload = {
                                    "results": rankings,
                                    "format": export_format.lower(),
                                    "jd_data": st.session_state.jd_data or {},
                                    "jd_title": st.session_state.jd_data.get("job_title", "Job Description") if st.session_state.jd_data else "Job Description"
                                }
                                
                                # Call export API
                                export_response = make_api_call(
                                    "POST",
                                    "/export",
                                    json=export_payload
                                )
                                
                                if export_response and "file_path" in export_response:
                                    file_path = export_response["file_path"]
                                    st.success(f"✅ Export successful! File: {file_path}")
                                    
                                    # Show download link
                                    st.info(f"📁 Download from: `{file_path}`")
                                    
                                    # Try to read and offer download if local
                                    import os
                                    if os.path.exists(file_path):
                                        with open(file_path, 'rb') as f:
                                            file_content = f.read()
                                            st.download_button(
                                                label=f"⬇️ Download {export_format}",
                                                data=file_content,
                                                file_name=os.path.basename(file_path),
                                                mime=get_mime_type(export_format)
                                            )
                                else:
                                    st.error(f"❌ Export failed: {export_response.get('error', 'Unknown error')}")
                            
                            except Exception as e:
                                st.error(f"❌ Export error: {str(e)}")
                    
                    # Also show quick download buttons for CSV/JSON (local quick exports)
                    st.markdown("---")
                    st.markdown("**Quick Export (Local)**")
                    quick_col1, quick_col2 = st.columns(2)
                    
                    with quick_col1:
                        # Create CSV export
                        csv_data = []
                        for rank, candidate in enumerate(rankings, 1):
                            csv_data.append({
                                "Rank": rank,
                                "Name": candidate['candidate_name'],
                                "Final Score": f"{candidate['final_score']:.4f}",
                                "Rule Score": f"{candidate['rule_score']:.4f}",
                                "Semantic Score": f"{candidate['semantic_score']:.4f}",
                                "Must-Have Matched": len(candidate.get("matched_must", [])),
                                "Nice-to-Have Matched": len(candidate.get("matched_nice", [])),
                                "Must-Have Missing": len(candidate.get("missing_must", []))
                            })
                        
                        df = pd.DataFrame(csv_data)
                        csv = df.to_csv(index=False)
                        # Only allow direct CSV/JSON downloads for users with export permission
                        if has_permission_ui("export_results"):
                            st.download_button(
                                label="📥 CSV (Direct)",
                                data=csv,
                                file_name=f"jd_ranking_{st.session_state.jd_id[:8]}.csv",
                                mime="text/csv"
                            )
                        else:
                            st.info("🔒 Direct downloads disabled: insufficient permissions")
                    
                    with quick_col2:
                        # JSON export
                        json_str = json.dumps(result, indent=2)
                        st.download_button(
                            label="📥 JSON (Direct)",
                            data=json_str,
                            file_name=f"jd_ranking_{st.session_state.jd_id[:8]}.json",
                            mime="application/json"
                        )
                
                elif result:
                    st.error(f"❌ Ranking failed: {result.get('detail', 'Unknown error')}")
        
        # New JD option
        st.divider()
        if st.button("🔄 Start New JD Matching"):
            st.session_state.jd_id = None
            st.session_state.jd_data = None
            st.rerun()


def render_chat_section():
    """Render chat interface for RAG queries over CVs with session management."""
    st.markdown("### 💬 Chat with CVs")
    st.markdown("Ask questions about candidate skills, experience, and qualifications. The system will search through CVs and provide answers with citations.")
    
    # Initialize chat state
    if 'current_session_id' not in st.session_state:
        st.session_state.current_session_id = None
    if 'chat_history' not in st.session_state:
        st.session_state.chat_history = []
    
    # Session management
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        if st.button("📋 New Session", use_container_width=True):
            st.session_state.current_session_id = None
            st.session_state.chat_history = []
            st.success("✓ New session created")
            st.rerun()
    with col2:
        # Only admins may load/list sessions
        if has_permission_ui("manage_users"):
            if st.button("📂 Load Session", use_container_width=True):
                # List available sessions
                response = make_api_call("GET", "/chat?limit=10")
                if response and "sessions" in response:
                    st.session_state.available_sessions = response["sessions"]
        else:
            st.info("🔒 Session loading is restricted to admins.")
    with col3:
        if st.button("💾 Save", use_container_width=True):
            st.success("✓ Session saved automatically")
    
    # Display current session ID
    if st.session_state.current_session_id:
        st.info(f"📌 Session ID: `{st.session_state.current_session_id[:8]}...`")
    
    # Settings for RAG query
    col1, col2 = st.columns([3, 1])
    with col1:
        question = st.text_input(
            "Your Question",
            placeholder="e.g., 'Find candidates with Machine Learning experience' or 'Who has Docker and FastAPI skills?'",
            key="chat_question"
        )
    with col2:
        top_k = st.number_input("Top Results", min_value=1, max_value=20, value=10)
    
    # Submit button
    if st.button("🔍 Search & Answer", use_container_width=True, type="primary"):
        if not question or len(question.strip()) < 3:
            st.warning("⚠️ Please enter a question (at least 3 characters)")
        else:
            with st.spinner("🤖 Searching candidates and generating answer..."):
                try:
                    # Call chat endpoint with session support
                    response = make_api_call(
                        "POST",
                        "/chat",
                        json={
                            "session_id": st.session_state.current_session_id,
                            "question": question,
                            "top_k": top_k
                        }
                    )
                    
                    if response and "error" not in response:
                        # Update session ID
                        st.session_state.current_session_id = response.get("session_id")
                        
                        # Add to chat history
                        st.session_state.chat_history.append({
                            "question": question,
                            "answer": response.get("answer", "No answer generated"),
                            "sources": response.get("sources", []),
                            "timestamp": datetime.now()
                        })
                        
                        st.success("✅ Answer generated successfully!")
                        st.rerun()
                    else:
                        st.error(f"❌ Error: {response.get('error', 'Unknown error occurred')}")
                
                except Exception as e:
                    st.error(f"❌ Connection error: {str(e)}")
    
    # Display chat history
    if not has_permission_ui("manage_users"):
        st.info("💡 Your conversation is saved but only admins can view full session history.")
    else:
        if st.session_state.chat_history:
            st.markdown("---")
            st.markdown("### 📝 Conversation History")
            
            # Display in reverse order (newest first)
            for i, chat in enumerate(reversed(st.session_state.chat_history)):
                with st.container():
                    # Question
                    st.markdown(f"**❓ Question:** {chat['question']}")
                    
                    # Answer
                    st.markdown(f"**🤖 Answer:**")
                    st.write(chat['answer'])
                    
                    # Sources
                    if chat['sources']:
                        st.markdown("**📎 Sources & Candidates:**")
                        for source in chat['sources']:
                            col1, col2 = st.columns([3, 1])
                            with col1:
                                st.markdown(
                                    f"**{source.get('candidate_name', 'Unknown')}** "
                                    f"({source.get('resume_id', 'N/A')})"
                                )
                                st.write(source.get('chunk_text', 'No text'))
                            with col2:
                                score = source.get('similarity_score', 0)
                                try:
                                    st.metric("Match", f"{score:.1%}")
                                except Exception:
                                    st.metric("Match", str(score))
                    
                    # Metadata
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.caption(f"📋 Candidates Reviewed: {chat.get('num_resumes', '')}")
                    with col2:
                        ts = chat.get('timestamp')
                        if hasattr(ts, 'strftime'):
                            st.caption(f"⏰ {ts.strftime('%Y-%m-%d %H:%M:%S')}")
                        else:
                            st.caption(f"⏰ {ts}")
                    with col3:
                        if st.button("🗑️ Delete", key=f"delete_chat_{i}"):
                            st.session_state.chat_history.pop(len(st.session_state.chat_history) - 1 - i)
                            st.rerun()
            
            # Clear history button
            if st.button("🧹 Clear All Conversation History", use_container_width=True):
                st.session_state.chat_history = []
                st.rerun()
        else:
            st.info("💡 No questions asked yet. Ask something to get started!")


def render_settings_section():
    """Render settings panel."""
    st.markdown("### ⚙️ Settings")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**API Configuration**")
        api_url = st.text_input("API URL", value=API_BASE_URL)
        api_key = st.text_input("API Key", value=API_KEY, type="password")
        
        if st.button("✅ Save Settings"):
            st.success("Settings saved (in session)")
    
    with col2:
        st.markdown("**System Status**")
        if st.button("🔍 Check API Health"):
            if check_health():
                st.success("✅ API is healthy and running")
            else:
                st.error("❌ Cannot reach API")


# ==================== Main App ====================

def main():
    """Main Streamlit app."""
    # Header
    st.markdown("""
    <div style="text-align: center; margin-bottom: 2rem;">
        <h1>🤖 ATS - AI-Powered CV Search & Ranking</h1>
        <p style="color: #666; font-size: 1.1rem;">Upload CVs, track ingestion jobs, and search with AI</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Check API health
    if not check_health():
        st.error("""
        ❌ **API is not running**
        
        Start the API with:
        ```bash
        python3 backend/api.py
        ```
        """)
        return
    
    # Main tabs (JD Matching visible only to recruiters/admins)
    tab_labels = ["📤 Upload", "📊 Dashboard", "📋 Jobs"]
    if has_permission_ui("rank_candidates"):
        tab_labels.append("🎯 JD Matching")
    tab_labels.append("💬 Chat")

    tabs = st.tabs(tab_labels)
    tabs_by_label = {label: tab for label, tab in zip(tab_labels, tabs)}

    with tabs_by_label["📤 Upload"]:
        render_upload_section()
        st.divider()
        render_dashboard_section()

    with tabs_by_label["📊 Dashboard"]:
        render_dashboard_section()
        st.divider()
        # Show recent uploads
        st.markdown("### 📈 Recent Activity")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 Refresh Stats"):
                st.rerun()

    with tabs_by_label["📋 Jobs"]:
        render_jobs_section()

    if "🎯 JD Matching" in tabs_by_label:
        with tabs_by_label["🎯 JD Matching"]:
            render_jd_matching_section()

    with tabs_by_label["💬 Chat"]:
        render_chat_section()
    
    # Sidebar
    with st.sidebar:
        st.markdown("### 🔧 Controls")

        # Login using backend auth if available; fallback to demo role selection
        st.markdown("**User Login**")
        if 'current_user' not in st.session_state:
            st.session_state.current_user = None
            st.session_state.auth_token = None

        login_col1, login_col2 = st.columns([2, 1])
        with login_col1:
            username = st.text_input("Username", value=(st.session_state.current_user.get('username') if st.session_state.current_user else ""))
            password = st.text_input("Password", type="password")
            # Role picker for demo fallback (backend determines role on real auth)
            role = st.selectbox("Role (demo fallback)", ["recruiter", "admin", "viewer"], index=0)
        with login_col2:
            if st.button("🔐 Login"):
                # Try backend authentication first
                try:
                    resp = make_api_call("POST", "/auth/login", json={"username": username, "password": password})
                    if resp and resp.get("token"):
                        # Successful backend login
                        st.session_state.auth_token = resp.get("token")
                        st.session_state.current_user = {
                            "username": resp.get("username"),
                            "role": resp.get("role"),
                            "user_id": resp.get("user_id")
                        }
                        st.success(f"Logged in as {st.session_state.current_user['username']} ({st.session_state.current_user['role']})")
                        st.rerun()
                    else:
                        # Fallback to demo role if backend didn't return token
                        st.info("Backend login failed — using demo role (local only)")
                        st.session_state.current_user = {"username": username or role, "role": role}
                        st.session_state.auth_token = None
                        st.rerun()
                except Exception as e:
                    # If any error (API unreachable etc.), fallback to demo login
                    st.warning(f"Backend auth error: {str(e)} — falling back to demo login")
                    st.session_state.current_user = {"username": username or role, "role": role}
                    st.session_state.auth_token = None
                    st.rerun()
            if st.button("🔓 Logout"):
                st.session_state.current_user = None
                st.session_state.auth_token = None
                st.success("Logged out")
                st.rerun()

        if st.session_state.get("current_user"):
            cu = st.session_state.current_user
            st.markdown(f"**Current User:** {cu.get('username')} — **Role:** {cu.get('role')} ")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 Refresh All", use_container_width=True):
                st.rerun()
        
        with col2:
            if st.button("⚙️ Settings", use_container_width=True):
                st.session_state.show_settings = not st.session_state.get("show_settings", False)
        
        if st.session_state.get("show_settings", False):
            st.divider()
            render_settings_section()
        
        # Help section
        st.divider()
        st.markdown("### ❓ Help")
        with st.expander("How to use"):
            st.markdown("""
            1. **Upload CVs** - Drag and drop or select CV files
            2. **Track Progress** - Monitor job status in real-time
            3. **View Results** - Check completed ingestions
            4. **Chat** - Ask questions about candidates (coming soon)
            
            **Supported Formats:**
            - PDF, DOCX, DOC, TXT
            - JPG, PNG, TIFF (with OCR)
            """)
        
        with st.expander("Troubleshooting"):
            st.markdown("""
            **Can't upload files?**
            - Check API is running: `python3 backend/api.py`
            - Verify API key is correct
            - Check file format is supported
            
            **Jobs stuck in processing?**
            - Start worker: `python3 backend/ingest/worker.py`
            - Check logs: `tail -f ingestion_worker.log`
            """)
        
        st.divider()
        st.markdown("**Version:** 1.0.0")
        st.markdown("[📖 API Docs](http://localhost:8000/docs)")


if __name__ == "__main__":
    main()
