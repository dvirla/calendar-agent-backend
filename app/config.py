import os
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables from .env file
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path, override=True)

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-this")
AZURE_AI_API_KEY = os.getenv("AZURE_AI_API_KEY")
AZURE_AI_O4_ENDPOINT = os.getenv("AZURE_AI_O4_ENDPOINT")
AZURE_API_VERSION = os.getenv("AZURE_API_VERSION")
LOGFIRE_TOKEN = os.getenv("LOGFIRE_TOKEN")

# Google OAuth settings
SCOPES = ['https://www.googleapis.com/auth/calendar']
REDIRECT_URI = 'http://localhost:8000/auth/callback'
FRONTEND_URL = os.getenv("FRONTEND_URL")

# Model related config
MODEL_TEMPRATURE = float(os.getenv("MODEL_TEMPRATURE", 0.0))