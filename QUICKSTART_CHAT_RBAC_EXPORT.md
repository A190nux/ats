# Chat, RBAC & Export Quick Start Guide

## Getting Started

### 1. Install Dependencies
```bash
pip install openpyxl==3.11.0 reportlab==4.0.9
```

### 2. Start the API
```bash
python3 backend/api.py
```

### 3. Start the Web UI
```bash
streamlit run web/app.py
```

---

## Feature 1: Chat with Session History

### Via Web UI

1. **Go to Chat tab** → Top navigation
2. **Click "New Session"** → Starts fresh conversation
3. **Type your question** → e.g., "Find Python developers"
4. **Click "Search & Answer"** → RAG system searches CVs
5. **View conversation** → All Q&A with sources displayed
6. **Load previous session** → Click "Load Session" to list prior conversations
7. **Save session** → Auto-saved; click "Save" to confirm

### Via API (curl)

#### Create/Continue Session
```bash
curl -X POST http://localhost:8000/chat \
  -H "X-API-Key: test-key-123" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Find candidates with Machine Learning and Docker experience",
    "top_k": 10,
    "session_id": "optional-existing-session-id"
  }'
```

**Response**:
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "message_id": "msg-123",
  "question": "Find candidates with Machine Learning and Docker experience",
  "answer": "I found 5 candidates with both skills...",
  "sources": [
    {
      "candidate_name": "John Doe",
      "resume_id": "resume-001",
      "similarity_score": 0.95,
      "chunk_text": "5 years ML experience with Docker deployment"
    }
  ],
  "timestamp": "2025-01-15T10:30:00"
}
```

#### Retrieve Session History
```bash
curl http://localhost:8000/chat/550e8400-e29b-41d4-a716-446655440000 \
  -H "X-API-Key: test-key-123"
```

#### List Recent Sessions
```bash
curl "http://localhost:8000/chat?limit=10" \
  -H "X-API-Key: test-key-123"
```

---

## Feature 2: Role-Based Access Control

### Default Users

Three default users are created automatically (demo only):

| Username | Password | Role | Permissions |
|----------|----------|------|-------------|
| admin | admin123 | admin | All |
| recruiter | recruiter123 | recruiter | Upload, Search, Parse, Rank, Export, Analytics |
| viewer | viewer123 | viewer | Search, Analytics (read-only) |

⚠️ **Production**: Create strong passwords and use JWT tokens

### Via API - Authentication

#### Login
```bash
curl -X POST http://localhost:8000/auth/login \
  -H "X-API-Key: test-key-123" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "recruiter",
    "password": "recruiter123"
  }'
```

**Response**:
```json
{
  "token": "recruiter",
  "user_id": "user-002",
  "username": "recruiter",
  "email": "recruiter@company.com",
  "role": "recruiter",
  "permissions": [
    "upload_cv",
    "search_cv",
    "parse_jd",
    "rank_candidates",
    "export_results",
    "view_analytics"
  ]
}
```

#### Get Current User
```bash
curl http://localhost:8000/auth/me \
  -H "Authorization: Bearer recruiter"
```

### Creating New Users (Admin Only)

**Python**:
```python
from backend.rbac import create_user

# Create new recruiter
user_id = create_user(
    username="john.doe",
    email="john@company.com",
    password="secure_password_123",
    role="recruiter"
)

print(f"Created user: {user_id}")
```

### Checking Permissions

**Python**:
```python
from backend.rbac import has_permission, get_user_permissions

user_id = "user-002"

# Check specific permission
if has_permission(user_id, "export_results"):
    print("User can export results")

