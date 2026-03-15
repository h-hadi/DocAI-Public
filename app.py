#!/usr/bin/env python3
"""DocAI — Gradio Web Interface with pipeline selector and dashboard."""

import threading
import traceback
from datetime import datetime
from pathlib import Path
from tempfile import gettempdir

import gradio as gr

from pipelines import PIPELINES, PIPELINE_LABELS
from present.word_export import export_to_word
from config import AVAILABLE_MODELS, estimate_cost
from html import escape as html_escape
from history import log_run, get_history, get_spending_summary, clear_history, get_error_log
from auth import (
    verify_login, is_password_expired, change_password,
    create_user, delete_user, list_users, toggle_expiry, get_user,
)

# Session state
_session_log: list[dict] = []
_last_result: dict = {}


def _log_event(event_type: str, message: str, status: str = "ok"):
    """Log an event to the session dashboard."""
    _session_log.append({
        "time": datetime.now().strftime("%H:%M:%S"),
        "type": event_type,
        "message": message,
        "status": status,
    })
    if len(_session_log) > 500:
        _session_log[:] = _session_log[-200:]


def analyze(
    folder_path: str,
    instruction: str,
    pipeline_key: str,
    model: str,
    request: gr.Request,
) -> tuple[str, str, str]:
    """Run selected pipeline on folder.

    Returns: (result_markdown, status_text, dashboard_html)
    """
    global _last_result

    # Check password expiry
    if request and request.username:
        user = get_user(request.username)
        if user and is_password_expired(user):
            return (
                "**Your password has expired.** Please go to the "
                "'Change Password' tab to set a new password before analyzing documents.",
                "Password expired",
                "",
            )

    if not folder_path.strip():
        return "Please enter a folder path.", "", ""
    if not pipeline_key:
        return "Please select a pipeline.", "", ""

    folder = Path(folder_path)
    if not folder.exists():
        _log_event("error", f"Folder not found: {folder_path}", "error")
        return f"**Error**: Folder not found: `{folder_path}`", "", ""

    # Get pipeline class
    pipeline_cls = PIPELINES.get(pipeline_key)
    if not pipeline_cls:
        return f"**Error**: Unknown pipeline: {pipeline_key}", "", ""

    pipeline = pipeline_cls()
    _log_event("pipeline", f"Running {pipeline.name} on {folder}")

    # Execute pipeline
    try:
        result = pipeline.execute(folder_path, instruction, model)
        _log_event("complete", f"{pipeline.name}: {result.files_processed} files", "ok")
    except Exception as e:
        _log_event("error", f"Pipeline failed: {e}", "error")
        dashboard = _build_dashboard_html()
        return f"**Error**: {e}\n\n```\n{traceback.format_exc()}\n```", "", dashboard

    # Store for export
    _last_result = {
        "result": result.output,
        "folder_path": folder_path,
        "instruction": instruction,
    }

    # Log errors
    for err in result.errors:
        _log_event("parse_error", err, "error")

    # Cost estimation
    input_tokens = result.metadata.get("total_tokens", 0)
    if not input_tokens and result.metadata.get("strategy"):
        input_tokens = 0  # tokens not tracked for this pipeline
    est_cost = estimate_cost(model, input_tokens)

    # Log to project history
    log_run(
        folder_path=folder_path,
        pipeline=pipeline_key,
        model=model,
        instruction=instruction,
        files_processed=result.files_processed,
        input_tokens=input_tokens,
        success=result.success,
        errors=result.errors,
    )
    _log_event("cost", f"Est. cost: ${est_cost:.4f} ({input_tokens:,} input tokens)")

    # Status bar
    status_parts = [
        f"Pipeline: {PIPELINE_LABELS.get(pipeline_key, pipeline_key)}",
        f"Files: {result.files_processed}",
        f"Model: {model}",
        f"Tokens: {input_tokens:,}",
        f"Est. Cost: ${est_cost:.4f}",
    ]
    if result.errors:
        status_parts.append(f"Errors: {len(result.errors)}")

    dashboard = _build_dashboard_html()
    return result.output, " | ".join(status_parts), dashboard


