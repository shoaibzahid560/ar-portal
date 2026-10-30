"""
Test settings. Environment variables take priority over .env, so tests never use the developer's
database or Google credentials. Database tests use TEST_DATABASE_URL instead (see tests/db.py).
"""

import os
import tempfile

os.environ["APP_ENV"] = "local"
os.environ["DATABASE_URL"] = ""
os.environ["WEB_ORIGIN"] = "http://localhost:3000"
os.environ["GOOGLE_CLIENT_ID"] = "test-client-id.apps.googleusercontent.com"
os.environ["GOOGLE_CLIENT_SECRET"] = "test-client-secret"
os.environ["ALLOWED_GOOGLE_DOMAIN"] = "example.com"
os.environ["LOCAL_STORAGE_DIR"] = tempfile.mkdtemp(prefix="ar-portal-test-storage-")
os.environ["BUSINESS_TIMEZONE"] = "Asia/Karachi"
