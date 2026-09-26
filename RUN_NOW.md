# Run the System Now (Without Dynamic Chat)

Your system can run now with the existing RAG-based assistant!

## Start Backend

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

Wait for: "Application startup complete"

## Start Frontend (New Terminal)

```bash
cd frontend
npm run dev
```

Wait for: "Local: http://localhost:5173/"

## What Works Now

✅ **Existing Features** (http://localhost:5173):
- Product Analysis
- Standards Discovery
- Gap Analysis
- Compliance Twin
- Certification Process
- Hallmarking Guide
- RAG Assistant at `/assistant`
- Standards Browser

❌ **Dynamic Chat** (http://localhost:5173/chat):
- Will show: "Search provider not available"
- Need Serper API key to enable

## To Enable Dynamic Chat

Add Serper API key to `backend/.env`:

1. Get key: https://serper.dev (free)
2. Edit `backend/.env`
3. Find: `SERPER_API_KEY=`
4. Add: `SERPER_API_KEY=your_key_here`
5. Restart backend (Ctrl+C then run uvicorn again)

Then the chat at `/chat` will work!

---

**Quick Start**: Just run the two commands above in separate terminals!
