# 🔗 Chat & Export Integration Guide

**Quick reference for integrating new chat, RBAC, and export features into your ATS workflow.**

---

## 🎯 Integration Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    Web UI (Streamlit)                           │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │  Chat Tab       │  │  JD Matching    │  │  Export Section │ │
│  │                 │  │  Results        │  │                 │ │
│  │ • New Session   │  │ • Ranking Table │  │ • Format Select │ │
│  │ • Load History  │  │ • Scores        │  │ • Download Btn  │ │
│  │ • Chat Display  │  │ • Sources       │  │ • Status        │ │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘ │
│           │                    │                     │           │
└───────────┼────────────────────┼─────────────────────┼───────────┘
            │                    │                     │
         HTTP API Calls      HTTP API Calls      HTTP API Calls
            │                    │                     │
┌───────────▼────────────────────▼─────────────────────▼───────────┐
│                    FastAPI Backend                               │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ Authentication (/auth/login, /auth/me)                   │   │
│  │   ↓                                                      │   │
│  │ Chat Endpoints (/chat, /chat/{session_id})              │   │
│  │   ↓                                                      │   │
│  │ Chat Session Management (chat_session.py)               │   │
│  │   ↓                                                      │   │
│  │ SQLite: chat_sessions.db (persistent storage)           │   │
│  │   ↓                                                      │   │
│  │ RBAC Middleware (rbac.py)                               │   │
│  │   ↓                                                      │   │
│  │ Export Endpoints (/export)                              │   │
│  │   ↓                                                      │   │
│  │ Export Utils (export_utils.py)                          │   │
│  │   ↓                                                      │   │
│  │ File Output (./data/exports/)                           │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🔐 Authentication Flow

### 1. Login (User not authenticated)

```
[Web UI] → POST /auth/login
├─ username: "recruiter@example.com"
└─ password: "secure_password"
    ↓
[API] → Verify credentials against RBAC database
    ↓
[Response] ← {token: "user-id-uuid", role: "recruiter", ...}
    ↓
[Session] → Store token in st.session_state.auth_token
```

### 2. Using Token (All subsequent requests)

```
[Web UI] → Any API call with header:
├─ Authorization: Bearer {token}
└─ Content-Type: application/json
    ↓
[API] → Verify token via /auth/me
    ├─ Extract user_id from token
    ├─ Check has_permission(user_id, required_permission)
    └─ Allow/Deny request
```

---

## 💬 Chat Integration

### Architecture

```
User Question
    ↓
[render_chat_section()] in web/app.py
    ├─ Initialize session if needed
    ├─ Display chat history
    └─ Handle user input
        ↓
POST /chat endpoint
    ├─ Create session (if new)
    ├─ Add user message
    ├─ Generate RAG answer via generate_rag_answer()
    ├─ Add assistant message
    └─ Return ChatResponse
        ↓
[ChatSession.add_message()] in backend/chat_session.py
    ├─ Append to in-memory list
    ├─ Persist to SQLite (chat_sessions, chat_messages tables)
    └─ Return message_id
        ↓
Update UI with:
├─ Assistant answer
├─ Source citations
├─ Timestamp
└─ Session ID
```

### Code Example: Sending a Chat Message

**Web UI (web/app.py):**
```python
def render_chat_section():
    # User input
    question = st.text_input("Your Question")
    
    if st.button("Send"):
        response = make_api_call(
            "POST",
            "/chat",
            json={
                "session_id": st.session_state.current_session_id,
                "question": question,
                "top_k": 10
            }
        )
        
        # Update UI
        st.session_state.current_session_id = response["session_id"]
        st.session_state.chat_history.append({
            "question": question,
            "answer": response["answer"],
            "sources": response["sources"],
            "timestamp": datetime.now()
        })
```

**API Backend (backend/api.py):**
```python
@app.post("/chat")
def chat_endpoint(request: ChatRequest):
    try:
        # Create or retrieve session
        if request.session_id:
            session = get_session(request.session_id)
        else:
            session = create_session(
                user_id=current_user["user_id"],
                title=f"Chat - {datetime.now().isoformat()}"
            )
        
        # Add user message
        session.add_message(
            role="user",
            content=request.question,
            sources=[]
        )
        
        # Generate answer
        answer_response = generate_rag_answer(
            question=request.question,
            top_k=request.top_k,
            llm_model="phi4-mini:latest"
        )
        
        # Add assistant message
        session.add_message(
            role="assistant",
            content=answer_response["answer"],
            sources=answer_response["sources"]
        )
        
        # Persist
        session.save()
        
        return ChatResponse(
            session_id=session.session_id,
            message_id=session.messages[-1]["id"],
            answer=answer_response["answer"],
            sources=answer_response["sources"],
            timestamp=datetime.now()
        )
```

