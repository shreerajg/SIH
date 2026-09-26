# Quick Start Guide - Dynamic BIS Knowledge Retrieval

## Overview

This system provides **live BIS knowledge retrieval** without requiring a pre-ingested corpus. It dynamically searches authoritative BIS sources and generates grounded answers using Gemini.

## 5-Minute Setup

### 1. Get API Keys

**Serper API** (free tier: 2,500 searches/month)
```bash
# Visit https://serper.dev
# Sign up → Get API key from dashboard
```

**Gemini API** (you likely already have this)
```bash
# Visit https://aistudio.google.com/app/apikey
# Create API key if needed
```

### 2. Configure Backend

```bash
cd backend

# Create .env file
cp .env.example .env

# Edit .env and add these critical variables:
SERPER_API_KEY=your_serper_key_here
GEMINI_API_KEY=your_gemini_key_here
LLM_PROVIDER=gemini
LLM_MODEL=gemini-2.0-flash
MONGO_URI=your_mongodb_uri_here
MONGO_DB_NAME=sih26107
```

### 3. Install Dependencies (if needed)

```bash
pip install httpx pydantic
```

### 4. Start the Backend

```bash
uvicorn app.main:app --reload --port 8000
```

You should see:
```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000
```

### 5. Start the Frontend

```bash
cd ../frontend
npm run dev
```

You should see:
```
  VITE ready in XXX ms

  ➜  Local:   http://localhost:5173/
```

### 6. Test It!

Open your browser to: **http://localhost:5173/chat**

Try these example queries:

**English:**
- "Which BIS standard applies to pressure cookers?"
- "What certification is required for electric irons?"
- "Where can I get my product tested?"
- "How do I apply for BIS certification?"

**Hindi:**
- "प्रेशर कुकर के लिए कौन सा BIS मानक है?"
- "मुझे BIS प्रमाणन कैसे मिलेगा?"

## What You Should See

1. **Search Status**: "Searching authoritative BIS sources..."
2. **Grounded Answer**: Response based on retrieved evidence
3. **Source Cards**: Clickable sources with:
   - ✓ Official BIS badge (for verified domains)
   - Title and snippet
   - Source URL
4. **Intent Classification**: Shows detected query type

## API Endpoints

### Chat Endpoint
```bash
curl -X POST http://localhost:8000/api/chat/message \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Which standard applies to helmets?",
    "language": "en"
  }'
```

### Health Check
```bash
curl http://localhost:8000/api/chat/health
```

Response:
```json
{
  "search_provider_available": true,
  "cache_enabled": true,
  "retrieval_enabled": true
}
```

## Troubleshooting

### ❌ "Search provider not available"

**Cause**: Missing or invalid Serper API key

**Fix**:
```bash
# Check backend/.env
SERPER_API_KEY=your_actual_key_here  # Not empty!

# Restart backend
```

### ❌ "LLM not available"

**Cause**: Missing or invalid Gemini API key

**Fix**:
```bash
# Check backend/.env
GEMINI_API_KEY=your_actual_key_here
LLM_PROVIDER=gemini  # Or 'auto'

# Restart backend
```

### ❌ "Database unreachable (503)"

**Cause**: MongoDB not running or wrong connection string

**Fix**:
```bash
# Local MongoDB
MONGO_URI=mongodb://localhost:27017

# Or MongoDB Atlas
MONGO_URI=mongodb+srv://user:pass@cluster.mongodb.net/

# Restart backend
```

### ❌ "No sources found"

**Possible causes**:
1. Internet connection issue
2. Serper API quota exhausted (check dashboard)
3. Query too specific/obscure

**Fix**: Try a broader query first

## Architecture Summary

```
User Question
    ↓
Intent Classification (heuristic + LLM)
    ↓
Search Query Generation (2-3 variations)
    ↓
Serper API → Google Search
    ↓
BIS Source Filtering & Validation
    ↓
Source Ranking (official > supporting)
    ↓
Gemini Grounded Generation
    ↓
Answer + Citations
```

## Key Features

✅ **No pre-ingested corpus required**
✅ **Grounded answers** - never invents standards
✅ **Source citations** - every claim backed by evidence
✅ **Official BIS priority** - verified domain filtering
✅ **Multilingual** - Hindi + English
✅ **Lightweight caching** - reduces API costs
✅ **Conversation context** - follow-up questions work

## Cost Estimate

**Free tier limits:**
- Serper: 2,500 searches/month
- Gemini Flash: Very generous free quota

**Typical usage:**
- Average user: 3-5 questions per session
- Cache hit rate: ~50% (after initial queries)
- Monthly capacity: **500-800 users** on free tier

## Next Steps

### For Demo
You're ready! The system works end-to-end.

### For Production
1. **Add monitoring** - Track query patterns, errors, latency
2. **Rate limiting** - Prevent abuse
3. **Redis cache** - Replace file-based cache
4. **Error alerts** - API quota warnings
5. **Analytics** - User behavior insights

### For Scale
1. **Search provider pool** - Multiple API keys
2. **Result vectorization** - Build semantic index of retrieved pages
3. **Direct BIS integration** - If BIS provides APIs
4. **Multi-region deployment** - Reduce latency

## Project Structure

```
backend/app/
├── retrieval/           # NEW: Dynamic search infrastructure
│   ├── base.py         # Search provider interface
│   ├── search_provider.py  # Serper implementation
│   ├── bis_retriever.py    # BIS-specific logic
│   ├── source_validator.py # Trust scoring
│   └── cache.py        # Result caching
├── services/
│   └── gemini_grounded.py  # NEW: Grounded answer generation
└── api/
    └── chat.py         # NEW: Chat endpoint

frontend/src/
├── components/
│   └── DynamicChat.tsx # NEW: Chat UI
├── pages/
│   └── DynamicChatPage.tsx  # NEW: Chat page
└── lib/
    ├── api.ts          # Updated: chatMessage()
    └── types.ts        # Updated: ChatResponse
```

## Support

If you encounter issues:

1. Check logs in terminal where backend is running
2. Verify environment variables in `.env`
3. Test API directly with curl
4. Check `IMPLEMENTATION_NOTES.md` for details

## Success Criteria

✓ User can ask arbitrary BIS questions
✓ System retrieves authoritative sources
✓ Answers cite evidence with [S1], [S2], etc.
✓ Official BIS sources are prioritized
✓ No hallucinated standards or requirements
✓ Hindi queries get Hindi answers
✓ Conversation context is maintained

---

**You're all set!** 🚀

Navigate to http://localhost:5173/chat and start asking BIS questions.
