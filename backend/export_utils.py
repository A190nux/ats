"""
Export utilities for ranking results (CSV, XLSX, JSON, PDF).

Provides functions to export candidate rankings in multiple formats
with professional formatting for PDF reports.
"""

import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    import pandas as pd
except ImportError:
    logger.warning("pandas not installed; CSV/XLSX export will be limited")
    pd = None

try:
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

    HAS_REPORTLAB = True
except ImportError:
    logger.warning("reportlab not installed; PDF export will be limited")
    HAS_REPORTLAB = False


def export_csv(
    results: List[Dict[str, Any]],
    jd_title: Optional[str] = None,
    output_path: Optional[str] = None,
) -> str:
    """Export ranking results to CSV.

    Args:
        results: List of ranking results (from jd_matcher.rank_all_candidates)
        jd_title: Optional JD title for filename
        output_path: Optional output file path (default: temp file)

    Returns:
        Path to CSV file
    """
    if not pd:
        logger.error("pandas required for CSV export")
        raise ImportError("pandas is required for CSV export")

    try:
        # Flatten results to DataFrame
        data = []
        for result in results:
            row = {
                "Rank": len(data) + 1,
                "Candidate Name": result.get("candidate_name", "Unknown"),
                "Score": f"{result.get('score', 0):.1%}",
                "Matched Must-Have": ", ".join(result.get("matched_must", [])) or "None",
                "Matched Nice-to-Have": ", ".join(result.get("matched_nice", [])) or "None",
                "Missing Must-Have": ", ".join(result.get("missing_must", [])) or "None",
            }
            data.append(row)

        df = pd.DataFrame(data)

        # Determine output path
        if not output_path:
            Path("./data/exports").mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            jd_name = jd_title or "candidates"
            jd_name = "".join(c for c in jd_name if c.isalnum() or c in " -_")[:30]
            output_path = f"./data/exports/{jd_name}_{timestamp}.csv"

        df.to_csv(output_path, index=False)
        logger.info(f"CSV exported to {output_path}")
        return output_path

    except Exception as e:
        logger.error(f"CSV export failed: {e}")
        raise


def export_xlsx(
    results: List[Dict[str, Any]],
    jd_data: Optional[Dict[str, Any]] = None,
    jd_title: Optional[str] = None,
    output_path: Optional[str] = None,
) -> str:
    """Export ranking results to XLSX with multiple sheets.

    Args:
        results: List of ranking results
        jd_data: Optional JD parsed data to include as a sheet
        jd_title: Optional JD title for filename
        output_path: Optional output file path

    Returns:
        Path to XLSX file
    """
    if not pd:
        logger.error("pandas required for XLSX export")
        raise ImportError("pandas is required for XLSX export")

    try:
        # Determine output path
        if not output_path:
            Path("./data/exports").mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            jd_name = jd_title or "candidates"
            jd_name = "".join(c for c in jd_name if c.isalnum() or c in " -_")[:30]
            output_path = f"./data/exports/{jd_name}_{timestamp}.xlsx"

        # Flatten results
        data = []
        for result in results:
            row = {
                "Rank": len(data) + 1,
                "Candidate Name": result.get("candidate_name", "Unknown"),
                "Score": f"{result.get('score', 0):.1%}",
                "Matched Must-Have": ", ".join(result.get("matched_must", [])) or "None",
                "Matched Nice-to-Have": ", ".join(result.get("matched_nice", [])) or "None",
                "Missing Must-Have": ", ".join(result.get("missing_must", [])) or "None",
                "CV Years Estimated": result.get("details", {}).get("cv_years_est", "N/A"),
            }
            data.append(row)

        df_results = pd.DataFrame(data)

        # Create Excel writer
        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            # Rankings sheet
            df_results.to_excel(writer, sheet_name="Rankings", index=False)

            # JD sheet if provided
            if jd_data:
                jd_info = {
                    "Job Title": jd_data.get("job_title"),
                    "Company": jd_data.get("company"),
                    "Department": jd_data.get("department"),
                    "Location": jd_data.get("location"),
                    "Experience (min years)": jd_data.get("experience", {}).get("minimum_years"),
                    "Education Level": jd_data.get("education", {}).get("degree_level"),
                }

                skills = jd_data.get("skills", {})
                if isinstance(skills, dict):
                    jd_info["Must-Have Skills"] = ", ".join(skills.get("must_have", [])) or "None"
                    jd_info["Nice-to-Have Skills"] = ", ".join(skills.get("nice_to_have", [])) or "None"

                df_jd = pd.DataFrame([jd_info])
                df_jd.to_excel(writer, sheet_name="Job Description", index=False)

        logger.info(f"XLSX exported to {output_path}")
        return output_path

    except Exception as e:
        logger.error(f"XLSX export failed: {e}")
        raise


