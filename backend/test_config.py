#!/usr/bin/env python3
"""Test script to verify configuration."""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("Testing configuration...")
print("=" * 60)

try:
    # Import settings
    from app.core.config import settings
    
    print("Configuration loaded successfully!")
    print()
    
    # Display important settings
    print("Application Settings:")
    print(f"  APP_NAME: {settings.APP_NAME}")
    print(f"  APP_VERSION: {settings.APP_VERSION}")
    print(f"  APP_ENV: {settings.APP_ENV}")
    print(f"  DEBUG: {settings.DEBUG}")
    print()
    
    print("Server Settings:")
    print(f"  HOST: {settings.HOST}")
    print(f"  PORT: {settings.PORT}")
    print(f"  API_V1_STR: {settings.API_V1_STR}")
    print()
    
    print("Database Settings:")
    print(f"  DATABASE_URL: {settings.DATABASE_URL[:50]}...")
    print(f"  DATABASE_POOL_SIZE: {settings.DATABASE_POOL_SIZE}")
    print()
    
    print("Security Settings:")
    print(f"  SECRET_KEY: {'***' if settings.SECRET_KEY else 'NOT SET'}")
    print(f"  JWT_SECRET_KEY: {'***' if settings.JWT_SECRET_KEY else 'NOT SET'}")
    print(f"  JWT_ALGORITHM: {settings.JWT_ALGORITHM}")
    print()
    
    print("CORS Settings:")
    print(f"  CORS_ORIGINS: {settings.CORS_ORIGINS}")
    print()
    
    print("File Upload Settings:")
    print(f"  UPLOAD_DIR: {settings.UPLOAD_DIR}")
    print(f"  MAX_UPLOAD_SIZE: {settings.MAX_UPLOAD_SIZE}")
    print(f"  ALLOWED_EXTENSIONS: {settings.ALLOWED_EXTENSIONS}")
    print()
    
    print("Logging Settings:")
    print(f"  LOG_LEVEL: {settings.LOG_LEVEL}")
    print(f"  LOG_FILE: {settings.LOG_FILE}")
    print()
    
    print("AI/RAG Settings:")
    print(f"  VECTOR_DB_PATH: {settings.VECTOR_DB_PATH}")
    print(f"  EMBEDDING_MODEL: {settings.EMBEDDING_MODEL}")
    print(f"  OPENAI_API_KEY: {'SET' if settings.OPENAI_API_KEY else 'NOT SET'}")
    print()
    
    print("=" * 60)
    print("SUCCESS: All configuration loaded correctly!")
    print("Application is ready to run.")
    
except Exception as e:
    print(f"ERROR: Failed to load configuration")
    print(f"Error details: {e}")
    print()
    print("Troubleshooting:")
    print("1. Check .env file exists and has correct field names")
    print("2. Check field names match Settings class")
    print("3. Check required fields are set (SECRET_KEY, DATABASE_URL, JWT_SECRET_KEY)")
    sys.exit(1)