### Session Persistence

```
First Request:
┌─────────────────────────────────────┐
│ POST /chat                          │
│ {session_id: null, question: "..."}│
└────────────┬────────────────────────┘
             ↓
        Create new ChatSession
        Generate UUID: abc-123-def
        Save to SQLite
             ↓
        Return {session_id: "abc-123-def", ...}

Second Request (same conversation):
┌─────────────────────────────────────┐
│ POST /chat                          │
│ {session_id: "abc-123-def", ...}    │
└────────────┬────────────────────────┘
             ↓
        Load existing ChatSession
        Append new message
        Save to SQLite
             ↓
        Return {session_id: "abc-123-def", ...}
```

---

## 📥 Export Integration

### Export Flow

```
Ranking Results from JD Matching
    ↓
[render_jd_matching_section()] in web/app.py
    ├─ Display ranking table
    ├─ Show export format selector
    └─ Handle export button click
        ↓
POST /export endpoint
    ├─ Validate results format
    ├─ Validate selected format (csv/xlsx/json/pdf)
    └─ Call appropriate export function
        ↓
[export_utils.py] - Process format
    ├─ CSV: pandas → CSV file
    ├─ XLSX: openpyxl → Excel file
    ├─ JSON: json.dumps → JSON file
    └─ PDF: reportlab → PDF file
        ↓
Output to ./data/exports/
    ├─ Filename: [JD_Title]_[TIMESTAMP].[ext]
    └─ Return file_path
        ↓
[Web UI]
    ├─ Receive file_path
    ├─ Create download button
    └─ User downloads file
```

### Code Example: Export Section

**Web UI (web/app.py):**
```python
def render_jd_matching_section():
    # ... existing ranking display code ...
    
    # Export Section
    st.markdown("### 📥 Export Results")
    
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        export_format = st.selectbox(
            "Select Export Format",
            ["CSV", "XLSX", "JSON", "PDF"],
            key="export_format"
        )
    
    with col2:
        if st.button("📤 Export", use_container_width=True):
            with st.spinner("Exporting..."):
                response = make_api_call(
                    "POST",
                    "/export",
                    json={
                        "results": st.session_state.ranking_results,
                        "jd_data": st.session_state.jd_data,
                        "format": export_format.lower()
                    }
                )
                
                if response and "file_path" in response:
                    file_path = response["file_path"]
                    file_size = response["file_size"]
                    
                    st.success(f"✅ Exported: {file_path}")
                    st.info(f"📦 Size: {file_size:,} bytes")
                    
                    # For development: show file access info
                    st.code(f"File saved to: {file_path}")
```

**API Backend (backend/api.py):**
```python
@app.post("/export")
def export_endpoint(request: ExportRequest):
    try:
        # Validate format
        if request.format not in ["csv", "xlsx", "json", "pdf"]:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid format: {request.format}"
            )
        
        # Call appropriate export function
        if request.format == "csv":
            file_path = export_csv(
                results=request.results,
                jd_title=request.jd_data.get("title", "Export"),
                output_path="./data/exports/"
            )
        
        elif request.format == "xlsx":
            file_path = export_xlsx(
                results=request.results,
                jd_data=request.jd_data,
                jd_title=request.jd_data.get("title", "Export"),
                output_path="./data/exports/"
            )
        
        elif request.format == "json":
            file_path = export_json(
                results=request.results,
                jd_data=request.jd_data,
                output_path="./data/exports/"
            )
        
        elif request.format == "pdf":
            file_path = export_pdf(
                results=request.results,
                jd_data=request.jd_data,
                output_path="./data/exports/",
                top_k=10
            )
        
        # Get file stats
        file_size = os.path.getsize(file_path)
        
        return {
            "file_path": file_path,
            "format": request.format,
            "file_size": file_size,
            "created_at": datetime.now().isoformat()
        }
```

