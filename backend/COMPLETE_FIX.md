# 🚨 COMPLETE FIX GUIDE - READ THIS CAREFULLY

## Problem Analysis from Your Logs:

```
21:10:05  INFO    httpx: HTTP Request: POST https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent "HTTP/1.1 400 Bad Request"
21:10:05  WARNING app.llm.providers: Gemini call failed
```

### Root Cause: Wrong Gemini Model

**Issue**: Code uses `gemini-2.0-flash` which doesn't exist yet
**Fix**: Need to use `gemini-1.5-flash` (stable version)

---

## 🔧 FIXES TO APPLY

### Fix 1: Update Gemini Model (CRITICAL)

The model name has already been fixed in the code to `gemini-1.5-flash`.

**Action Required**: RESTART BACKEND

```bash
# In your backend terminal, press Ctrl+C
# Then restart:
uvicorn app.main:app --reload --port 8000
```

### Fix 2: Use the CORRECT Page

**YOU ARE CURRENTLY ON THE WRONG PAGE!**

Your logs show:
```
INFO: POST /api/rag/query HTTP/1.1 200 OK
```

This is the **OLD** corpus-based assistant, NOT the new dynamic chat!

**Current (Wrong)**: http://localhost:5173/assistant
**New (Correct)**: http://localhost:5173/chat

---

## ✅ STEP-BY-STEP TO FIX

### Step 1: Restart Backend

In your backend terminal:
1. Press `Ctrl+C` to stop
2. Run: `uvicorn app.main:app --reload --port 8000`
3. Wait for "Application startup complete"

You should see these NEW lines:
```
INFO: Serper search provider initialized  
INFO: BIS retriever initialized
```

### Step 2: Navigate to Dynamic Chat Page

**DO NOT GO TO**: http://localhost:5173/assistant
**GO TO THIS URL**: http://localhost:5173/chat

### Step 3: Test Dynamic Search

Try this query:
```
Which BIS standard applies to pressure cookers?
```

**What you should see**:
1. Search animation: "Searching authoritative BIS sources..."
2. Source cards with BIS official badges
3. AI answer with [S1], [S2] citations
4. No 400 errors in backend logs

---

## 🌐 Multilingual is Already Working!

On the `/chat` page, you'll see:
- **English / हिंदी** toggle button (top right)

Try Hindi:
```
प्रेशर कुकर के लिए कौन सा BIS मानक है?
```

Response will be in Hindi with English source citations.

---

## 🔍 How Dynamic Search Works

### Intelligent Fallback Chain:

```
User Query
    ↓
1. Check existing corpus first (fast, verified)
    ↓ (if found)
    Return corpus answer
    ↓ (if NOT found)
2. Dynamic BIS search (live, authoritative)
    ↓
    Serper API → Google Search → BIS domains
    ↓
3. Gemini grounded generation
    ↓
    Answer + Citations
```

This is **by design** - uses existing corpus when available, searches when needed!

---

## 📊 Before vs After

### BEFORE (Current Logs):
```
❌ POST /api/rag/query (old endpoint)
❌ WARNING: Gemini 400 Bad Request
❌ Retrieval-only mode
```

### AFTER (Expected):
```
✅ POST /api/chat/message (new endpoint)
✅ INFO: Retrieved 6 sources from BIS
✅ INFO: Gemini generation successful
✅ INFO: 5 official sources, 1 supporting
```

---

## 🎯 Complete Test Checklist

After restarting backend and going to `/chat`:

1. **English Query**:
   ```
   Which BIS standard applies to pressure cookers?
   ```
   ✅ Should see live search
   ✅ Should see source cards
   ✅ Should see citations [S1], [S2]

2. **Hindi Query**:
   - Click हिंदी button
   ```
   स्टील की बोतल के लिए मानक क्या है?
   ```
   ✅ Response in Hindi
   ✅ Sources in English

3. **Follow-up**:
   ```
   What testing is required?
   ```
   ✅ Understands context (refers to pressure cookers)

4. **Unknown Product**:
   ```
   Which standard applies to flying cars?
   ```
   ✅ Should say "could not find information"
   ✅ NOT invent a standard

---

## 🆘 If Still Seeing 400 Errors

### Option A: Use Different Gemini Model

Edit `backend/.env`:
```bash
LLM_MODEL=gemini-1.5-pro
```

Restart backend.

### Option B: Verify API Key

Test your Gemini key directly:
```bash
curl -X POST \
  'https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=YOUR_KEY_HERE' \
  -H 'Content-Type: application/json' \
  -d '{"contents":[{"parts":[{"text":"Say hello"}]}]}'
```

Should return JSON, not error.

---

## 📱 Quick Reference

### URLs:
- Backend: http://localhost:8000
- **Dynamic Chat**: http://localhost:5173/chat ← USE THIS
- Old Assistant: http://localhost:5173/assistant
- API Docs: http://localhost:8000/docs

### Key Files:
- Config: `backend/.env`
- Logs: Backend terminal output
- Dynamic Chat Code: `backend/app/api/chat.py`

### Restart Commands:
```bash
# Backend
cd backend
uvicorn app.main:app --reload --port 8000

# Frontend (if needed)
cd frontend
npm run dev
```

---

## 🎬 TL;DR - DO THIS NOW:

1. **Stop backend** (Ctrl+C)
2. **Restart backend**: `uvicorn app.main:app --reload --port 8000`
3. **Open**: http://localhost:5173/chat (NOT /assistant!)
4. **Ask**: "Which BIS standard applies to pressure cookers?"
5. **Verify**: No 400 errors, see live search, get citations

---

**The code fix is already done. You just need to restart backend and use the right page!**
