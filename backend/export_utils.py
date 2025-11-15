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
        title_text = "📋 Candidate Ranking Report"
        if jd_data and jd_data.get("job_title"):
            title_text += f" - {jd_data['job_title']}"
        elements.append(Paragraph(title_text, title_style))

        # Report metadata
        report_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        metadata_style = ParagraphStyle(
            "Metadata",
            parent=styles["Normal"],
            fontSize=9,
            textColor=colors.HexColor("#666666"),
            spaceAfter=12,
            alignment=TA_CENTER,
        )
        elements.append(Paragraph(f"Report Generated: {report_date}", metadata_style))
        elements.append(Spacer(1, 0.2 * inch))

        # JD Summary Section
        if jd_data:
            elements.append(Paragraph("<b>📌 Job Description Summary</b>", styles["Heading2"]))
            
            # Create job details table
            jd_details = [
                ["Field", "Value"],
                ["Job Title", jd_data.get('job_title', 'N/A')],
                ["Company", jd_data.get('company', 'N/A')],
                ["Location", jd_data.get('location', 'N/A')],
                ["Department", jd_data.get('department', 'N/A')],
                ["Min. Experience", f"{jd_data.get('experience', {}).get('minimum_years', 'N/A')} years"],
                ["Education", jd_data.get('education', {}).get('degree_level', 'N/A')],
            ]
            
            jd_table = Table(jd_details, colWidths=[1.5 * inch, 4.0 * inch])
            jd_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c5aa0")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, 0), 11),
                        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 1), (-1, -1), 10),
                        ("GRID", (0, 0), (-1, -1), 1, colors.HexColor("#cccccc")),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f9f9f9"), colors.white]),
                        ("TOPPADDING", (0, 0), (-1, -1), 8),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ]
                )
            )
            elements.append(jd_table)
            
            # Skills section
            skills_data = jd_data.get("skills", {})
            if skills_data:
                elements.append(Spacer(1, 0.2 * inch))
                elements.append(Paragraph("<b>Required Skills</b>", styles["Heading3"]))
                
                must_have = skills_data.get("must_have", [])
                nice_to_have = skills_data.get("nice_to_have", [])
                
                skills_text = ""
                if must_have:
                    skills_text += f"<b>Must-Have:</b> {', '.join(must_have[:10])}"
                    if len(must_have) > 10:
                        skills_text += f", ... and {len(must_have) - 10} more<br/>"
                    else:
                        skills_text += "<br/>"
                
                if nice_to_have:
                    skills_text += f"<b>Nice-to-Have:</b> {', '.join(nice_to_have[:10])}"
                    if len(nice_to_have) > 10:
                        skills_text += f", ... and {len(nice_to_have) - 10} more"
                
                if skills_text:
                    elements.append(Paragraph(skills_text, styles["Normal"]))
            
            elements.append(Spacer(1, 0.3 * inch))

        # Summary Statistics
        elements.append(Paragraph("<b>📊 Ranking Summary</b>", styles["Heading2"]))
        
        top_candidates = results[:top_k] if results else []
        if top_candidates:
            avg_score = sum(r.get('final_score', 0) if 'final_score' in r else r.get('score', 0) for r in top_candidates) / len(top_candidates)
            top_score = max(r.get('final_score', 0) if 'final_score' in r else r.get('score', 0) for r in top_candidates) if top_candidates else 0
            
            summary_data = [
                ["Metric", "Value"],
                ["Total Candidates Evaluated", str(len(results))],
                ["Top Candidates Shown", str(len(top_candidates))],
                ["Highest Score", f"{top_score:.2%}"],
                ["Average Score (Top 10)", f"{avg_score:.2%}"],
            ]
            
            summary_table = Table(summary_data, colWidths=[2.5 * inch, 2.5 * inch])
            summary_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c5aa0")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, 0), 11),
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        ("FONTSIZE", (0, 1), (-1, -1), 10),
                        ("GRID", (0, 0), (-1, -1), 1, colors.HexColor("#cccccc")),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f9f9f9"), colors.white]),
                        ("TOPPADDING", (0, 0), (-1, -1), 10),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                    ]
                )
            )
            elements.append(summary_table)

        # Top Candidates Table
        elements.append(Spacer(1, 0.3 * inch))
        elements.append(Paragraph("<b>🎯 Top Candidates</b>", styles["Heading2"]))

        table_data = [["Rank", "Candidate Name", "Final Score", "Matched Must", "Missing Must", "Est. Exp."]]
        
        for idx, result in enumerate(top_candidates, 1):
            final_score = result.get('final_score', 0) if 'final_score' in result else result.get('score', 0)
            matched = ", ".join(result.get("matched_must", [])[:2])
            missing = ", ".join(result.get("missing_must", [])[:2])
            
            if len(result.get("missing_must", [])) > 2:
                missing += f" +{len(result.get('missing_must', [])) - 2}"
            if len(result.get("matched_must", [])) > 2:
                matched += f" +{len(result.get('matched_must', [])) - 2}"

            exp_years = result.get("details", {}).get("cv_years_est", "N/A")
            
            table_data.append(
                [
                    str(idx),
                    result.get("candidate_name", "Unknown")[:25],
                    f"{final_score:.1%}",
                    matched or "None",
                    missing or "None",
                    str(exp_years),
                ]
            )

        table = Table(table_data, colWidths=[0.5 * inch, 1.8 * inch, 1.0 * inch, 1.3 * inch, 1.3 * inch, 0.6 * inch])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f4788")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("ALIGN", (2, 0), (2, -1), "CENTER"),
                    ("ALIGN", (5, 0), (5, -1), "CENTER"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 11),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                    ("TOPPADDING", (0, 1), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
                    ("GRID", (0, 0), (-1, -1), 1, colors.HexColor("#666666")),
                    ("FONTSIZE", (0, 1), (-1, -1), 9),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
                ]
            )
        )
        elements.append(table)

        # Footer
        elements.append(Spacer(1, 0.4 * inch))
        footer_style = ParagraphStyle(
            "Footer",
            parent=styles["Normal"],
            fontSize=8,
            textColor=colors.HexColor("#999999"),
            alignment=TA_CENTER,
        )
        footer_text = f"ATS Report | Generated: {report_date}<br/>This report contains confidential information intended for authorized hiring team members only."
        elements.append(Paragraph(footer_text, footer_style))

        # Build PDF
        doc.build(elements)
        logger.info(f"PDF exported to {output_path}")
        return output_path

    except Exception as e:
        logger.error(f"PDF export failed: {e}")
        raise
