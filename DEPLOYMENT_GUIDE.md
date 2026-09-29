# Deployment Guide - SIH26107 Platform

This guide walks you through deploying your BIS Standards Intelligence Platform to production using **Render** (backend) and **Vercel** (frontend).

---

## 🎯 Quick Overview

- **Backend (FastAPI)** → Deploy to **Render** (Free tier available)
- **Frontend (React/Vite)** → Deploy to **Vercel** (Free tier available)
- **Database** → **MongoDB Atlas** (Free tier available)

---

## Part 1: Setup MongoDB Atlas (Database)

### Step 1: Create MongoDB Atlas Account
1. Go to [https://www.mongodb.com/cloud/atlas/register](https://www.mongodb.com/cloud/atlas/register)
2. Sign up with your email or Google account
3. Choose the **FREE** M0 tier

### Step 2: Create a Cluster
1. After signup, click **"Build a Database"**
2. Choose **M0 FREE** tier
3. Select a region close to you (e.g., Mumbai/Singapore for India)
4. Click **"Create Cluster"**

### Step 3: Create Database User
1. Click **"Database Access"** in the left sidebar
2. Click **"Add New Database User"**
3. Choose **"Password"** authentication
4. Username: `sih26107_user` (or your choice)
5. Click **"Autogenerate Secure Password"** and **SAVE THIS PASSWORD**
6. Database User Privileges: Select **"Read and write to any database"**
7. Click **"Add User"**

### Step 4: Whitelist IP Addresses
1. Click **"Network Access"** in the left sidebar
2. Click **"Add IP Address"**
3. Click **"Allow Access from Anywhere"** (or add `0.0.0.0/0`)
   - This allows Render to connect (Render uses dynamic IPs)
4. Click **"Confirm"**

### Step 5: Get Connection String
1. Click **"Database"** in the left sidebar
2. Click **"Connect"** on your cluster
3. Choose **"Connect your application"**
4. Copy the connection string (looks like):
   ```
   mongodb+srv://sih26107_user:<password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
   ```
5. **Replace `<password>`** with the password you saved earlier
6. **SAVE THIS CONNECTION STRING** - you'll need it for Render

---

## Part 2: Deploy Backend to Render

### Step 1: Push Code to GitHub
1. Make sure your code is committed:
   ```bash
   git add .
   git commit -m "Prepare for deployment"
   ```

2. Create a GitHub repository and push:
   ```bash
   git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
   git branch -M main
   git push -u origin main
   ```

### Step 2: Create Render Account
1. Go to [https://render.com/](https://render.com/)
2. Click **"Get Started for Free"**
3. Sign up with GitHub (recommended - easier deployment)

### Step 3: Deploy from Blueprint
1. From Render Dashboard, click **"New +"** → **"Blueprint**
2. Connect your GitHub repository
3. Give it a name: `sih26107-platform`
4. Click **"Apply"**

### Step 4: Configure Environment Variables
Render will create the service. Now set these environment variables:

1. Go to your service → **"Environment"** tab
2. Add these variables:

| Key | Value | Notes |
|-----|-------|-------|
| `MONGO_URI` | `mongodb+srv://user:pass@...` | Your Atlas connection string |
| `MONGO_DB_NAME` | `sih26107` | Database name |
| `MONGO_TIMEOUT_MS` | `8000` | Connection timeout |
| `FRONTEND_URL` | `https://your-app.vercel.app` | Set after frontend deploy |
| `CORS_ORIGINS` | `https://your-app.vercel.app` | Set after frontend deploy |
| `LLM_PROVIDER` | `auto` | Optional - for AI features |
| `LLM_API_KEY` | (leave empty) | Optional - add if using OpenAI/Anthropic |
| `LLM_MODEL` | (leave empty) | Optional |
| `APP_ENV` | `production` | Already set in render.yaml |

3. Click **"Save Changes"**

### Step 5: Get Your Backend URL
1. After deployment completes, copy your backend URL:
   ```
   https://sih26107-api.onrender.com
   ```
2. **SAVE THIS URL** - you'll need it for the frontend

### Step 6: Initialize Demo Data
1. In Render Dashboard, go to your service
2. Click **"Shell"** tab (opens terminal)
3. Run:
   ```bash
   python scripts/setup_demo.py
   ```
4. This will populate your MongoDB with sample standards data

### Backend Health Check
Visit: `https://YOUR-BACKEND-URL.onrender.com/api/health`

You should see:
```json
{"status": "healthy", "database": "connected"}
```

---

## Part 3: Deploy Frontend to Vercel

### Step 1: Create Vercel Account
1. Go to [https://vercel.com/signup](https://vercel.com/signup)
2. Sign up with GitHub (recommended)

### Step 2: Import Project
1. From Vercel Dashboard, click **"Add New..."** → **"Project"**
2. Import your GitHub repository
3. Vercel will auto-detect it's a Vite project

### Step 3: Configure Build Settings
Vercel should auto-fill these, but verify:

- **Framework Preset**: Vite
- **Root Directory**: `frontend`
- **Build Command**: `npm run build`
- **Output Directory**: `dist`

### Step 4: Set Environment Variables
Click **"Environment Variables"** and add:

| Key | Value |
|-----|-------|
| `VITE_API_BASE_URL` | `https://YOUR-BACKEND-URL.onrender.com/api` |

Replace `YOUR-BACKEND-URL` with your actual Render backend URL from Part 2, Step 5.

### Step 5: Deploy
1. Click **"Deploy"**
2. Wait for build to complete (2-3 minutes)
3. You'll get a URL like: `https://your-app.vercel.app`

### Step 6: Update Backend CORS Settings
Now that you have your frontend URL, go back to Render:

1. Go to Render Dashboard → Your service → **"Environment"**
2. Update these variables:
   - `FRONTEND_URL` = `https://your-app.vercel.app`
   - `CORS_ORIGINS` = `https://your-app.vercel.app`
3. Click **"Save Changes"**
4. Service will auto-redeploy

---

## 🎉 Your Live URLs

After completing all steps:

- **Frontend**: `https://your-app.vercel.app`
- **Backend API**: `https://sih26107-api.onrender.com`
- **API Health**: `https://sih26107-api.onrender.com/api/health`
- **API Docs**: `https://sih26107-api.onrender.com/docs`

---

## ⚡ Important Notes

### Render Free Tier
- **Spins down after 15 minutes of inactivity**
- First request after idle takes ~30-60 seconds (cold start)
- Good for demos, not production traffic
- Upgrade to paid plan ($7/month) for always-on service

### Vercel Free Tier
- 100GB bandwidth per month
- Unlimited deployments
- Perfect for most projects

### MongoDB Atlas Free Tier
- 512MB storage
- Shared CPU
- Enough for thousands of standards documents

---

## 🔧 Troubleshooting

### Backend won't start
- Check MongoDB connection string is correct
- Verify MongoDB Network Access allows `0.0.0.0/0`
- Check Render logs: Dashboard → Logs tab

### Frontend can't reach backend
- Verify `VITE_API_BASE_URL` is set correctly
- Check CORS settings in backend
- Open browser console (F12) to see error messages

### Database connection timeout
- Check MongoDB Atlas cluster is running
- Verify IP whitelist includes `0.0.0.0/0`
- Try increasing `MONGO_TIMEOUT_MS` to `15000`

---

## 🔄 Updating Your Deployment

### Update Backend
1. Push changes to GitHub: `git push`
2. Render auto-deploys from `main` branch

### Update Frontend
1. Push changes to GitHub: `git push`
2. Vercel auto-deploys from `main` branch

### Manual Redeploy
- **Render**: Dashboard → "Manual Deploy" → "Deploy latest commit"
- **Vercel**: Dashboard → Deployments → "Redeploy"

---

## 📊 Monitoring

### Check Backend Status
```bash
curl https://YOUR-BACKEND-URL.onrender.com/api/health
```

### View Logs
- **Render**: Dashboard → Logs tab (real-time)
- **Vercel**: Dashboard → Deployments → Select deployment → View Function Logs

---

## 🎓 Next Steps

1. ✅ Set up custom domain (optional)
2. ✅ Enable HTTPS (automatic on both platforms)
3. ✅ Set up monitoring/alerts
4. ✅ Configure CI/CD for automated testing
5. ✅ Add LLM API keys for AI features (OpenAI/Anthropic)

---

## 💡 Pro Tips

1. **Use environment branches**: Create `staging` branch for testing before production
2. **Monitor usage**: Both platforms have analytics dashboards
3. **Backup MongoDB**: Atlas has automatic backups on paid tiers
4. **SSL is automatic**: Both Render and Vercel provide free SSL certificates
5. **Preview deployments**: Vercel creates preview URLs for every PR

---

## 📞 Support

- **Render Docs**: https://render.com/docs
- **Vercel Docs**: https://vercel.com/docs
- **MongoDB Atlas Docs**: https://docs.atlas.mongodb.com/

---

**🚀 You're ready to go live!**