def _build_dashboard_html() -> str:
    """Build dashboard HTML from session log."""
    if not _session_log:
        return '<div style="padding: 20px; color: #6b7280; background: #ffffff; text-align: center;">No activity yet.</div>'

    html = ['<div style="font-family: system-ui, -apple-system, sans-serif; padding: 16px; background: #ffffff; color: #1f2937;">']
    html.append('<h3 style="color: #1e40af; font-weight: 600;">Processing Log</h3>')
    html.append(
        '<div style="max-height: 300px; overflow-y: auto; '
        'background: #1e293b; border: 1px solid #e5e7eb; border-radius: 6px; padding: 10px;">'
    )
    for event in reversed(_session_log[-30:]):
        color = "#10b981" if event["status"] == "ok" else "#ef4444"
        html.append(
            f'<div style="font-size: 13px; padding: 3px 0; font-family: Consolas, monospace; color: #f4f4f4;">'
            f'<span style="color: #a0a0a0;">{html_escape(event["time"])}</span> '
            f'<span style="color: {color}; font-weight: 600;">[{html_escape(event["type"])}]</span> '
            f'{html_escape(event["message"])}'
            f'</div>'
        )
    html.append('</div></div>')
    return "\n".join(html)


def _card(title: str, value: str, color: str, icon: str = "") -> str:
    """Generate a summary card HTML."""
    return (
        f'<div style="background: #ffffff; color: #1f2937; border: 1px solid #e5e7eb; border-radius: 10px; '
        f'padding: 18px 22px; min-width: 140px; text-align: center; flex: 1; '
        f'border-top: 4px solid {color}; box-shadow: 0 2px 8px rgba(0,0,0,0.06); '
        f'font-family: system-ui, sans-serif;">'
        f'<div style="font-size: 11px; color: #6b7280; text-transform: uppercase; letter-spacing: 0.5px;">'
        f'{icon} {title}</div>'
        f'<div style="font-size: 28px; font-weight: 700; color: {color}; margin-top: 6px;">{value}</div>'
        f'</div>'
    )


def _section_header(title: str) -> str:
    """Generate a styled section header."""
    return (
        f'<h3 style="margin: 28px 0 12px 0; padding-bottom: 8px; '
        f'border-bottom: 2px solid #e5e7eb; color: #1e40af; font-weight: 600;">{title}</h3>'
    )


def _styled_table(headers: list[str], rows: list[list[str]], aligns: list[str] | None = None) -> str:
    """Generate a styled table with alternating rows."""
    if not aligns:
        aligns = ["left"] * len(headers)
    html = ['<table style="width: 100%; border-collapse: collapse; font-size: 13px; margin-bottom: 16px; '
            'font-family: system-ui, sans-serif;">']
    html.append('<thead><tr style="background: #1e40af; color: #ffffff;">')
    for i, h in enumerate(headers):
        html.append(
            f'<th style="padding: 10px 12px; text-align: {aligns[i]}; font-weight: 600; '
            f'font-size: 12px; text-transform: uppercase; letter-spacing: 0.3px; color: #ffffff;">{h}</th>'
        )
    html.append('</tr></thead><tbody>')
    for idx, row in enumerate(rows):
        bg = "#f9fafb" if idx % 2 == 0 else "#ffffff"
        html.append(f'<tr style="background: {bg};">')
        for i, cell in enumerate(row):
            html.append(
                f'<td style="padding: 8px 12px; border-bottom: 1px solid #e5e7eb; '
                f'text-align: {aligns[i]}; color: #1f2937;">{cell}</td>'
            )
        html.append('</tr>')
    html.append('</tbody></table>')
    return "\n".join(html)


