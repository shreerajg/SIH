# Deploy Everything to Vercel (No Card Required!)

Deploy both frontend and backend to Vercel completely free - no credit card needed!

---

## 🎯 Why Vercel for Everything?

✅ **No credit card** required  
✅ **Free tier** is generous  
✅ **One platform** for both frontend & backend  
✅ **Auto-deploy** on git push  
✅ **Built-in SSL** and CDN  

---

## 📋 Prerequisites

You have:
- ✅ MongoDB Atlas connection string
- ✅ Code ready to deploy
- ✅ GitHub account

---

## 🚀 Step-by-Step Deployment

### Step 1: Push Code to GitHub

First, commit and push all files:

```bash
git add .
git commit -m "Configure Vercel deployment"
git push origin main
```

**Don't have a GitHub repo yet?**
1. Go to [github.com](https://github.com) → New Repository
2. Name it: `sih-bis-platform` (or your choice)
3. **Don't** initialize with README (you already have code)
4. Then:

```bash
git remote add origin https://github.com/YOUR_USERNAME/sih-bis-platform.git
git branch -M main
git push -u origin main
```

---

### Step 2: Sign Up for Vercel

1. Go to **[vercel.com/signup](https://vercel.com/signup)**
2. Click **"Continue with GitHub"**
3. Authorize Vercel to access your repositories
4. ✅ **No credit card required!**

---

### Step 3: Import Your Project

1. In Vercel Dashboard, click **"Add New..."** → **"Project"**
2. Find your repository in the list
3. Click **"Import"**

---

### Step 4: Configure Project Settings

Vercel will show configuration screen:

#### Framework Preset
- Select: **Other**

#### Root Directory
- Leave as: `.` (root)

#### Build Settings
- **Build Command**: `cd frontend && npm install && npm run build`
- **Output Directory**: `frontend/dist`
- **Install Command**: `npm install`

---

### Step 5: Environment Variables

Click **"Environment Variables"** and add these:

| Name | Value |
|------|-------|
| `MONGO_URI` | `mongodb+srv://shreerajgudade124_db_user:dXZjaULWBvLpParP@cluster0.yb7hjpt.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0` |
| `MONGO_DB_NAME` | `sih26107` |
| `MONGO_TIMEOUT_MS` | `8000` |
| `APP_ENV` | `production` |
| `LLM_PROVIDER` | `auto` |
| `PYTHONPATH` | `backend` |

**For Frontend:**
| Name | Value |
|------|-------|
| `VITE_API_BASE_URL` | `/api` |

---

### Step 6: Deploy!

1. Click **"Deploy"**
2. Wait 3-5 minutes for build
3. You'll get a URL like: `https://sih-bis-platform.vercel.app`

---

## ✅ Verify Deployment

### Test Backend
Visit: `https://your-app.vercel.app/api/health`

Should return:
```json
{"status": "healthy", "database": "connected"}
```

### Test API Docs
Visit: `https://your-app.vercel.app/api/docs`

Should show FastAPI interactive documentation.

### Test Frontend
Visit: `https://your-app.vercel.app`

Should load your React app!

---

## 🎨 Your Live URLs

After deployment:

```
🌐 Full App:    https://your-app.vercel.app
📡 Backend API: https://your-app.vercel.app/api
📚 API Docs:    https://your-app.vercel.app/docs
💚 Health:      https://your-app.vercel.app/api/health
```

Everything on one domain! 🎉

---

## 🔄 Updating Your App

Every time you push to GitHub, Vercel automatically deploys:

```bash
# Make changes to your code
git add .
git commit -m "Add new feature"
git push origin main
```

Vercel will:
1. Detect the push
2. Build your app
3. Deploy automatically
4. Show you the new URL

---

## 📊 Vercel Free Tier Limits

- **100 GB** bandwidth per month
- **100** deployments per day
- **Unlimited** projects
- **Serverless Functions**: 100 GB-hours
- **1000 GB** edge network requests

**Perfect for demos and small-medium projects!**

---

## 🔧 Troubleshooting

### Build fails

**Check build logs:**
1. Go to Vercel Dashboard
2. Click your project → Deployments
3. Click the failed deployment
4. View logs

**Common fixes:**
- Make sure all dependencies are in `requirements.txt`
- Check `package.json` is in `frontend/` folder
- Verify paths in `vercel.json`

### Backend returns 500 error

**Check Function logs:**
1. Dashboard → Project → Functions
2. Select the failing function
3. View logs

**Common fixes:**
- Verify MongoDB connection string is correct
- Check MongoDB Network Access allows `0.0.0.0/0`
- Increase `MONGO_TIMEOUT_MS` to `15000`

### Frontend can't reach backend

**Solution:**
- The backend is at `/api` path, not external URL
- Make sure `VITE_API_BASE_URL=/api` (no domain)
- Check browser console (F12) for errors

### MongoDB connection timeout

**Solution:**
1. Go to MongoDB Atlas → Network Access
2. Make sure `0.0.0.0/0` is whitelisted
3. Try connection string in local test first

---

## 💡 Pro Tips

### 1. Environment Variables
- Use different values for **Production**, **Preview**, and **Development**
- Vercel lets you set per-environment variables

### 2. Preview Deployments
- Every pull request gets its own preview URL
- Test before merging to main!

### 3. Custom Domain (Optional)
- Go to Project Settings → Domains
- Add your custom domain (free SSL included!)

### 4. Analytics
- Vercel provides free analytics
- Settings → Analytics → Enable

### 5. Monitor Performance
- Dashboard shows response times
- Function execution logs
- Bandwidth usage

---

## 🔐 Security Best Practices

### ✅ What We Did Right:
1. Environment variables (not hardcoded)
2. MongoDB credentials in Vercel secrets
3. CORS configured properly
4. HTTPS automatic (Vercel provides SSL)

### 🛡️ Additional Security:
1. **MongoDB**: Restrict IP to Vercel's IPs (optional)
2. **Rate limiting**: Add to FastAPI for production
3. **Rotate secrets**: Change MongoDB password regularly

---

## 📈 Next Steps

### Immediate:
- [ ] Test all API endpoints at `/api/docs`
- [ ] Test frontend functionality
- [ ] Share your live URL!

### Optional:
- [ ] Add custom domain
- [ ] Enable Vercel Analytics
- [ ] Set up GitHub Actions for testing
- [ ] Add more demo data

---

## 🆘 Need Help?

### Vercel Resources:
- **Docs**: https://vercel.com/docs
- **Discord**: https://vercel.com/discord
- **Support**: Help button in dashboard

### Project-Specific Issues:
- Check `DEPLOYMENT_GUIDE.md` for detailed info
- See `QUICK_DEPLOY.md` for checklist
- Your MongoDB info in `DEPLOYMENT_CONFIG.md`

---

## 🎉 Success!

Your entire BIS Standards Intelligence Platform is now live on Vercel!

**Share your URL**: `https://your-app.vercel.app`

Both frontend and backend are deployed, connected to MongoDB Atlas, and ready for demos! 🚀

---

## 📝 Quick Commands Reference

```bash
# Check git status
git status

# Add all changes
git add .

# Commit with message
git commit -m "Your message"

# Push to GitHub (triggers Vercel deploy)
git push origin main

# Check deployment status (in Vercel Dashboard)
# Or install Vercel CLI:
npm i -g vercel
vercel --prod
```

---

**You're all set!** Let me know if you need help with any step! 🎯