# Get all permissions
permissions = get_user_permissions(user_id)
print(f"User permissions: {permissions}")
```

---

## Feature 3: Export Results

### Via Web UI

1. **Go to JD Matching tab** → Parse or select JD
2. **Rank candidates** → Click "Rank Candidates"
3. **Scroll to Export section** → After results
4. **Select format**: CSV / XLSX / JSON / PDF
5. **Click "Export Now"** → Generates file
6. **Download** → Use download button or file path

### Via API

#### Export as PDF (Professional Report)
```bash
curl -X POST http://localhost:8000/export \
  -H "X-API-Key: test-key-123" \
  -H "Content-Type: application/json" \
  -d '{
    "results": [
      {
        "rank": 1,
        "candidate_name": "John Doe",
        "final_score": 0.92,
        "rule_score": 0.88,
        "semantic_score": 0.96,
        "matched_must": ["Python", "Docker"],
        "matched_nice": ["Kubernetes", "FastAPI"],
        "missing_must": []
      }
    ],
    "format": "pdf",
    "jd_title": "Senior Python Developer",
    "jd_data": {
      "job_title": "Senior Python Developer",
      "company": "Tech Corp",
      "location": "Remote",
      "skills": {
        "must_have": ["Python", "Docker", "SQL"],
        "nice_to_have": ["Kubernetes", "FastAPI"]
      }
    }
  }'
```

**Response**:
```json
{
  "format": "pdf",
  "file_path": "./data/exports/jd_ranking_2025-01-15_103000.pdf",
  "message": "Exported 5 results to PDF"
}
```

#### Export as CSV
```bash
curl -X POST http://localhost:8000/export \
  -H "X-API-Key: test-key-123" \
  -H "Content-Type: application/json" \
  -d '{
    "results": [...],
    "format": "csv",
    "jd_title": "Senior Python Developer"
  }'
```

#### Export as XLSX (Excel)
```bash
curl -X POST http://localhost:8000/export \
  -H "X-API-Key: test-key-123" \
  -H "Content-Type: application/json" \
  -d '{
    "results": [...],
    "format": "xlsx",
    "jd_title": "Senior Python Developer",
    "jd_data": {...}
  }'
```

### Export Formats

#### CSV
- **Fields**: Rank, Name, Final Score, Rule Score, Semantic Score, Must-Have Matched, Nice-to-Have Matched, Missing Must-Have
- **Use**: Simple spreadsheet, email-friendly
- **Example**: `jd_ranking_2025-01-15_103000.csv`

#### XLSX
- **Sheets**: 
  - Rankings (formatted table)
  - JD Details (job requirements)
- **Use**: Professional reporting with formatting
- **Example**: `jd_ranking_2025-01-15_103000.xlsx`

#### JSON
- **Structure**: Complete data with metadata
- **Fields**: exported_at, jd, results, summary
- **Use**: Integration with other systems, data pipelines
- **Example**: `jd_ranking_2025-01-15_103000.json`

#### PDF
- **Contents**:
  - Header with job title and company
  - JD summary with skills
  - Rankings table (top 10)
  - Footer with metadata
- **Styling**: Professional colors, readable fonts
- **Use**: Client presentations, archived reports
- **Example**: `jd_ranking_2025-01-15_103000.pdf`

### Finding Exported Files

All exports go to: `./data/exports/`

```bash
ls -lh ./data/exports/
# Output:
# jd_ranking_2025-01-15_103000.pdf (2.5M)
# jd_ranking_2025-01-15_103015.xlsx (150K)
# jd_ranking_2025-01-15_103030.csv (50K)
# jd_ranking_2025-01-15_103045.json (80K)
```

---

## Database Files

### Chat Sessions Database
```
./data/chat_sessions.db
├── chat_sessions table  (session metadata)
└── chat_messages table  (conversation history)
```

**Access via SQLite**:
```bash
sqlite3 ./data/chat_sessions.db
sqlite> SELECT * FROM chat_sessions LIMIT 5;
sqlite> SELECT * FROM chat_messages WHERE session_id = 'xxx' LIMIT 10;
```

### RBAC Database
```
./data/rbac.db
├── users table  (usernames, password hashes, roles)
└── roles table  (role definitions and permissions)
```

**Access via SQLite**:
```bash
sqlite3 ./data/rbac.db
sqlite> SELECT username, role FROM users;
sqlite> SELECT role_name, permissions_json FROM roles;
```

---

## Common Workflows

### Workflow 1: Rank Candidates & Export PDF

1. Upload CVs (JD Matching tab → Upload)
2. Parse JD (paste or upload)
3. Rank candidates
4. Select PDF format
5. Click Export Now
6. Download PDF report
7. Send to client/team

### Workflow 2: Ask Questions About Candidates

1. Go to Chat tab
2. Click New Session
3. Ask: "Find all candidates with 5+ years Python"
4. Read answer with sources
5. Ask follow-up: "Who also has Docker?"
6. Session saved automatically
7. Can load session later

### Workflow 3: Create User & Assign Role

```python
from backend.rbac import create_user, has_permission