def _build_comprehensive_dashboard() -> str:
    """Build the comprehensive dashboard HTML with all stats, costs, history, and errors."""
    summary = get_spending_summary()
    history = get_history()
    errors = get_error_log()

    html = [
        '<div style="font-family: system-ui, -apple-system, sans-serif; '
        'padding: 20px; max-width: 1200px; margin: 0 auto; background: #ffffff; color: #1f2937;">'
    ]

    # Summary Cards
    html.append('<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); '
                'gap: 14px; margin-bottom: 28px;">')
    html.append(_card("Total Runs", str(summary["total_runs"]), "#1e40af", "\U0001f4ca"))
    html.append(_card("Total Tokens", f'{summary["total_tokens"]:,}', "#059669", "\U0001f4dd"))
    html.append(_card("Est. AI Cost", f'${summary["total_cost_usd"]:.2f}', "#7c3aed", "\U0001f4b0"))
    sr = (
        f'{round(summary["successful_runs"] * 100 / summary["total_runs"])}%'
        if summary["total_runs"] else "N/A"
    )
    html.append(_card("Success Rate", sr, "#10b981", "\u2705"))
    html.append(_card("Files Processed", f'{summary["total_files"]:,}', "#6366f1", "\U0001f4c1"))
    html.append(_card("Total Errors", str(summary["total_errors"]), "#f59e0b", "\u26a0\ufe0f"))
    html.append('</div>')

    # AI Rate Charges by Model
    if summary["by_model"]:
        html.append(_section_header("\U0001f4b3 AI Rate Charges by Model"))
        rows = []
        for model, data in summary["by_model"].items():
            rows.append([
                f'<strong>{html_escape(model)}</strong>',
                str(data["runs"]),
                f'{data["tokens"]:,}',
                f'${data["cost"]:.4f}',
                f'${data["cost"] / data["runs"]:.4f}' if data["runs"] else "$0.00",
            ])
        html.append(_styled_table(
            ["Model", "Runs", "Tokens", "Total Cost", "Avg Cost/Run"],
            rows,
            ["left", "right", "right", "right", "right"],
        ))

    # Token Spending by Pipeline
    if summary["by_pipeline"]:
        html.append(_section_header("\U0001f9ea Token Spending by Pipeline"))
        rows = []
        for pipe, data in summary["by_pipeline"].items():
            label = PIPELINE_LABELS.get(pipe, pipe)
            rows.append([
                f'<strong>{html_escape(label)}</strong>',
                str(data["runs"]),
                f'{data["tokens"]:,}',
                f'${data["cost"]:.4f}',
            ])
        html.append(_styled_table(
            ["Pipeline", "Runs", "Tokens", "Est. Cost"],
            rows,
            ["left", "right", "right", "right"],
        ))

    # Daily Spending Trend
    if summary["by_date"]:
        html.append(_section_header("\U0001f4c5 Daily Spending Trend"))
        rows = []
        max_cost = max(summary["by_date"].values()) if summary["by_date"] else 1
        for date, cost in sorted(summary["by_date"].items(), reverse=True)[:30]:
            bar_width = int((cost / max_cost) * 200) if max_cost > 0 else 0
            bar = (
                f'<div style="background: linear-gradient(90deg, #1e40af, #3b82f6); '
                f'height: 16px; width: {bar_width}px; border-radius: 3px; display: inline-block;"></div>'
            )
            rows.append([date, f'${cost:.4f}', bar])
        html.append(_styled_table(
            ["Date", "Est. Cost", ""],
            rows,
            ["left", "right", "left"],
        ))

    # Recent Runs
    if history:
        html.append(_section_header("\U0001f55b Recent Analysis Runs"))
        rows = []
        for r in history[:50]:
            ts = r.get("timestamp", "")[:19].replace("T", " ")
            status = "OK" if r.get("success") else "FAIL"
            status_color = "#10b981" if r.get("success") else "#ef4444"
            status_html = f'<span style="color: {status_color}; font-weight: 600;">{status}</span>'
            label = PIPELINE_LABELS.get(r.get("pipeline", ""), r.get("pipeline", ""))
            rows.append([
                f'<span style="font-size: 12px;">{ts}</span>',
                html_escape(label),
                html_escape(r.get("model", "")),
                str(r.get("files_processed", 0)),
                f'{r.get("input_tokens", 0):,}',
                f'${r.get("estimated_cost_usd", 0):.4f}',
                status_html,
            ])
        html.append(_styled_table(
            ["Time", "Pipeline", "Model", "Files", "Tokens", "Cost", "Status"],
            rows,
            ["left", "left", "left", "right", "right", "right", "center"],
        ))

    # Error Log
    if errors:
        html.append(_section_header("\u26a0\ufe0f Error Log"))
        rows = []
        for e in errors[:30]:
            ts = e.get("timestamp", "")[:19].replace("T", " ")
            rows.append([
                f'<span style="font-size: 12px;">{ts}</span>',
                html_escape(e.get("pipeline", "")),
                html_escape(e.get("model", "")),
                f'<span style="color: #ef4444;">{html_escape(e.get("error", ""))}</span>',
            ])
        html.append(_styled_table(
            ["Time", "Pipeline", "Model", "Error"],
            rows,
            ["left", "left", "left", "left"],
        ))

    # Session Processing Log
    if _session_log:
        html.append(_section_header("\U0001f4cb Session Processing Log"))
        html.append(
            '<div style="max-height: 250px; overflow-y: auto; '
            'background: #1e293b; border-radius: 8px; padding: 12px; font-family: Consolas, monospace;">'
        )
        for event in reversed(_session_log[-30:]):
            color = "#7fba72" if event["status"] == "ok" else "#f38ba8"
            html.append(
                f'<div style="font-size: 12px; padding: 2px 0; color: #f4f4f4;">'
                f'<span style="color: #a0a0a0;">{html_escape(event["time"])}</span> '
                f'<span style="color: {color}; font-weight: 600;">[{html_escape(event["type"])}]</span> '
                f'{html_escape(event["message"])}'
                f'</div>'
            )
        html.append('</div>')

    if not history and not _session_log:
        html.append(
            '<div style="text-align: center; padding: 60px 20px; color: #6b7280; background: #ffffff;">'
            '<div style="font-size: 48px; margin-bottom: 12px;">\U0001f4ca</div>'
            '<p style="font-size: 16px; color: #6b7280;">No activity yet. Analyze some documents to see your dashboard.</p>'
            '</div>'
        )

    html.append('</div>')
    return "\n".join(html)


