# Deploy to Railway (No Card Required!)

Railway offers free tier without credit card. Perfect for demos and small projects.

---

## 🚀 Deploy Backend to Railway

### Step 1: Sign Up
1. Go to **[railway.app](https://railway.app)**
2. Click **"Login"** or **"Start a New Project"**
3. Sign in with **GitHub** (recommended)
4. ✅ **No credit card required for free tier!**

### Step 2: Create New Project
1. Click **"New Project"**
2. Select **"Deploy from GitHub repo"**
3. Choose your repository: `SIH_Demo`
4. Railway will detect it's a Python/Docker project

### Step 3: Configure Service
1. Railway will start building automatically
2. Click on your service → **"Variables"** tab
3. Add these environment variables:

```env
MONGO_URI=mongodb+srv://shreerajgudade124_db_user:dXZjaULWBvLpParP@cluster0.yb7hjpt.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0
MONGO_DB_NAME=sih26107
MONGO_TIMEOUT_MS=8000
APP_ENV=production
LLM_PROVIDER=auto
PORT=8000
```

4. Click **"Settings"** tab:
   - **Root Directory**: Set to `backend`
   - **Start Command**: Leave as default (uses Dockerfile)

### Step 4: Get Your Backend URL
1. Go to **"Settings"** → **"Domains"**
2. Click **"Generate Domain"**
3. You'll get a URL like: `https://your-app.up.railway.app`
4. **Save this URL** - you need it for frontend!

### Step 5: Initialize Database
1. In Railway dashboard, click your service
2. Click the **three dots (...)** → **"Run Command"**
3. Enter: `python scripts/setup_demo.py`
4. Click **"Run"**

---

## 🎨 Deploy Frontend to Vercel

### Step 1: Sign Up
1. Go to **[vercel.com](https://vercel.com/signup)**
2. Sign up with **GitHub**
3. ✅ **No credit card required!**

### Step 2: Import Project
1. Click **"Add New..."** → **"Project"**
2. Select your GitHub repository
3. Configure settings:
   - **Framework Preset**: Vite
   - **Root Directory**: `frontend`
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`

### Step 3: Environment Variables
Click **"Environment Variables"** and add:

```env
VITE_API_BASE_URL=https://your-app.up.railway.app/api
```

Replace with your Railway URL from Step 4 above.

### Step 4: Deploy
1. Click **"Deploy"**
2. Wait 2-3 minutes
3. You'll get a URL like: `https://your-app.vercel.app`

---

## 🔄 Final Step: Update CORS

Go back to Railway:
1. Click your service → **"Variables"**
2. Add two more variables:

```env
FRONTEND_URL=https://your-app.vercel.app
CORS_ORIGINS=https://your-app.vercel.app
```

Replace with your actual Vercel URL.

3. Service will auto-redeploy

---

## ✅ Test Your Deployment

### Backend Health Check
Visit: `https://your-railway-app.up.railway.app/api/health`

Should return:
```json
{"status": "healthy", "database": "connected"}
```

### Frontend
Visit: `https://your-app.vercel.app`

Should load your app without errors!

---

## 📊 Railway Free Tier Limits

- **$5 free credits per month** (enough for small projects)
- **500 hours** of usage
- **100 GB** outbound bandwidth
- No credit card needed

**Pro Tip**: Railway shows usage in dashboard - keep an eye on it!

---

## 🔄 Auto-Deploy on Git Push

Both Railway and Vercel automatically deploy when you push to GitHub:

```bash
git add .
git commit -m "Update feature"
git push origin main
```

Both services will detect the push and redeploy automatically! 🚀

---

## 🆘 Troubleshooting

### Railway build fails
- Check logs in Railway dashboard
- Verify Dockerfile path is correct
- Make sure all dependencies are in requirements.txt

### Frontend can't reach backend
- Check `VITE_API_BASE_URL` matches Railway URL
- Verify CORS settings in Railway variables
- Check browser console (F12) for errors

### Database connection issues
- Verify MongoDB connection string
- Check Network Access in MongoDB Atlas (should allow `0.0.0.0/0`)
- Test connection string locally first

---

## 🎉 Done!

Your app is live without any credit card! Share your Vercel URL with others.

**Your Live URLs:**
- Frontend: `https://__________.vercel.app`
- Backend: `https://__________.up.railway.app`
- API Docs: `https://__________.up.railway.app/docs`

---

## 💡 Alternative: Student Benefits

If you're a student, get free credits:
- **GitHub Education Pack**: https://education.github.com/pack
  - Includes Heroku, DigitalOcean, Azure, and more
- **Render Student**: Free credits with .edu email
