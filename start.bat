@echo off
REM =============================================================================
REM start.bat — One-command local startup for MAE (Windows)
REM
REM Usage:
REM   Double-click start.bat  OR  run it from a command prompt:
REM   > start.bat
REM
REM What it does:
REM   1. Checks .env exists (copies .env.example if not)
REM   2. Creates the Python virtual environment if absent
REM   3. Installs / upgrades Python dependencies
REM   4. Runs Alembic migrations (creates SQLite DB on first run)
REM   5. Installs frontend npm dependencies if node_modules is absent
REM   6. Starts the FastAPI backend (port 8000) in a new window
REM   7. Starts the Vite dev server (port 5173) in a new window
REM
REM Requirements:
REM   - Python 3.11+  (available on PATH as "python")
REM   - Node.js 18+   (available on PATH as "node")
REM   - npm 9+        (available on PATH as "npm")
REM =============================================================================

setlocal EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

echo [MAE] Starting MAE local development environment...
echo.

REM -----------------------------------------------------------------------------
REM 1. .env
REM -----------------------------------------------------------------------------

if not exist ".env" (
    echo [MAE] .env not found — copying .env.example
    copy ".env.example" ".env" >nul
    echo.
    echo [MAE] IMPORTANT: Open .env in a text editor and set GEMINI_API_KEY,
    echo [MAE] then re-run start.bat.
    echo.
    pause
    exit /b 1
)

REM Check for missing GEMINI_API_KEY (simple grep-equivalent)
findstr /r "^GEMINI_API_KEY=$" ".env" >nul 2>&1
if !errorlevel! == 0 (
    echo [MAE] WARNING: GEMINI_API_KEY appears to be empty in .env.
    echo [MAE]          The backend will start but LLM calls will fail.
    echo [MAE]          Get a free key at https://aistudio.google.com/app/apikey
    echo.
)

REM -----------------------------------------------------------------------------
REM 2. Python virtual environment
REM -----------------------------------------------------------------------------

set "VENV_DIR=.venv"

if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo [MAE] Creating Python virtual environment in %VENV_DIR% ...
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [MAE] ERROR: Failed to create virtual environment.
        echo [MAE]        Ensure Python 3.11+ is installed and on PATH.
        pause
        exit /b 1
    )
)

REM -----------------------------------------------------------------------------
REM 3. Python dependencies
REM -----------------------------------------------------------------------------

echo [MAE] Installing Python dependencies ...
call "%VENV_DIR%\Scripts\activate.bat"
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

REM Set PYTHONPATH so 'backend' package is importable by Alembic and uvicorn
set "PYTHONPATH=%SCRIPT_DIR%"
if errorlevel 1 (
    echo [MAE] ERROR: pip install failed. Check requirements.txt and your internet connection.
    pause
    exit /b 1
)

REM -----------------------------------------------------------------------------
REM 4. Alembic migrations
REM -----------------------------------------------------------------------------

echo [MAE] Running database migrations ...
alembic upgrade head
if errorlevel 1 (
    echo [MAE] ERROR: Alembic migration failed. Check your .env DB settings.
    pause
    exit /b 1
)

REM -----------------------------------------------------------------------------
REM 5. Frontend dependencies
REM -----------------------------------------------------------------------------

REM Always run npm install — it is fast when packages are already cached,
REM and avoids stale node_modules missing executables like vite.
echo [MAE] Installing frontend npm dependencies ...
cd frontend
npm install
if errorlevel 1 (
    echo [MAE] ERROR: npm install failed. Check Node.js installation.
    pause
    exit /b 1
)
cd ..

REM -----------------------------------------------------------------------------
REM 6. Start backend in a new window
REM -----------------------------------------------------------------------------

echo [MAE] Starting FastAPI backend on http://localhost:8000 ...
start "MAE Backend" cmd /k "cd /d %SCRIPT_DIR% && set PYTHONPATH=%SCRIPT_DIR% && call .venv\Scripts\activate.bat && uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload"

REM Give uvicorn a moment to bind
timeout /t 2 /nobreak >nul

REM -----------------------------------------------------------------------------
REM 7. Start frontend in a new window
REM -----------------------------------------------------------------------------

echo [MAE] Starting Vite dev server on http://localhost:5173 ...
start "MAE Frontend" cmd /k "cd /d %SCRIPT_DIR%\frontend && npm run dev"

REM -----------------------------------------------------------------------------
REM Done
REM -----------------------------------------------------------------------------

echo.
echo [MAE] Both servers are starting in separate windows.
echo.
echo [MAE]   Backend : http://localhost:8000
echo [MAE]   Frontend: http://localhost:5173
echo [MAE]   API docs: http://localhost:8000/docs
echo.
echo [MAE] Close the Backend and Frontend windows to stop the servers.
echo.
pause