def export_word_only() -> str | None:
    """Export the last analysis result as a Word document."""
    if not _last_result:
        return None
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = str(Path(gettempdir()) / f"DocAI_Report_{timestamp}.docx")
        export_to_word(
            _last_result["result"],
            _last_result["folder_path"],
            _last_result["instruction"],
            output_path=path,
        )
        _log_event("export", f"Word document exported: {path}")
        return path
    except Exception as e:
        _log_event("export", f"Export failed: {e}", "error")
        return None


def _browse_folder() -> str:
    """Open a native folder picker dialog (tkinter) and return the selected path."""
    result = [None]

    def _run_dialog():
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            folder = filedialog.askdirectory(title="Select Document Folder")
            root.destroy()
            result[0] = folder if folder else None
        except Exception:
            result[0] = None

    # tkinter must run on a separate thread to avoid blocking Gradio
    t = threading.Thread(target=_run_dialog)
    t.start()
    t.join(timeout=120)  # 2 minute timeout
    return result[0] or ""


def _gradio_auth(username: str, password: str) -> bool:
    """Gradio auth callback. Allows login even with expired password
    (expiry is enforced at the analysis level, not login)."""
    user = verify_login(username, password)
    return user is not None


_pw_change_attempts: dict[str, list[float]] = {}
_MAX_PW_ATTEMPTS = 5
_PW_LOCKOUT_SECONDS = 300  # 5 minutes


