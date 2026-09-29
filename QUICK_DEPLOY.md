# Quick Deploy Checklist

Use this as a quick reference while deploying. See `DEPLOYMENT_GUIDE.md` for detailed instructions.

---

## ☑️ Pre-Deployment Checklist

- [ ] Code is committed to Git
- [ ] GitHub repository is created
- [ ] Code is pushed to GitHub

```bash
git add .
git commit -m "Ready for deployment"
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

---

## 1️⃣ MongoDB Atlas (5 minutes)

### Setup
- [ ] Create account at [mongodb.com/cloud/atlas/register](https://www.mongodb.com/cloud/atlas/register)
- [ ] Create FREE M0 cluster
- [ ] Create database user with password
- [ ] Set Network Access to `0.0.0.0/0` (Allow from anywhere)
- [ ] Get connection string and save it

**Connection String Format:**
```
mongodb+srv://USERNAME:PASSWORD@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
```

---

## 2️⃣ Render Backend (10 minutes)

### Deploy
- [ ] Sign up at [render.com](https://render.com) with GitHub
- [ ] New + → Blueprint
- [ ] Select your GitHub repository
- [ ] Apply blueprint

### Configure Environment
Go to service → Environment → Add these:

```env
MONGO_URI=mongodb+srv://user:pass@cluster0.xxxxx.mongodb.net/
MONGO_DB_NAME=sih26107
MONGO_TIMEOUT_MS=8000
FRONTEND_URL=https://YOUR-APP.vercel.app    # Add after Vercel deploy
CORS_ORIGINS=https://YOUR-APP.vercel.app    # Add after Vercel deploy
LLM_PROVIDER=auto
APP_ENV=production
```

- [ ] Save and wait for deployment
- [ ] **Copy your backend URL**: `https://sih26107-api.onrender.com`
- [ ] Test: Visit `https://YOUR-URL.onrender.com/api/health`

### Initialize Data
- [ ] Go to Shell tab in Render
- [ ] Run: `python scripts/setup_demo.py`

---

## 3️⃣ Vercel Frontend (5 minutes)

### Deploy
- [ ] Sign up at [vercel.com](https://vercel.com) with GitHub
- [ ] Add New → Project
- [ ] Import your repository
- [ ] Set **Root Directory**: `frontend`

### Environment Variables
```env
VITE_API_BASE_URL=https://YOUR-RENDER-URL.onrender.com/api
```

- [ ] Click Deploy
- [ ] **Copy your frontend URL**: `https://your-app.vercel.app`

---

## 4️⃣ Final Step: Update Backend CORS

- [ ] Go back to Render → Environment
- [ ] Update `FRONTEND_URL` with your Vercel URL
- [ ] Update `CORS_ORIGINS` with your Vercel URL
- [ ] Save (auto-redeploys)

---

## ✅ Verification

Test these URLs (replace with your actual URLs):

### Backend
- [ ] Health: `https://YOUR-BACKEND.onrender.com/api/health`
- [ ] Docs: `https://YOUR-BACKEND.onrender.com/docs`

**Expected:**
```json
{"status": "healthy", "database": "connected"}
```

### Frontend
- [ ] Visit: `https://YOUR-APP.vercel.app`
- [ ] Should load without errors
- [ ] Open browser console (F12) - no CORS errors

---

## 🔗 Your Live URLs

Write them here for reference:

```
Frontend:  https://___________________________.vercel.app
Backend:   https://___________________________.onrender.com
API Docs:  https://___________________________.onrender.com/docs
MongoDB:   cluster0._____.mongodb.net
```

---

## ⚠️ Common Issues

| Issue | Solution |
|-------|----------|
| Backend returns 503 | Check MongoDB connection string |
| CORS errors | Update `CORS_ORIGINS` in Render |
| Backend is slow | Free tier cold starts ~30s |
| Frontend shows API error | Check `VITE_API_BASE_URL` |

---

## 🎉 Done!

Your app is live and ready to demo. Share your frontend URL with others.

**Next:** See `DEPLOYMENT_GUIDE.md` for custom domains, monitoring, and advanced features.