# Create recruiter
recruiter_id = create_user(
    username="jane.smith",
    email="jane@company.com",
    password="secure_pass",
    role="recruiter"
)

# Verify permissions
if has_permission(recruiter_id, "export_results"):
    print("Jane can export results ✓")
```

### Workflow 4: Use Existing Session

**API**:
```bash
# Get list of sessions
curl http://localhost:8000/chat?limit=5 \
  -H "X-API-Key: test-key-123"

# Get session ID from response, then:
curl -X POST http://localhost:8000/chat \
  -H "X-API-Key: test-key-123" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "550e8400-e29b-41d4-a716-446655440000",
    "question": "Follow-up question here",
    "top_k": 10
  }'
```

---

## Troubleshooting

### "Chat session not found"
- Verify session ID is correct
- Check `./data/chat_sessions.db` exists
- Try creating new session

### "Export failed: No such file or directory"
- Ensure `./data/exports/` exists
- Run: `mkdir -p ./data/exports/`
- Check write permissions

### "PDF generation failed"
- Verify `reportlab` installed: `pip install reportlab`
- Check for special characters in JD title
- Review API logs for details

### "User authentication failed"
- Verify `./data/rbac.db` exists
- Check username and password
- Default users: admin/admin123, recruiter/recruiter123, viewer/viewer123

### "Permission denied"
- Check user role: `sqlite3 ./data/rbac.db "SELECT username, role FROM users;"`
- Verify role has permission: `sqlite3 ./data/rbac.db "SELECT permissions_json FROM roles WHERE role_name='recruiter';"`

---

## Production Checklist

- [ ] Change default user passwords
- [ ] Replace SHA256 with bcrypt password hashing
- [ ] Implement JWT token authentication
- [ ] Add rate limiting on API endpoints
- [ ] Move databases from `./data/` to persistent volume
- [ ] Implement export file cleanup (30-day retention)
- [ ] Add SSL/TLS for API
- [ ] Monitor disk space for exports
- [ ] Add backup strategy for databases
- [ ] Implement audit logging

---

## Support & Examples

### Python Script: Automated Export Workflow

```python
import requests
import json

API_BASE_URL = "http://localhost:8000"
API_KEY = "test-key-123"

# 1. Authenticate
response = requests.post(
    f"{API_BASE_URL}/auth/login",
    headers={"X-API-Key": API_KEY},
    json={"username": "recruiter", "password": "recruiter123"}
)
user = response.json()
print(f"✓ Logged in as {user['username']} ({user['role']})")

# 2. Create chat session
response = requests.post(
    f"{API_BASE_URL}/chat",
    headers={"X-API-Key": API_KEY},
    json={
        "question": "Find Python developers",
        "top_k": 5
    }
)
session = response.json()
print(f"✓ Created session: {session['session_id']}")

# 3. Export results as PDF
response = requests.post(
    f"{API_BASE_URL}/export",
    headers={"X-API-Key": API_KEY},
    json={
        "results": [
            {"candidate_name": "John", "final_score": 0.95},
            {"candidate_name": "Jane", "final_score": 0.87}
        ],
        "format": "pdf",
        "jd_title": "Senior Python Developer"
    }
)
export = response.json()
print(f"✓ Exported to: {export['file_path']}")
```

---

**Last Updated**: January 15, 2025
**Version**: 1.0.0
