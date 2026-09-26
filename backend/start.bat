@echo off
REM Simple startup script for Windows

echo ==========================================
echo Starting Dynamic BIS Chat System
echo ==========================================
echo.

REM Check if .env exists
if not exist "backend\.env" (
    echo Error: backend\.env not found
    echo Run: copy backend\.env.example backend\.env
    exit /b 1
)

echo Starting backend on http://localhost:8000
echo Starting frontend on http://localhost:5173
echo.
echo Open http://localhost:5173/chat when both are ready
echo.
echo Press Ctrl+C in each window to stop
echo ==========================================
echo.

REM Start backend in new window
start "Backend" cmd /k "cd backend && uvicorn app.main:app --reload --port 8000"

REM Wait a moment
timeout /t 3 /nobreak >nul

REM Start frontend in new window
start "Frontend" cmd /k "cd frontend && npm run dev"

echo.
echo Both services are starting in separate windows
echo Close those windows to stop the services