def _handle_change_password(old_pw: str, new_pw: str, confirm_pw: str, request: gr.Request) -> str:
    """Handle password change request. Username from session — users can only change their own."""
    import time

    if not request or not request.username:
        return "Authentication required."
    username = request.username

    # Rate limiting: max 5 attempts per 5 minutes
    now = time.time()
    attempts = _pw_change_attempts.get(username, [])
    attempts = [t for t in attempts if now - t < _PW_LOCKOUT_SECONDS]
    if len(attempts) >= _MAX_PW_ATTEMPTS:
        return "Too many attempts. Please wait 5 minutes before trying again."
    _pw_change_attempts[username] = attempts

    if not old_pw or not new_pw:
        return "All fields are required."
    if new_pw != confirm_pw:
        return "New passwords do not match."
    if len(new_pw) < 8:
        return "Password must be at least 8 characters."
    if not any(c.isupper() for c in new_pw):
        return "Password must contain at least one uppercase letter."
    if not any(c.isdigit() for c in new_pw):
        return "Password must contain at least one digit."
    if old_pw == new_pw:
        return "New password must be different from the current password."

    # Record attempt before trying
    _pw_change_attempts[username].append(now)

    if change_password(username, old_pw, new_pw):
        _pw_change_attempts.pop(username, None)  # Reset on success
        return "Password changed successfully."
    return "Current password is incorrect."


def _check_admin(request: gr.Request) -> str | None:
    """Return error message if user is not admin, None if OK."""
    if not request or not request.username:
        return "Authentication required."
    user = get_user(request.username)
    if not user or user.get("role") != "admin":
        return "Access denied. Admin privileges required."
    return None


def _handle_create_user(new_username: str, new_password: str, role: str, request: gr.Request) -> str:
    """Admin: create a new user."""
    err = _check_admin(request)
    if err:
        return err
    if not new_username or not new_password:
        return "Username and password are required."
    if len(new_password) < 8:
        return "Password must be at least 8 characters."
    if not any(c.isupper() for c in new_password):
        return "Password must contain at least one uppercase letter."
    if not any(c.isdigit() for c in new_password):
        return "Password must contain at least one digit."
    if create_user(new_username, new_password, role):
        return f"User '{new_username}' created successfully."
    return f"Username '{new_username}' already exists."


def _handle_delete_user(target_username: str, request: gr.Request) -> str:
    """Admin: delete a user."""
    err = _check_admin(request)
    if err:
        return err
    if not target_username:
        return "Please enter a username to delete."
    if delete_user(target_username):
        return f"User '{target_username}' deleted."
    return f"Cannot delete '{target_username}' (user not found or is admin)."


def _handle_toggle_expiry(target_username: str, disable: bool, request: gr.Request) -> str:
    """Admin: toggle password expiry for a user."""
    err = _check_admin(request)
    if err:
        return err
    if not target_username:
        return "Please enter a username."
    if toggle_expiry(target_username, disable):
        state = "disabled" if disable else "enabled"
        return f"Password expiry {state} for '{target_username}'."
    return f"User '{target_username}' not found."


