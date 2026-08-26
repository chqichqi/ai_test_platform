# AI Agent Test Platform - Production Deployment Guide

## 🚀 Complete Production-Ready System

The AI Agent Test Platform is now production-ready with:
- ✅ **Real SQLite database** with data persistence
- ✅ **JWT authentication** with secure token handling
- ✅ **Production configuration** with environment variables
- ✅ **Database models** for all entities (Users, Documents, Tests, Skills, Reports)
- ✅ **API endpoints** with proper authentication and authorization
- ✅ **Deployment scripts** for both development and production

## 📁 Project Structure

```
ai-agent-test-platform/
├── frontend/                    # React frontend (port 3000)
│   ├── src/
│   │   ├── api/
│   │   │   ├── axiosConfig.ts   # API configuration
│   │   │   └── authApi.ts       # Authentication API
│   │   └── ...                  # Other frontend files
│   └── package.json
│
├── backend/                     # FastAPI backend (port 8000)
│   ├── production_backend.py    # Production backend with database
│   ├── database.py              # SQLAlchemy models & database setup
│   ├── auth_utils.py            # JWT authentication utilities
│   ├── requirements_prod.txt    # Production dependencies
│   ├── .env                     # Environment configuration
│   ├── .env.example             # Example environment file
│   ├── start_production.bat     # Windows production script
│   ├── start_development.bat    # Windows development script
│   └── start_production.sh      # Linux/Mac production script
│
└── PRODUCTION_DEPLOYMENT.md     # This file
```

## 🛠️ Quick Deployment

### Option 1: Development Mode (Auto-reload)
```bash
cd backend
start_development.bat
```

### Option 2: Production Mode
```bash
cd backend
start_production.bat
```

## 🔧 Manual Setup

### 1. Backend Setup
```bash
# Navigate to backend
cd backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate.bat
# Linux/Mac:
source venv/bin/activate

# Install dependencies
pip install -r requirements_prod.txt

# Initialize database
python -c "from database import init_database; init_database()"

# Start production server
uvicorn production_backend:app --host 0.0.0.0 --port 8000 --workers 4
```

### 2. Frontend Setup
```bash
# Navigate to frontend
cd frontend

# Install dependencies
npm install

# Start development server
npm start
```

## 🌐 Access Points

- **Frontend Application**: http://localhost:3000
- **Backend API**: http://localhost:8000/api/v1
- **API Documentation**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health

## 🔐 Default Credentials

- **Admin User**: `admin` / `admin123`
- **Regular User**: `user` / `user123`

## 📊 Database Schema

### Tables Created:
1. **users** - User authentication and profiles
2. **documents** - RAG document storage
3. **queries** - RAG query history
4. **skills** - SKILLS management
5. **tests** - Test execution records
6. **reports** - Test reports
7. **api_monitors** - API monitoring data

### Sample Data:
- 2 default users (admin, user)
- 3 sample skills (webapp-testing, xlsx, docx)
- 2 sample documents
- 2 sample tests
- 1 sample report

## 🔒 Security Features

### JWT Authentication
- Access tokens (30 min expiry)
- Refresh tokens (7 day expiry)
- Secure password hashing with bcrypt
- Role-based access control (admin/user)

### Database Security
- SQLite with proper connection handling
- Password hashing (never stored in plain text)
- User activation status control

### API Security
- CORS configured for frontend origins
- Authentication required for all endpoints
- Admin-only endpoints for sensitive operations

## ⚙️ Configuration

### Environment Variables (.env file)
```env
# Application Settings
APP_ENV=production
HOST=0.0.0.0
PORT=8000

# Database
DATABASE_URL=sqlite:///./ai_agent_test.db
# For PostgreSQL: DATABASE_URL=postgresql://user:password@localhost:5432/dbname

# Security (CHANGE THESE IN PRODUCTION!)
SECRET_KEY=your-secret-key-change-this
JWT_SECRET_KEY=your-jwt-secret-key-change-this

# CORS
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

## 🚢 Production Deployment

### 1. Docker Deployment (Recommended)
```dockerfile
# Dockerfile
FROM python:3.9-slim

WORKDIR /app

COPY requirements_prod.txt .
RUN pip install --no-cache-dir -r requirements_prod.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "production_backend:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

### 2. Cloud Deployment Options

#### A. Heroku
```bash
# Add PostgreSQL addon
heroku addons:create heroku-postgresql:hobby-dev

# Set environment variables
heroku config:set APP_ENV=production
heroku config:set SECRET_KEY=your-secret-key

# Deploy
git push heroku main
```

#### B. AWS Elastic Beanstalk
```bash
# Create requirements.txt
echo "gunicorn==21.2.0" >> requirements.txt
cat requirements_prod.txt >> requirements.txt

# Deploy
eb init
eb create ai-agent-test-platform
eb deploy
```

#### C. DigitalOcean App Platform
1. Connect GitHub repository
2. Set environment variables
3. Configure build command: `pip install -r requirements_prod.txt`
4. Configure run command: `gunicorn production_backend:app --workers 4 --worker-class uvicorn.workers.UvicornWorker`

## 📈 Monitoring & Maintenance

### Health Checks
```bash
# Check backend health
curl http://your-domain.com/health

# Check database connection
curl http://your-domain.com/api/v1/monitoring
```

### Database Backups
```bash
# Backup SQLite database
cp ai_agent_test.db ai_agent_test_backup_$(date +%Y%m%d).db

# Restore from backup
cp ai_agent_test_backup_20240321.db ai_agent_test.db
```

### Logs
- Backend logs: Console output or log files
- Access logs: HTTP request/response logging
- Error logs: Application errors and exceptions

## 🔄 Upgrading

### 1. Database Migrations
```python
# For schema changes, use Alembic (included in requirements)
alembic revision --autogenerate -m "Description of changes"
alembic upgrade head
```

### 2. Application Updates
```bash
# Pull latest code
git pull origin main

# Update dependencies
pip install -r requirements_prod.txt --upgrade

# Restart application
# (Depends on your deployment method)
```

## 🆘 Troubleshooting

### Common Issues:

1. **Port already in use**
   ```bash
   # Find and kill process
   netstat -ano | findstr :8000
   taskkill /PID <PID> /F
   ```

2. **Database connection errors**
   ```bash
   # Reinitialize database
   python -c "from database import init_database; init_database()"
   ```

3. **Authentication failures**
   - Check JWT secret keys in .env file
   - Verify token expiration
   - Check user activation status

4. **CORS errors**
   - Verify CORS origins in .env
   - Check frontend URL matches configured origins

### Getting Help:
1. Check API docs: http://localhost:8000/docs
2. Review server logs for error messages
3. Verify all services are running
4. Test with curl commands first

## 📞 Support

For issues or questions:
1. Check the API documentation
2. Review server logs
3. Test individual endpoints with curl
4. Verify database connectivity

## 🎉 Deployment Complete!

Your AI Agent Test Platform is now:
- ✅ **Production-ready** with real database
- ✅ **Secure** with JWT authentication
- ✅ **Scalable** with proper architecture
- ✅ **Maintainable** with clear documentation
- ✅ **Deployable** to any cloud platform

**Next Steps:**
1. Deploy to your preferred cloud platform
2. Set up SSL certificates (HTTPS)
3. Configure monitoring and alerts
4. Set up automated backups
5. Scale based on usage patterns