### Export Formats Reference

| Format | Best For | Features |
|--------|----------|----------|
| **CSV** | Data analysis, spreadsheets | Lightweight, universal compatibility |
| **XLSX** | Excel workflows, multi-sheet reports | Formatted tables, multiple sheets |
| **JSON** | API integration, data exchange | Structured, includes metadata |
| **PDF** | Professional reports, printing | Styled, professional appearance |

---

## 🛡️ RBAC Integration

### Permission Checks

**In API endpoints:**
```python
@app.post("/chat")
def chat_endpoint(request: ChatRequest):
    # Get current user
    current_user = authenticate_request(request.headers)
    
    # Check permission
    if not has_permission(current_user["user_id"], "search_cv"):
        raise HTTPException(
            status_code=403,
            detail="Permission denied: search_cv required"
        )
    
    # Proceed with endpoint logic
    ...

@app.post("/export")
def export_endpoint(request: ExportRequest):
    # Check permission
    if not has_permission(current_user["user_id"], "export_results"):
        raise HTTPException(
            status_code=403,
            detail="Permission denied: export_results required"
        )
    ...
```

**In Web UI:**
```python
# Get user permissions
response = requests.get(
    "http://localhost:8000/auth/me",
    headers={"Authorization": f"Bearer {token}"}
)

user_data = response.json()
permissions = user_data.get("permissions", [])

# Conditionally show UI elements
if "export_results" in permissions:
    st.button("📥 Export Results")
else:
    st.info("❌ Export not available for your role")
```

### Default Roles & Permissions

**Admin** (8 permissions)
- `upload_cv` - Upload and ingest CVs
- `search_cv` - Search candidates
- `parse_jd` - Parse job descriptions
- `rank_candidates` - Run rankings
- `export_results` - Export data
- `view_analytics` - View analytics
- `manage_users` - Create/manage users
- `manage_settings` - Modify settings

**Recruiter** (6 permissions)
- `upload_cv`
- `search_cv`
- `parse_jd`
- `rank_candidates`
- `export_results`
- `view_analytics`

**Viewer** (2 permissions)
- `search_cv` (read-only)
- `view_analytics` (read-only)

---

## 🗄️ Database Management

### View Chat Sessions

```bash
# Connect to SQLite
sqlite3 ./data/chat_sessions.db

# List all sessions
SELECT session_id, user_id, title, created_at FROM chat_sessions LIMIT 10;

# Count messages per session
SELECT session_id, COUNT(*) as message_count 
FROM chat_messages 
GROUP BY session_id;

# View specific session messages
SELECT role, content, created_at 
FROM chat_messages 
WHERE session_id = 'abc-123-def' 
ORDER BY created_at;
```

### View RBAC Data

```bash
# Connect to SQLite
sqlite3 ./data/rbac.db

# List all users
SELECT user_id, username, email, role, created_at FROM users;

# List available roles
SELECT role_name, description, permissions_json FROM roles;

# Check specific user permissions
SELECT permissions_json 
FROM roles 
WHERE role_name = (SELECT role FROM users WHERE username = 'recruiter1');
```

### Clear Data (Development Only)

```bash
# ⚠️ WARNING: This will delete all data!

# Clear chat sessions
rm ./data/chat_sessions.db

# Clear RBAC data
rm ./data/rbac.db

# Clear exports
rm -rf ./data/exports/*

# Restart API - databases will be recreated
python3 backend/api.py
```

---

## 🔧 Troubleshooting

### Issue: Chat endpoint returns "Permission Denied"

**Cause:** User doesn't have `search_cv` permission

**Solution:**
```python
# Check user permissions
import sqlite3
conn = sqlite3.connect('./data/rbac.db')
cursor = conn.cursor()

cursor.execute('''
    SELECT role FROM users WHERE username = 'your_username'
''')
user_role = cursor.fetchone()[0]

cursor.execute('''
    SELECT permissions_json FROM roles WHERE role_name = ?
''', (user_role,))
permissions_str = cursor.fetchone()[0]

print("Current permissions:", permissions_str)

# Promote user to recruiter role
cursor.execute('''
    UPDATE users SET role = 'recruiter' WHERE username = 'your_username'
''')
conn.commit()
```