def _build_users_table(request: gr.Request) -> str:
    """Build HTML table of all users for admin panel."""
    err = _check_admin(request)
    if err:
        return f"<p style='color:red;'>{err}</p>"
    users = list_users()
    if not users:
        return "<p>No users found.</p>"

    html = ['<table style="width:100%; border-collapse:collapse; font-size:14px; '
            'font-family: system-ui, sans-serif; background: #ffffff; color: #1f2937;">']
    html.append(
        '<tr style="background:#1e40af; color:#ffffff;">'
        '<th style="padding:10px 8px; border:1px solid #e5e7eb; color:#ffffff;">Username</th>'
        '<th style="padding:10px 8px; border:1px solid #e5e7eb; color:#ffffff;">Role</th>'
        '<th style="padding:10px 8px; border:1px solid #e5e7eb; color:#ffffff;">Created</th>'
        '<th style="padding:10px 8px; border:1px solid #e5e7eb; color:#ffffff;">Password Changed</th>'
        '<th style="padding:10px 8px; border:1px solid #e5e7eb; color:#ffffff;">Expiry Disabled</th>'
        '</tr>'
    )
    for idx, u in enumerate(users):
        expiry = "Yes" if u.get("password_expiry_disabled") else "No"
        created = u.get("created_at", "")[:19]
        changed = u.get("password_changed_at", "")[:19]
        bg = "#f9fafb" if idx % 2 == 0 else "#ffffff"
        html.append(
            f'<tr style="background:{bg};">'
            f'<td style="padding:6px 8px; border:1px solid #e5e7eb; color:#1f2937;">{html_escape(u["username"])}</td>'
            f'<td style="padding:6px 8px; border:1px solid #e5e7eb; color:#1f2937;">{html_escape(u["role"])}</td>'
            f'<td style="padding:6px 8px; border:1px solid #e5e7eb; color:#1f2937;">{created}</td>'
            f'<td style="padding:6px 8px; border:1px solid #e5e7eb; color:#1f2937;">{changed}</td>'
            f'<td style="padding:6px 8px; border:1px solid #e5e7eb; color:#1f2937;">{expiry}</td>'
            f'</tr>'
        )
    html.append('</table>')
    return "\n".join(html)


# --- Build the UI ---

_DOCAI_THEME = gr.themes.Default(
    primary_hue=gr.themes.Color(
        c50="#eff6ff", c100="#dbeafe", c200="#bfdbfe", c300="#93c5fd",
        c400="#60a5fa", c500="#3b82f6", c600="#2563eb", c700="#1d4ed8",
        c800="#1e40af", c900="#1e3a8a", c950="#172554",
    ),
    font=["system-ui", "-apple-system", "sans-serif"],
    font_mono=["Consolas", "monospace"],
)

_DOCAI_CSS = """
.gradio-container { max-width: 1280px !important; background: #ffffff !important; color: #1f2937 !important; }
.gradio-container .dark { background: #ffffff !important; color: #1f2937 !important; }
footer { display: none !important; }
.gr-button.primary { background: #1e40af !important; border-color: #1e40af !important; }
.gr-button.primary:hover { background: #1d4ed8 !important; }
.gr-button.secondary { border-color: #3b82f6 !important; color: #3b82f6 !important; }
.markdown-text, .prose { color: #1f2937 !important; }
label, .label-text { color: #1f2937 !important; }
input, textarea, select { color: #1f2937 !important; background: #ffffff !important; }
.tab-nav button { color: #1f2937 !important; }
.tab-nav button.selected { color: #1e40af !important; border-color: #1e40af !important; }
"""

