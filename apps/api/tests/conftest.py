"""Tests never use the developer's .env database: environment variables take priority over .env."""

import os

os.environ["APP_ENV"] = "local"
os.environ["DATABASE_URL"] = ""
