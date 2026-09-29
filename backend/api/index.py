import sys
import os

# Add parent directory to path so we can import app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mangum import Mangum
from app.main import app

# Wrap FastAPI app with Mangum for Vercel serverless deployment
handler = Mangum(app, lifespan="off")

# Export for Vercel
app = handler