with gr.Blocks(title="DocAI — Document Analysis") as demo:
    gr.HTML(
        '<div style="background: linear-gradient(135deg, #1e3a8a 0%, #1e40af 50%, #2563eb 100%); '
        'color: #ffffff; padding: 28px 32px; border-radius: 12px; margin-bottom: 16px; '
        'box-shadow: 0 4px 16px rgba(30,58,138,0.3); font-family: system-ui, sans-serif;">'
        '<h1 style="margin: 0; font-size: 32px; font-weight: 700; letter-spacing: -0.5px; color: #ffffff;">'
        '\U0001f4c4 DocAI</h1>'
        '<p style="margin: 8px 0 0 0; font-size: 15px; color: rgba(255,255,255,0.9); font-weight: 400;">'
        'Your personal AI-powered document analyst. Point to a folder, select a pipeline, '
        'get structured results in seconds.</p>'
        '</div>'
    )

    with gr.Tabs():
        # ===================== ANALYZE TAB =====================
        with gr.Tab("\U0001f50d Analyze", id="analyze"):
            gr.Markdown("### Select a folder and pipeline to begin analysis")
            with gr.Row():
                folder_input = gr.Textbox(
                    label="\U0001f4c2 Folder Path (paste path or click Browse)",
                    placeholder=r"C:\path\to\documents  — paste a path or click Browse \u2192",
                    scale=5,
                )
                browse_btn = gr.Button("\U0001f4c1 Browse", scale=1, variant="secondary", size="lg")
            with gr.Row():
                pipeline_input = gr.Dropdown(
                    label="Pipeline",
                    choices=list(PIPELINE_LABELS.keys()),
                    value="general",
                    scale=2,
                )
                model_input = gr.Dropdown(
                    label="Model",
                    choices=AVAILABLE_MODELS,
                    value="gpt-4o",
                    scale=1,
                )

            browse_btn.click(fn=_browse_folder, outputs=[folder_input])

            instruction_input = gr.Textbox(
                label="Instruction (optional — pipeline has smart defaults)",
                placeholder="e.g., Focus on revenue trends and flag any anomalies > 15%",
                lines=3,
            )

            with gr.Row():
                analyze_btn = gr.Button("Analyze", variant="primary", scale=2)

            status_bar = gr.Textbox(label="Status", interactive=False)
            analysis_output = gr.Markdown(label="Results")
            analyze_dashboard = gr.HTML(label="Processing Log")

            analyze_btn.click(
                fn=analyze,
                inputs=[folder_input, instruction_input, pipeline_input, model_input],
                outputs=[analysis_output, status_bar, analyze_dashboard],
            )

            gr.Markdown("---")
            export_btn = gr.Button("Export Last Result as Word Document")
            export_file = gr.File(label="Download")
            export_btn.click(fn=export_word_only, outputs=[export_file])

            gr.Examples(
                examples=[
                    [r"C:\Documents\financials", "Compare year-over-year revenue and expenses", "year_over_year", "gpt-4o"],
                    [r"C:\Documents\reports", "Summarize all documents and identify common themes", "summarizer", "claude-sonnet-4-6"],
                    [r"C:\Documents\letters", "Extract donor intent from gift letters", "donor_intent", "gemini-2.5-pro"],
                    [r"C:\Documents\data", "Detect patterns, trends, and anomalies in spreadsheets", "pta", "gpt-4o"],
                ],
                inputs=[folder_input, instruction_input, pipeline_input, model_input],
            )

        # ===================== PIPELINE INFO TAB =====================
        with gr.Tab("\U0001f9ea Pipelines", id="pipelines"):
            gr.Markdown("### Available Pipelines\n")
            for key, label in PIPELINE_LABELS.items():
                pipeline_cls = PIPELINES[key]
                p = pipeline_cls()
                accepted = ", ".join(t.value for t in p.accepted_types)
                gr.Markdown(
                    f"**{label}** (`{key}`)\n"
                    f"- {p.description}\n"
                    f"- Accepted file types: {accepted}\n"
                )

        # ===================== DASHBOARD TAB (Comprehensive) =====================
        with gr.Tab("\U0001f4ca Dashboard", id="dashboard"):
            dashboard_refresh = gr.Button("\U0001f504 Refresh Dashboard", variant="primary")
            dashboard_html = gr.HTML()
            dashboard_refresh.click(fn=_build_comprehensive_dashboard, outputs=[dashboard_html])

        # ===================== CHANGE PASSWORD TAB =====================
        with gr.Tab("\U0001f512 Password", id="change_password"):
            gr.Markdown("### Change Your Password")
            gr.Markdown(
                "Non-admin passwords expire every **14 days**. "
                "If your password has expired, change it here to regain access.\n\n"
                "**Requirements:** 8+ characters, at least one uppercase letter, at least one digit."
            )
            cp_username = gr.Textbox(label="Logged in as", interactive=False)
            cp_old_pw = gr.Textbox(label="Current Password", type="password")
            cp_new_pw = gr.Textbox(label="New Password", type="password")
            cp_confirm_pw = gr.Textbox(label="Confirm New Password", type="password")
            cp_btn = gr.Button("Change Password", variant="primary")
            cp_result = gr.Textbox(label="Result", interactive=False)
            cp_btn.click(
                fn=_handle_change_password,
                inputs=[cp_old_pw, cp_new_pw, cp_confirm_pw],
                outputs=[cp_result],
            )

        # ===================== ADMIN TAB =====================
        with gr.Tab("\u2699\ufe0f Admin", id="admin", visible=False) as admin_tab:
            gr.Markdown("### User Management (Admin Only)")
            gr.Markdown(
                "Only admin users can manage users. "
                "If you are not an admin, these actions will fail."
            )

            # Users list
            admin_refresh = gr.Button("Refresh User List")
            admin_users_html = gr.HTML()
            admin_refresh.click(fn=_build_users_table, outputs=[admin_users_html])

            gr.Markdown("---")

            # Create user
            gr.Markdown("#### Create User")
            with gr.Row():
                cu_username = gr.Textbox(label="Username", scale=2)
                cu_password = gr.Textbox(label="Password", type="password", scale=2)
                cu_role = gr.Dropdown(
                    label="Role", choices=["user", "admin"], value="user", scale=1
                )
            cu_btn = gr.Button("Create User")
            cu_result = gr.Textbox(label="Result", interactive=False)
            cu_btn.click(
                fn=_handle_create_user,
                inputs=[cu_username, cu_password, cu_role],
                outputs=[cu_result],
            )

            gr.Markdown("---")

            # Delete user
            gr.Markdown("#### Delete User")
            with gr.Row():
                du_username = gr.Textbox(label="Username to Delete", scale=3)
                du_btn = gr.Button("Delete User", variant="stop", scale=1)
            du_result = gr.Textbox(label="Result", interactive=False)
            du_btn.click(
                fn=_handle_delete_user,
                inputs=[du_username],
                outputs=[du_result],
            )

            gr.Markdown("---")

            # Toggle expiry
            gr.Markdown("#### Toggle Password Expiry")
            with gr.Row():
                te_username = gr.Textbox(label="Username", scale=2)
                te_disable = gr.Checkbox(label="Disable Expiry", value=False, scale=1)
                te_btn = gr.Button("Update Expiry Setting", scale=1)
            te_result = gr.Textbox(label="Result", interactive=False)
            te_btn.click(
                fn=_handle_toggle_expiry,
                inputs=[te_username, te_disable],
                outputs=[te_result],
            )


    # ===================== FOOTER =====================
    gr.HTML(
        '<div style="margin-top: 24px; padding: 16px 32px; '
        'background: linear-gradient(135deg, #1e3a8a 0%, #1e40af 100%); '
        'border-radius: 10px; text-align: center; '
        'box-shadow: 0 2px 8px rgba(30,58,138,0.2); font-family: system-ui, sans-serif;">'
        '<p style="margin: 0; color: #ffffff; font-size: 13px;">'
        'DocAI &mdash; Your Personal AI-Powered Document Analyst &mdash; '
        '<a href="https://github.com/hhadi" target="_blank" '
        'style="color: #bfdbfe; text-decoration: none; font-weight: 600;">'
        'Haidar Hadi</a>'
        '</p>'
        '</div>'
    )

    def _on_page_load(request: gr.Request):
        """Auto-fill username and show admin tab only for admin users."""
        username = request.username if request else ""
        is_admin = False
        if username:
            user = get_user(username)
            is_admin = bool(user and user.get("role") == "admin")
        return username, gr.update(visible=is_admin)

    demo.load(fn=_on_page_load, outputs=[cp_username, admin_tab])


if __name__ == "__main__":
    demo.launch(
        server_name="127.0.0.1",
        server_port=7860,
        auth=_gradio_auth,
        auth_message=(
            "DocAI Login — Enter your credentials.\n"
            "If your password has expired, change it in the 'Change Password' tab first."
        ),
        theme=_DOCAI_THEME,
        css=_DOCAI_CSS,
    )
