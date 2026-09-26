# How to Run the Dynamic BIS Chat System

## Current Status Check

Your system already has:
- ✅ MongoDB Atlas connection configured
- ✅ Frontend dependencies installed
- ✅ Backend Python environment ready
- ✅ Uvicorn installed

## What You Need to Add

### Required API Keys

You need **2 API keys** to enable dynamic chat:

#### 1. Serper API Key (for live BIS search)
- **Cost**: FREE (2,500 searches/month)
- **Get it**: https://serper.dev
  1. Click "Sign Up" (top right)
  2. Sign in with Google/GitHub
  3. Go to Dashboard → API Key
  4. Copy your API key

#### 2. Gemini API Key (for AI responses)
- **Cost**: FREE (generous quota)
- **Get it**: https://aistudio.google.com/app/apikey
  1. Sign in with Google
  2. Click "Create API Key"
  3. Copy your API key

---

## Setup Steps (5 minutes)

### Step 1: Add API Keys to `.env`

Open `backend/.env` in a text editor and add these lines at the end:

```bash
# --- Dynamic Search (ADD THESE LINES) ---------------------------------
SERPER_API_KEY=your_serper_key_here
GEMINI_API_KEY=your_gemini_key_here
SEARCH_CACHE_TTL=3600
```

**Replace**:
- `your_serper_key_here` with your actual Serper key
- `your_gemini_key_here` with your actual Gemini key

**Example**:
```bash
SERPER_API_KEY=abc123xyz789def456
GEMINI_API_KEY=AIzaSyC1234567890abcdefghijk
SEARCH_CACHE_TTL=3600
```

### Step 2: Update LLM Provider

In the same `backend/.env` file, change:

```bash
# BEFORE:
LLM_PROVIDER=auto
LLM_API_KEY=

# AFTER:
LLM_PROVIDER=gemini
# LLM_API_KEY can stay empty (GEMINI_API_KEY is used instead)
```

Save the file.

---

## Running the System

### Option A: Two Separate Terminals (Recommended)

**Terminal 1 - Backend:**
```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

Wait for:
```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000
```

**Terminal 2 - Frontend:**
```bash
cd frontend
npm run dev
```

Wait for:
```
  VITE ready in XXX ms
  ➜  Local:   http://localhost:5173/
```

### Option B: Using the Provided Startup Scripts

**Windows (PowerShell):**
```powershell
# Terminal 1
cd backend
python -m uvicorn app.main:app --reload --port 8000

# Terminal 2
cd frontend
npm run dev
```

**Mac/Linux:**
```bash
# Terminal 1
cd backend
uvicorn app.main:app --reload --port 8000

# Terminal 2
cd frontend
npm run dev
```

---

## Testing the Dynamic Chat

### Step 1: Open the Chat Interface

Open your browser to: **http://localhost:5173/chat**

You should see:
- "BIS Knowledge Assistant" header
- Language selector (English / हिंदी)
- Empty chat area with example prompts
- Input box at the bottom

### Step 2: Try Example Queries

**English queries:**
```
Which BIS standard applies to pressure cookers?
What certification is required for electric irons?
Where can I get my product tested?
How do I apply for BIS certification?
Explain IS 2082 in simple terms
```

**Hindi queries:**
```
प्रेशर कुकर के लिए कौन सा BIS मानक है?
मुझे BIS प्रमाणन कैसे मिलेगा?
```

### Step 3: What You Should See

For each query, you'll see:

1. **User message** (blue bubble on right)
2. **Search status** (animated "Searching authoritative BIS sources...")
3. **AI response** (white bubble on left) with:
   - Grounded answer with inline citations [S1], [S2]
   - Source cards below showing:
     - ✓ Official BIS badge (green shield)
     - Source title
     - Snippet preview
     - Domain name
     - Clickable link
4. **Intent classification** (small text showing detected query type)

---

## Troubleshooting

### ❌ "Search provider not available"

**Problem**: Serper API key is missing or invalid

**Solution**:
1. Check `backend/.env` has `SERPER_API_KEY=...`
2. Make sure the key has no spaces or quotes
3. Restart backend: `Ctrl+C` then run uvicorn again

### ❌ "LLM not available"

**Problem**: Gemini API key is missing or invalid

**Solution**:
1. Check `backend/.env` has `GEMINI_API_KEY=...`
2. Check `LLM_PROVIDER=gemini` (or `auto`)
3. Restart backend

### ❌ Backend won't start - "Port already in use"

**Problem**: Port 8000 is already occupied

**Solution**:
```bash
# Use a different port
uvicorn app.main:app --reload --port 8001