### Issue: Export fails with "FileNotFoundError"

**Cause:** Export directory doesn't exist

**Solution:**
```bash
mkdir -p ./data/exports
chmod 755 ./data/exports
```

### Issue: PDF export has basic formatting

**Cause:** `reportlab` not installed

**Solution:**
```bash
pip install reportlab==4.0.9
```

### Issue: Session not persisting across page reloads

**Cause:** `st.session_state` is ephemeral; needs API call

**Solution:**
```python
# WRONG - data lost on page reload
st.session_state.chat_history = []

# CORRECT - data persists via API
response = requests.get(
    f"http://localhost:8000/chat/{session_id}",
    headers={"Authorization": f"Bearer {token}"}
)
messages = response.json()["messages"]
```

---

## 📊 Data Flow Examples

### Complete Chat Flow

```
1. User opens "💬 Chat" tab
   ↓
2. Streamlit calls render_chat_section()
   ↓
3. User enters question: "Find Python developers"
   ↓
4. User clicks "🔍 Search & Answer"
   ↓
5. make_api_call() sends:
   POST /chat {
     "session_id": null (or existing UUID),
     "question": "Find Python developers",
     "top_k": 10
   }
   ↓
6. API receives request:
   - Creates new ChatSession or loads existing
   - Adds user message to session
   - Calls generate_rag_answer()
   - Adds assistant message to session
   - Persists to SQLite
   ↓
7. API returns ChatResponse:
   {
     "session_id": "abc-123-def",
     "answer": "Found 5 candidates...",
     "sources": [...],
     "timestamp": "2025-11-15T13:19:11Z"
   }
   ↓
8. Streamlit updates UI:
   - Stores session_id for future requests
   - Adds to chat_history
   - Displays answer + sources
   ↓
9. User asks follow-up question
   ↓
10. Repeat from step 4 using same session_id
```

### Complete Export Flow

```
1. User views ranking results
   ↓
2. User selects export format (e.g., "XLSX")
   ↓
3. User clicks "📤 Export"
   ↓
4. make_api_call() sends:
   POST /export {
     "results": [{rank: 1, candidate_name: "...", score: 0.95, ...}],
     "jd_data": {"title": "Senior Backend Developer", ...},
     "format": "xlsx"
   }
   ↓
5. API receives request:
   - Validates format (xlsx ✓)
   - Calls export_xlsx()
   ↓
6. export_xlsx() creates:
   - New workbook with openpyxl
   - "Rankings" sheet with styled table
   - "JD Info" sheet with requirements
   - "Summary" sheet with statistics
   - Saves to ./data/exports/Senior Backend Developer_20251115_131911.xlsx
   ↓
7. API returns ExportResponse:
   {
     "file_path": "./data/exports/Senior Backend Developer_20251115_131911.xlsx",
     "format": "xlsx",
     "file_size": 12345,
     "created_at": "2025-11-15T13:19:11Z"
   }
   ↓
8. Streamlit displays:
   - Success message: "✅ Exported to file"
   - File path and size
   - Download button (for local dev)
   ↓
9. User can download file from ./data/exports/
```

---

## ✅ Integration Checklist

Before deploying to production, verify:

- [ ] API server starts without errors: `python3 backend/api.py`
- [ ] Web UI loads and connects to API
- [ ] Chat endpoint creates sessions: `GET /chat?limit=10`
- [ ] RBAC database has default roles
- [ ] Export creates files in `./data/exports/`
- [ ] All permissions checks working
- [ ] Token-based auth working
- [ ] Database files created: `chat_sessions.db`, `rbac.db`
- [ ] Error handling displays proper messages
- [ ] Tests pass: `python test_new_features.py`

---

## 📞 Quick Reference

| Task | Command |
|------|---------|
| Start API | `python3 backend/api.py` |
| Start Web UI | `cd web && streamlit run app.py` |
| Run tests | `python test_new_features.py` |
| View API docs | `http://localhost:8000/docs` |
| Check chat DB | `sqlite3 ./data/chat_sessions.db` |
| Check RBAC DB | `sqlite3 ./data/rbac.db` |
| List exports | `ls -lh ./data/exports/` |
| View API logs | `tail -f backend.log` |

---

**Last Updated:** November 15, 2025
**Version:** 1.0.0
**Status:** Production Ready ✅
