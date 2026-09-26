# BIS Knowledge Assistant Setup Guide

## Issue: Getting search results instead of AI responses

The BIS Knowledge Assistant requires API keys to provide conversational AI responses. Without them, it falls back to showing raw search results.

## Quick Fix

### Option 1: Enable LLM for AI Responses (Recommended)

1. **Get a free Gemini API key:**
   - Go to https://makersuite.google.com/app/apikey
   - Click "Create API key" 
   - Copy the key

2. **Configure the backend:**
   ```bash
   cd backend
   cp .env.example .env
   ```

3. **Edit `backend/.env` and add:**
   ```
   GEMINI_API_KEY=your_api_key_here
   LLM_PROVIDER=gemini
   ```

4. **Restart the backend:**
   ```bash
   cd backend
   uvicorn app.main:app --reload --port 8000
   ```

### Option 2: Enable Dynamic Search (For real-time BIS data)

1. **Get a free Serper API key:**
   - Go to https://serper.dev
   - Sign up (2,500 free queries/month)
   - Get your API key

2. **Add to `backend/.env`:**
   ```
   SERPER_API_KEY=your_serper_key_here
   ```

## What Each Option Provides

- **Without API keys**: Raw search results (current behavior)
- **With LLM only**: AI responses from local corpus
- **With Serper only**: Live BIS data but basic formatting  
- **With both**: Full AI responses with live BIS data (best experience)

## Language Support

The system now supports proper responses in:
- English (en)
- हिंदी (hi) 
- मराठी (mr)
- Tamil (ta)
- Telugu (te)
- Kannada (kn)
- Malayalam (ml)
- Bengali (bn)
- Gujarati (gu)
- Punjabi (pa)
- Odia (or)
- Assamese (as)

## Test After Setup

Try asking: "BIS certification for electric irons?" in Hindi and verify you get a proper conversational response in Hindi.