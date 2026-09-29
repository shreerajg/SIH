# Your Deployment Configuration

**⚠️ KEEP THIS FILE PRIVATE - Contains sensitive information**

---

## 🔐 MongoDB Atlas Credentials

```
Username: shreerajgudade124_db_user
Password: dXZjaULWBvLpParP
Cluster: Cluster0
```

### Your MongoDB Connection String

Click "Drivers and Client Libraries" in the MongoDB Atlas interface to get your full connection string. It will look like:

```
mongodb+srv://shreerajgudade124_db_user:dXZjaULWBvLpParP@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0
```

**Replace `cluster0.xxxxx.mongodb.net` with your actual cluster address from Atlas.**

---

## 📝 Next Steps

### 1. Get Your Complete Connection String

1. In MongoDB Atlas, click **"Drivers and Client Libraries"** (as shown in your screenshot)
2. Select:
   - **Driver**: Python
   - **Version**: 3.6 or later
3. Copy the full connection string
4. The password will already be filled in, or replace `<password>` with: `dXZjaULWBvLpParP`

### 2. Test Connection String Format

Your final connection string should look like:
```
mongodb+srv://shreerajgudade124_db_user:dXZjaULWBvLpParP@cluster0.xxxxxx.mongodb.net/?retryWrites=true&w=majority
```

---

## 🚀 Render Deployment - Environment Variables

When you deploy to Render, set these exact values:

```env
MONGO_URI=mongodb+srv://shreerajgudade124_db_user:dXZjaULWBvLpParP@cluster0.XXXXX.mongodb.net/?retryWrites=true&w=majority
MONGO_DB_NAME=sih26107
MONGO_TIMEOUT_MS=8000
APP_ENV=production
LLM_PROVIDER=auto
FRONTEND_URL=https://YOUR-APP.vercel.app
CORS_ORIGINS=https://YOUR-APP.vercel.app
```

**IMPORTANT**: 
- Replace `cluster0.XXXXX.mongodb.net` with your actual cluster hostname from Atlas
- Update `FRONTEND_URL` and `CORS_ORIGINS` after deploying to Vercel

---

## 🎯 Vercel Deployment - Environment Variables

```env
VITE_API_BASE_URL=https://YOUR-BACKEND.onrender.com/api
```

**Replace after Render deployment**

---

## ✅ Deployment Checklist

- [x] MongoDB Atlas account created
- [x] Database user created
- [ ] Get full connection string from "Drivers and Client Libraries"
- [ ] Verify Network Access allows `0.0.0.0/0`
- [ ] Push code to GitHub
- [ ] Deploy backend to Render
- [ ] Get Render backend URL
- [ ] Deploy frontend to Vercel
- [ ] Get Vercel frontend URL
- [ ] Update Render CORS settings
- [ ] Test both URLs

---

## 🔗 Your URLs (Fill in after deployment)

```
Frontend:  https://________________________________.vercel.app
Backend:   https://________________________________.onrender.com
API Docs:  https://________________________________.onrender.com/docs
API Health: https://________________________________.onrender.com/api/health
```

---

## ⚠️ Security Notes

1. **Never commit this file to Git** (already in .gitignore)
2. **Use environment variables** in deployment platforms, not hardcoded values
3. **Rotate passwords** if exposed publicly
4. **Enable IP whitelist** in MongoDB Atlas for additional security (production)

---

## 🆘 Troubleshooting

### If MongoDB connection fails:

1. **Check Network Access**:
   - MongoDB Atlas → Network Access
   - Should show `0.0.0.0/0` (Allow from anywhere)
   - Or add Render's IP ranges

2. **Verify Connection String**:
   - Must start with `mongodb+srv://`
   - Password must be URL-encoded (no special characters issues)
   - Database name is set in `MONGO_DB_NAME` separately

3. **Test locally first**:
   ```bash
   cd backend
   export MONGO_URI="your-connection-string"
   export MONGO_DB_NAME="sih26107"
   python -c "from app.core.database import db; print(db.test_connection())"
   ```

---

## 📞 Support Links

- MongoDB Atlas Dashboard: https://cloud.mongodb.com/
- Render Dashboard: https://dashboard.render.com/
- Vercel Dashboard: https://vercel.com/dashboard

---

**Ready to deploy?** Follow the steps in `DEPLOYMENT_GUIDE.md` with these credentials!