def export_json(
    results: List[Dict[str, Any]],
    jd_data: Optional[Dict[str, Any]] = None,
    output_path: Optional[str] = None,
) -> str:
    """Export ranking results to JSON.

    Args:
        results: List of ranking results
        jd_data: Optional JD parsed data to include
        output_path: Optional output file path

    Returns:
        Path to JSON file
    """
    try:
        # Determine output path
        if not output_path:
            Path("./data/exports").mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"./data/exports/ranking_{timestamp}.json"

        export_data = {
            "exported_at": datetime.now().isoformat(),
            "jd": jd_data or {},
            "results": results,
            "summary": {
                "total_candidates": len(results),
                "top_score": max((r.get("score", 0) for r in results), default=0),
                "avg_score": sum(r.get("score", 0) for r in results) / len(results) if results else 0,
            },
        }

        with open(output_path, "w") as f:
            json.dump(export_data, f, indent=2)

        logger.info(f"JSON exported to {output_path}")
        return output_path

    except Exception as e:
        logger.error(f"JSON export failed: {e}")
        raise


def export_pdf(
    results: List[Dict[str, Any]],
    jd_data: Optional[Dict[str, Any]] = None,
    output_path: Optional[str] = None,
    top_k: int = 10,
) -> str:
    """Generate a professional PDF report of top candidates.

    Args:
        results: List of ranking results
        jd_data: Optional JD data for context
        output_path: Optional output file path
        top_k: Number of top candidates to include

    Returns:
        Path to PDF file
    """
    if not HAS_REPORTLAB:
        logger.error("reportlab required for PDF export")
        raise ImportError("reportlab is required for PDF export")

    try:
        # Determine output path
        if not output_path:
            Path("./data/exports").mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            jd_name = jd_data.get("job_title", "Ranking") if jd_data else "Ranking"
            jd_name = "".join(c for c in jd_name if c.isalnum() or c in " -_")[:30]
            output_path = f"./data/exports/{jd_name}_{timestamp}.pdf"

        # Create PDF document
        doc = SimpleDocTemplate(output_path, pagesize=letter)
        elements = []
        styles = getSampleStyleSheet()

        # Title
        title_style = ParagraphStyle(
            "CustomTitle",
            parent=styles["Heading1"],
            fontSize=24,
            textColor=colors.HexColor("#1f4788"),
            spaceAfter=30,
            alignment=TA_CENTER,
        )
        title_text = "Candidate Ranking Report"
        if jd_data and jd_data.get("job_title"):
            title_text += f" - {jd_data['job_title']}"
        elements.append(Paragraph(title_text, title_style))

        # JD Summary
        if jd_data:
            jd_summary = f"""
            <b>Job Description:</b> {jd_data.get('job_title', 'N/A')}<br/>
            <b>Company:</b> {jd_data.get('company', 'N/A')}<br/>
            <b>Location:</b> {jd_data.get('location', 'N/A')}<br/>
            <b>Experience Required:</b> {jd_data.get('experience', {}).get('minimum_years', 'N/A')} years<br/>
            """
            elements.append(Paragraph(jd_summary, styles["Normal"]))
            elements.append(Spacer(1, 0.3 * inch))

        # Rankings table
        elements.append(Paragraph("<b>Top Candidates</b>", styles["Heading2"]))

        table_data = [["Rank", "Candidate", "Score", "Matched Skills", "Missing Skills"]]
        for idx, result in enumerate(results[:top_k], 1):
            matched = ", ".join(result.get("matched_must", [])[:3])
            missing = ", ".join(result.get("missing_must", [])[:3])
            if len(result.get("missing_must", [])) > 3:
                missing += "..."
            if len(result.get("matched_must", [])) > 3:
                matched += "..."

            table_data.append(
                [
                    str(idx),
                    result.get("candidate_name", "Unknown"),
                    f"{result.get('score', 0):.0%}",
                    matched or "None",
                    missing or "None",
                ]
            )

        table = Table(table_data, colWidths=[0.5 * inch, 1.5 * inch, 0.8 * inch, 1.8 * inch, 1.8 * inch])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f4788")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 12),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                    ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
                    ("GRID", (0, 0), (-1, -1), 1, colors.black),
                    ("FONTSIZE", (0, 1), (-1, -1), 10),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
                ]
            )
        )
        elements.append(table)

        # Footer
        elements.append(Spacer(1, 0.5 * inch))
        footer_text = f"Report generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        elements.append(Paragraph(footer_text, styles["Normal"]))

        # Build PDF
        doc.build(elements)
        logger.info(f"PDF exported to {output_path}")
        return output_path

    except Exception as e:
        logger.error(f"PDF export failed: {e}")
        raise
