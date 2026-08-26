# AI Agent Test Platform - Deployment Guide

## System Architecture

The AI Agent Test Platform consists of:
1. **Frontend**: React 18 + TypeScript + Ant Design (port 3000)
2. **Backend**: Python FastAPI (port 8000)
3. **Database**: SQLite (development) / PostgreSQL (production)

## Prerequisites

- Node.js 18+ and npm
- Python 3.9+
- Git

## Quick Start

### 1. Start Backend Server

```bash
cd backend
pip install -r requirements-minimal.txt
python clean_backend.py
```

Backend will be available at: http://localhost:8000
- API Documentation: http://localhost:8000/docs
- Health Check: http://localhost:8000/health

### 2. Start Frontend Server

```bash
cd frontend
npm install
npm start
```

Frontend will be available at: http://localhost:3000

## API Endpoints

### Authentication
- `POST /api/v1/auth/login` - User login
- `POST /api/v1/auth/register` - User registration
- `GET /api/v1/auth/me` - Get current user
- `POST /api/v1/auth/logout` - User logout

### RAG Testing
- `GET /api/v1/rag/documents` - Get document list
- `POST /api/v1/rag/query` - Query documents

### SKILLS Management
- `GET /api/v1/skills` - Get SKILLS list

### Testing
- `GET /api/v1/tests/functional` - Get functional tests
- `GET /api/v1/tests/api` - Get API tests

### Reports
- `GET /api/v1/reports` - Get test reports

## Default Credentials

- **Admin**: `admin` / `password123`
- **User**: `user` / `password123`

## Environment Configuration

### Backend (.env file in backend/)
```
APP_ENV=development
DATABASE_URL=sqlite:///./test.db
SECRET_KEY=your-secret-key-here
JWT_SECRET_KEY=your-jwt-secret-key-here
```

### Frontend (.env file in frontend/)
```
REACT_APP_API_URL=http://localhost:8000/api/v1
REACT_APP_ENV=development
```

## Testing the Integration

1. **Backend Health**: `curl http://localhost:8000/health`
2. **Login Test**: 
   ```bash
   curl -X POST http://localhost:8000/api/v1/auth/login \
     -H "Content-Type: application/json" \
     -d '{"username":"admin","password":"password123"}'
   ```
3. **Frontend Connection**: Open http://localhost:3000 in browser

## Troubleshooting

### Backend won't start
- Check if port 8000 is already in use: `netstat -ano | findstr :8000`
- Kill existing processes: `taskkill /f /im python.exe`

### Frontend can't connect to backend
- Verify backend is running on port 8000
- Check CORS configuration in backend
- Verify frontend API URL is set to `http://localhost:8000/api/v1`

### Authentication issues
- Check token is being sent in Authorization header
- Verify JWT secret key is configured

## Production Deployment

### Backend (Production)
1. Use PostgreSQL instead of SQLite
2. Set `APP_ENV=production`
3. Use proper SSL certificates
4. Configure firewall rules

### Frontend (Production)
1. Build for production: `npm run build`
2. Serve with Nginx or similar
3. Configure HTTPS

## Monitoring

- Backend logs: Check console output or log files
- Frontend logs: Browser developer tools
- API monitoring: Available at `/api/v1/monitoring`

## Support

For issues or questions:
1. Check the API documentation at http://localhost:8000/docs
2. Review server logs for error messages
3. Verify all services are running and accessible