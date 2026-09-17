# How to Run API Sentinel

---

## Prerequisites
- Python 3.10+ installed
- Terminal / Command Prompt

---

## Method 1: Quick Start (Recommended for Windows)

### 1. One-Time Setup (if `.venv` is not created yet)
Open Command Prompt / PowerShell in the project directory:
```bash
python -m venv .venv
.venv\Scripts\pip install -e .
```

### 2. Start Everything & Launch Demo
Double-click or run:
```cmd
start_all.cmd
```
*This automatically starts the API server, starts the Dashboard, injects validation issues, and opens the browser.*

### 3. Generate / Push Issues Again (During Demo)
```cmd
push_issues.cmd
```

### 4. Stop All Services
```cmd
stop_all.cmd
```

---

## Method 2: Manual Terminal Commands

### Step 1: Environment Setup
```bash
# Create and activate virtual environment
python -m venv .venv

# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -e .
```

### Step 2: Start Demo API (Terminal 1)
```bash
uvicorn example_app:app --reload --host 127.0.0.1 --port 8000
```
- **API Base URL:** `http://127.0.0.1:8000`
- **Swagger Documentation:** `http://127.0.0.1:8000/docs`

### Step 3: Start Dashboard (Terminal 2)
```bash
uvicorn dashboard.app:app --reload --host 127.0.0.1 --port 8001
```
- **Dashboard URL:** `http://127.0.0.1:8001`

### Step 4: Run Validation & Push Issues (Terminal 3)
```bash
python push_to_dashboard.py
```

---

## Presentation / Demo Steps for Faculty

1. **Open Swagger UI:** Go to [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) to show the monitored API endpoints and OpenAPI schema.
2. **Open Dashboard:** Go to [http://127.0.0.1:8001](http://127.0.0.1:8001) to present the real-time API monitoring interface.
3. **Trigger Validation Issues:** Run `push_issues.cmd` or `python push_to_dashboard.py`.
4. **Show Live Results:** Refresh the Dashboard to showcase:
   - Request & response schema validation errors
   - Performance & latency metrics
   - Detailed issue breakdowns and logs
5. **Stop Services:** Run `stop_all.cmd` or press `Ctrl + C` in the terminals.
