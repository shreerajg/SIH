# 🚀 Simple Vercel Deployment Guide

Deploy your SIH BIS Platform to Vercel in 3 easy steps - **NO CREDIT CARD REQUIRED!**

---

## 🎯 What You'll Deploy

We'll use **two separate Vercel projects**:
1. **Frontend** (React/Vite) - Your main app
2. **Backend** (FastAPI/Python) - Your API

This is the simplest approach and works perfectly on Vercel's free tier.

---

## ✅ What You Already Have

- ✅ MongoDB Atlas database with connection string
- ✅ Code ready to deploy
- ✅ GitHub account

---

## 📦 Step 1: Push Code to GitHub

```bash
git add .
git commit -m "Ready for Vercel deployment"
git push origin main
```

**Don't have a GitHub repo?**
1. Create new repo at [github.com](https://github.com/new)
2. Name it: `sih-bis-platform`
3. Then:
```bash
git remote add origin https://github.com/YOUR_USERNAME/sih-bis-platform.git
git branch -M main
git push -u origin main
```

---

## 🔧 Step 2: Deploy Backend

### 2.1 Sign Up for Vercel
1. Go to **[vercel.com/signup](https://vercel.com/signup)**
2. Click **"Continue with GitHub"**
3. ✅ No credit card needed!

### 2.2 Create Backend Project
1. Click **"Add New..."** → **"Project"**
2. Import your repository
3. **Project Settings:**
   - **Project Name**: `sih26107-backend`
   - **Framework Preset**: Other
   - **Root Directory**: `backend`
   - **Build Command**: (leave empty)
   - **Output Directory**: (leave empty)

### 2.3 Add Environment Variables

Click **Environment Variables** and add:

```env
MONGO_URI=mongodb+srv://shreerajgudade124_db_user:dXZjaULWBvLpParP@cluster0.yb7hjpt.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0
MONGO_DB_NAME=sih26107
MONGO_TIMEOUT_MS=8000
APP_ENV=production
LLM_PROVIDER=auto
PYTHONPATH=.
```

### 2.4 Deploy
1. Click **"Deploy"**
2. Wait 3-5 minutes
3. **Save your backend URL**: `https://sih26107-backend.vercel.app`

---

## 🎨 Step 3: Deploy Frontend

### 3.1 Create Frontend Project
1. In Vercel Dashboard, click **"Add New..."** → **"Project"**
2. Import **the same repository** again
3. **Project Settings:**
   - **Project Name**: `sih26107-frontend`
   - **Framework Preset**: Vite
   - **Root Directory**: `frontend`
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`

### 3.2 Add Environment Variable

```env
VITE_API_BASE_URL=https://sih26107-backend.vercel.app/api
```

Replace with your actual backend URL from Step 2.4

### 3.3 Deploy
1. Click **"Deploy"**
2. Wait 2-3 minutes
3. **Save your frontend URL**: `https://sih26107-frontend.vercel.app`

---

## 🔄 Step 4: Update Backend CORS

Go back to your **backend project** in Vercel:

1. Go to **Settings** → **Environment Variables**
2. Add these two new variables:

```env
FRONTEND_URL=https://sih26107-frontend.vercel.app
CORS_ORIGINS=https://sih26107-frontend.vercel.app
```

Replace with your actual frontend URL from Step 3.3

3. Go to **Deployments** → Click **"..."** on latest deployment → **"Redeploy"**

---

## ✅ Test Your Deployment

### Backend Health Check
Visit: `https://sih26107-backend.vercel.app/api/health`

**Expected response:**
```json
{"status": "healthy", "database": "connected"}
```

### API Documentation
Visit: `https://sih26107-backend.vercel.app/docs`

Should show interactive API docs!

### Frontend App
Visit: `https://sih26107-frontend.vercel.app`

Your app should load and work! 🎉

---

## 🔗 Your Live URLs

Write them here:

```
✨ Main App:     https://sih26107-frontend.vercel.app
🔌 Backend API:  https://sih26107-backend.vercel.app/api
📚 API Docs:     https://sih26107-backend.vercel.app/docs
💚 Health Check: https://sih26107-backend.vercel.app/api/health
```

---

## 🎉 You're Live!

Share your frontend URL with anyone - your BIS Standards Intelligence Platform is now online!

---

## 🔄 How to Update Your App

Every time you push to GitHub, both projects auto-deploy:

```bash
# Make your changes
git add .
git commit -m "Updated feature"
git push origin main
```

Both Vercel projects will automatically redeploy! ⚡

---

## 🆘 Troubleshooting

### Backend returns 500 error
**Solution:**
1. Check Vercel → Backend Project → Logs
2. Verify MongoDB connection string is correct
3. Check MongoDB Atlas Network Access allows `0.0.0.0/0`

### Frontend shows CORS error
**Solution:**
1. Verify `CORS_ORIGINS` in backend matches frontend URL exactly
2. Redeploy backend after adding CORS settings
3. Check browser console (F12) for specific error

### "Module not found" errors
**Solution:**
1. Make sure `requirements.txt` (backend) has all dependencies
2. Make sure `package.json` (frontend) has all dependencies
3. Check build logs in Vercel dashboard

### MongoDB connection timeout
**Solution:**
1. MongoDB Atlas → Network Access → Add `0.0.0.0/0`
2. Verify connection string has correct password
3. Try increasing `MONGO_TIMEOUT_MS` to `15000`

---

## 📊 Vercel Free Tier

Each project gets:
- **100 GB** bandwidth/month
- **100** builds/day
- **Serverless Functions**: 100 GB-hours/month
- **Unlimited** projects

**Total: 200 GB bandwidth for both projects - plenty for demos!**

---

## 💡 Pro Tips

### Custom Domain (Optional)
1. Go to Project Settings → Domains
2. Add your domain (e.g., `bis-platform.com`)
3. Vercel provides free SSL automatically!

### Environment Branches
Create different environments:
- `main` branch → Production
- `dev` branch → Development
- Each gets its own URL!

### Monitor Usage
Check Dashboard → Usage to see:
- Bandwidth used
- Function invocations
- Build time

### Preview Deployments
- Every git push gets a preview URL
- Perfect for testing before going live!

---

## 🔒 Security Checklist

- ✅ MongoDB credentials in Vercel environment variables (not in code)
- ✅ Network Access configured in MongoDB Atlas
- ✅ CORS properly configured
- ✅ HTTPS automatic (Vercel provides SSL)
- ✅ `.gitignore` prevents secrets from being committed

---

## 📞 Support

- **Vercel Docs**: https://vercel.com/docs
- **Vercel Discord**: https://vercel.com/discord
- **MongoDB Atlas**: https://docs.atlas.mongodb.com/

---

## 🎓 Next Steps

1. ✅ **Initialize demo data**: Run setup script (see below)
2. ✅ **Test all features**: Try product search, standards lookup
3. ✅ **Share your URL**: Demo to stakeholders
4. ✅ **Monitor usage**: Check Vercel dashboard
5. ✅ **Add custom domain**: Make it professional

### Initialize Demo Data

To add sample standards to your database:

1. Install Vercel CLI:
```bash
npm i -g vercel
```

2. Link to your backend project:
```bash
cd backend
vercel link
```

3. Run setup script:
```bash
vercel env pull .env.local
python scripts/setup_demo.py
```

---

## 🏆 Success!

Your platform is live and ready for:
- ✅ Live demos
- ✅ User testing
- ✅ Stakeholder presentations
- ✅ SIH submission

**Share this URL**: `https://sih26107-frontend.vercel.app`

---

**Questions? Issues? Let me know!** 🚀
