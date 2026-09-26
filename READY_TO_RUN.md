# ✅ READY TO RUN!

All API keys are configured. Your dynamic BIS chat system is ready!

## 🚀 Start the System (2 Commands)

### Terminal 1 - Backend:
```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

Wait for:
```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000
```

### Terminal 2 - Frontend:
```bash
cd frontend
npm run dev
```

Wait for:
```
  ➜  Local:   http://localhost:5173/
```

## 🧪 Test the Dynamic Chat

Open: **http://localhost:5173/chat**

Try these queries:

**English:**
```
Which BIS standard applies to pressure cookers?
What certification is required for electric irons?
Where can I test my product?
How do I apply for BIS certification?
```

**Hindi:**
```
प्रेशर कुकर के लिए कौन सा BIS मानक है?
मुझे BIS प्रमाणन कैसे मिलेगा?
```

## What You Should See

1. **Search status**: "Searching authoritative BIS sources..."
2. **AI Answer**: With inline citations [S1], [S2], [S3]
3. **Source Cards**: 
   - ✓ Official BIS badge (green shield)
   - Title and snippet
   - Clickable URLs
   - Domain name
4. **Intent**: Shows detected query type

## ✅ API Keys Configured

- ✅ Gemini API Key: Set
- ✅ Serper API Key: Set
- ✅ LLM Provider: gemini
- ✅ MongoDB: Connected

## 📊 What's Available

**New Feature:**
- 🆕 `/chat` - Dynamic BIS knowledge retrieval
  - Live search from official BIS sources
  - No pre-ingested corpus needed
  - Real-time information

**Existing Features:**
- `/assistant` - RAG-based assistant
- `/manufacturer` - Product analysis
- `/consumer` - Consumer lookup
- `/hallmarking` - Hallmarking guide
- `/standards` - Standards browser

## 🎯 Demo Flow

1. Start at `/chat`
2. Ask: "Which BIS standard applies to pressure cookers?"
3. See live search → AI response → Source citations
4. Click sources to verify official BIS pages
5. Try Hindi: "स्टील की बोतल के लिए मानक क्या है?"
6. Follow up: "What testing is required?"

## 🔧 Troubleshooting

If chat shows "Search provider not available":
- Check backend terminal for errors
- Verify Serper key is correct in `.env`
- Restart backend (Ctrl+C then run uvicorn again)

If "LLM not available":
- Check Gemini key in `.env`
- Verify `LLM_PROVIDER=gemini`
- Restart backend

## 💡 Tips

- Each query searches live BIS sources (no corpus needed)
- Source cards are clickable - verify information directly
- Official BIS sources have green shield badge
- Cache reduces duplicate searches
- Conversation context maintained across questions

---

**Everything is configured! Just run the 2 commands above and open http://localhost:5173/chat**