# Then update frontend API URL:
# frontend/.env.development → VITE_API_BASE_URL=http://localhost:8001/api
```

### ❌ Frontend won't start - "Port 5173 in use"

**Problem**: Port 5173 is already occupied

**Solution**: Vite will auto-select the next available port (5174, 5175, etc.)

### ❌ "No sources found" for every query

**Problem**: Either internet connection or Serper API issue

**Solution**:
1. Check internet connection
2. Visit https://serper.dev/dashboard to check quota
3. Try a simpler query: "BIS pressure cooker"

### ❌ Backend crashes on startup

**Problem**: Missing Python dependencies

**Solution**:
```bash
cd backend
pip install httpx pydantic
```

Then restart backend.

---

## Verify Everything is Working

### Backend Health Check

Open in browser: http://localhost:8000/api/health

You should see JSON with:
```json
{
  "status": "operational",
  "llm": {
    "available": true,
    "provider": "gemini"
  },
  ...
}
```

### Chat Health Check

Open in browser: http://localhost:8000/api/chat/health

You should see:
```json
{
  "search_provider_available": true,
  "cache_enabled": true,
  "retrieval_enabled": true
}
```

If all `true`, you're good to go!

---

## Quick Reference

### Important URLs
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs
- Frontend: http://localhost:5173
- Dynamic Chat: http://localhost:5173/chat
- Existing Assistant: http://localhost:5173/assistant

### Key Files
- Backend config: `backend/.env`
- Frontend config: `frontend/.env.development`
- Backend logs: Terminal 1 output
- Frontend logs: Terminal 2 output

### Stop the System
- Press `Ctrl+C` in both terminals

---

## What's Different from Before?

**Old System** (`/assistant`):
- Uses pre-ingested RAG corpus
- Limited to documents in MongoDB
- Requires data ingestion scripts

**New System** (`/chat`):
- Dynamic live search from BIS sources
- No corpus required
- Works with any product/query
- Real-time information retrieval

**Both are available!** Use:
- `/assistant` for deep corpus queries
- `/chat` for general BIS questions

---

## Next Steps

Once it's running:

1. **Test all query types**:
   - Product standards
   - Certification requirements
   - Testing labs
   - Hallmarking info
   - General BIS procedures

2. **Try Hindi**:
   - Toggle language to Hindi
   - Ask questions in Hindi
   - Verify Hindi responses

3. **Check sources**:
   - Click source cards
   - Verify they're official BIS pages
   - Check citation accuracy

4. **Monitor logs**:
   - Watch backend terminal for errors
   - Check cache hits/misses
   - Monitor API call patterns

---

## Need Help?

If you're still stuck:

1. **Check logs** in both terminal windows
2. **Verify API keys** are correct in `.env`
3. **Test APIs directly**:
   ```bash
   # Test chat endpoint
   curl -X POST http://localhost:8000/api/chat/message \
     -H "Content-Type: application/json" \
     -d '{"message":"test"}'
   ```

4. **Review files**:
   - `IMPLEMENTATION_NOTES.md` - Technical details
   - `QUICKSTART.md` - Setup overview

---

## You're Ready!

Just need to:
1. Add API keys to `backend/.env`
2. Start backend in Terminal 1
3. Start frontend in Terminal 2
4. Open http://localhost:5173/chat
5. Ask BIS questions!

Total time: **5 minutes** ⏱️
