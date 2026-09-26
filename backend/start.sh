#!/bin/bash
# Simple startup script for Dynamic BIS Chat

echo "=========================================="
echo "Starting Dynamic BIS Chat System"
echo "=========================================="
echo ""

# Check if .env exists
if [ ! -f "backend/.env" ]; then
    echo "❌ Error: backend/.env not found"
    echo "Run: cp backend/.env.example backend/.env"
    exit 1
fi

# Check for API keys
if ! grep -q "SERPER_API_KEY=.*[^=]" backend/.env; then
    echo "⚠️  Warning: SERPER_API_KEY not set in backend/.env"
    echo "Get free key at: https://serper.dev"
fi

if ! grep -q "GEMINI_API_KEY=.*[^=]" backend/.env; then
    echo "⚠️  Warning: GEMINI_API_KEY not set in backend/.env"
    echo "Get free key at: https://aistudio.google.com/app/apikey"
fi

echo ""
echo "Starting backend on http://localhost:8000"
echo "Starting frontend on http://localhost:5173"
echo ""
echo "Open http://localhost:5173/chat when both are ready"
echo ""
echo "Press Ctrl+C to stop"
echo "=========================================="
echo ""

# Start backend in background
cd backend
uvicorn app.main:app --reload --port 8000 &
BACKEND_PID=$!

# Wait a moment for backend to start
sleep 2

# Start frontend
cd ../frontend
npm run dev &
FRONTEND_PID=$!

# Wait for both processes
wait $BACKEND_PID $FRONTEND_PID
