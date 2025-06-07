# Calendar Agent Backend

A FastAPI-based backend service for a calendar AI agent that integrates with Google Calendar and provides conversational AI capabilities.

## Features

- 🔐 **Multi-User Authentication**: Secure Google OAuth2 integration with JWT tokens
- 📅 **Google Calendar Integration**: Full read/write access to user calendars with encrypted credential storage
- 🤖 **AI-Powered Calendar Assistant**: Autonomous agent with natural language processing for calendar management
- 💾 **Persistent Conversations**: Database-backed conversation history and user management
- ⚡ **Persistent Action Approval**: Database-backed approval workflow for calendar modifications with auto-expiry
- 🛡️ **Security-First Design**: Encrypted credentials, per-user isolation, and secure token management

## Quick Start

### Prerequisites

- Python 3.8+
- Google Cloud Project with Calendar API enabled
- Virtual environment (recommended)

### 1. Environment Setup

```bash
# Clone and navigate to project
cd calendar-agent-backend

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration

Create a `.env` file in the project root:

```env
# Database (SQLite for development, PostgreSQL for production)
DATABASE_URL=sqlite:///./app.db

# JWT Security
SECRET_KEY=your-secret-key-change-this-in-production

# Google OAuth (from Google Cloud Console)
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret

# Encryption (generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
ENCRYPTION_KEY=your-fernet-encryption-key

# Azure AI (for conversational AI)
AZURE_AI_API_KEY=your-azure-ai-key
AZURE_AI_O4_ENDPOINT=your-azure-endpoint
AZURE_API_VERSION=your-api-version
```

### 3. Run the Application

```bash
# Development mode with auto-reload
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Or using the CLAUDE.md command
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000` with interactive docs at `http://localhost:8000/docs`.

## User Authentication Workflow

The application implements a complete multi-user authentication system:

### 1. Initial Authentication
```
User Request → GET /auth/google → Google OAuth URL
              ↓
Google Login → GET /auth/callback → User Creation/Retrieval
              ↓
Credential Storage → JWT Token → Frontend Redirect
```

### 2. Authenticated Requests
```
Client Request + JWT Token → Verify Token → Get User Context
                            ↓
Per-User Calendar Service → Encrypted Credentials → Google API
                            ↓
AI Agent with User Context → Database Operations → Response
```

### 3. Security Flow
- Google OAuth provides user identity and calendar access
- Calendar credentials are encrypted and stored per-user
- JWT tokens provide stateless session management
- All calendar operations are isolated per user
- Conversation history is maintained per user

## Database Architecture

### Database Models

The application uses SQLAlchemy ORM with the following database models:

#### User Model
- **Purpose**: Stores user account information
- **Fields**:
  - `id`: Primary key
  - `email`: Unique user email address
  - `full_name`: User's full name (optional)
  - `google_id`: Google OAuth ID for authentication
  - `is_active`: Account status flag
  - `created_at`: Account creation timestamp

#### CalendarConnection Model
- **Purpose**: Manages Google Calendar API credentials and connection status
- **Fields**:
  - `id`: Primary key
  - `user_id`: Foreign key to User
  - `google_credentials`: Encrypted JSON containing OAuth tokens
  - `is_connected`: Connection status flag
  - `last_sync`: Last synchronization timestamp
  - `created_at`: Connection creation timestamp

#### Conversation Model
- **Purpose**: Tracks user conversation sessions
- **Fields**:
  - `id`: Primary key
  - `user_id`: Foreign key to User
  - `title`: Conversation title
  - `created_at`: Creation timestamp
  - `updated_at`: Last update timestamp

#### Message Model
- **Purpose**: Stores individual messages within conversations
- **Fields**:
  - `id`: Primary key
  - `conversation_id`: Foreign key to Conversation
  - `content`: Message text content
  - `role`: Message role ('user' or 'assistant')
  - `timestamp`: Message timestamp

#### PendingAction Model
- **Purpose**: Stores pending calendar actions requiring user approval
- **Fields**:
  - `id`: Primary key
  - `action_id`: Unique action identifier
  - `user_id`: Foreign key to User
  - `action_type`: Type of action ('create_event', 'update_event', 'delete_event')
  - `description`: Human-readable action description
  - `details`: JSON containing action parameters
  - `created_at`: Action creation timestamp
  - `expires_at`: Automatic expiry timestamp (30 minutes default)

### Database Configuration

The application supports both PostgreSQL (production) and SQLite (development) databases:

```python
# Set DATABASE_URL environment variable
# PostgreSQL: postgresql://user:password@host:port/database
# SQLite: sqlite:///./app.db
```

### Database Services

#### UserService
- `get_user_by_email(db, email)`: Retrieve user by email
- `get_user_by_google_id(db, google_id)`: Retrieve user by Google ID
- `create_user(db, email, full_name, google_id)`: Create new user

#### ConversationService
- `create_conversation(db, user_id, title)`: Create new conversation
- `get_user_conversations(db, user_id)`: Get all user conversations
- `add_message(db, conversation_id, content, role)`: Add message to conversation
- `get_conversation_messages(db, conversation_id)`: Get conversation messages

#### CalendarService
- `save_calendar_credentials(db, user_id, credentials_dict)`: Store encrypted credentials
- `get_calendar_credentials(db, user_id)`: Retrieve decrypted credentials

#### PendingActionService
- `create_pending_action(db, user_id, action_id, action_type, description, details)`: Store new pending action
- `get_user_pending_actions(db, user_id)`: Get active pending actions for user
- `get_pending_action(db, action_id, user_id)`: Get specific action by ID
- `delete_pending_action(db, action_id, user_id)`: Remove action after approval/rejection
- `cleanup_expired_actions(db)`: Remove expired actions automatically

## Authentication System

### JWT Token Authentication

The application uses JWT (JSON Web Tokens) for authentication with the following configuration:

- **Algorithm**: HS256
- **Token Expiry**: 30 minutes (configurable)
- **Security**: HTTPBearer token scheme

### Authentication Flow

1. **Token Creation**: 
   ```python
   AuthService.create_access_token(data, expires_delta)
   ```

2. **Token Verification**:
   ```python
   AuthService.verify_token(token)
   ```

3. **User Authentication Dependency**:
   ```python
   get_current_user(credentials, db)
   ```

### Google OAuth Integration

The application integrates with Google OAuth for user authentication and calendar access:

- **Scopes**: 
  - `https://www.googleapis.com/auth/calendar` (Calendar read/write access)
  - `https://www.googleapis.com/auth/userinfo.email` (User email)
  - `https://www.googleapis.com/auth/userinfo.profile` (User profile)
- **Redirect URI**: `http://localhost:8000/auth/callback`
- **Required Environment Variables**:
  - `GOOGLE_CLIENT_ID`
  - `GOOGLE_CLIENT_SECRET`

### Security Features

#### Credential Encryption
Google Calendar credentials are encrypted before storage using Fernet symmetric encryption:

```python
# Credentials are encrypted with ENCRYPTION_KEY
cipher_suite = Fernet(ENCRYPTION_KEY)
encrypted_credentials = cipher_suite.encrypt(credentials_json.encode())
```

#### Required Environment Variables

Create a `.env` file with the following variables:

```env
# Database
DATABASE_URL=postgresql://user:password@localhost:5432/calendar_agent
# or for development: sqlite:///./app.db

# JWT Security
SECRET_KEY=your-secret-key-change-this-in-production

# Google OAuth
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret

# Encryption
ENCRYPTION_KEY=your-fernet-encryption-key

# Azure AI (if using)
AZURE_AI_API_KEY=your-azure-ai-key
AZURE_AI_O4_ENDPOINT=your-azure-endpoint
AZURE_API_VERSION=your-api-version
```

## Database Setup

### Initial Setup

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Set Environment Variables**:
   Create `.env` file with required variables (see above)

3. **Initialize Database**:
   ```python
   # Tables are created automatically when running the application
   # Or manually run:
   python -c "from app.database import Base, engine; Base.metadata.create_all(bind=engine)"
   ```

### Database Migrations

The application uses Alembic for database migrations:

```bash
# Initialize Alembic (if not already done)
alembic init alembic

# Create a new migration
alembic revision --autogenerate -m "Description of changes"

# Apply migrations
alembic upgrade head
```

## Security Considerations

1. **JWT Secret**: Use a strong, unique SECRET_KEY in production
2. **Encryption Key**: Generate a secure ENCRYPTION_KEY for credential storage
3. **Database**: Use PostgreSQL with proper authentication in production
4. **HTTPS**: Enable HTTPS in production environments
5. **Token Expiry**: Consider shorter token expiry times for high-security applications

## API Endpoints Reference

### Authentication Endpoints

| Method | Endpoint | Auth Required | Description |
|--------|----------|---------------|-------------|
| `GET` | `/auth/google` | ❌ | Get Google OAuth authorization URL |
| `GET` | `/auth/callback` | ❌ | Handle Google OAuth callback |

### User Management

| Method | Endpoint | Auth Required | Description |
|--------|----------|---------------|-------------|
| `GET` | `/user/profile` | ✅ | Get current user profile |
| `GET` | `/user/conversations` | ✅ | Get user's conversation history |
| `GET` | `/user/conversations/{id}/messages` | ✅ | Get messages from specific conversation |

### Calendar Operations

| Method | Endpoint | Auth Required | Description |
|--------|----------|---------------|-------------|
| `GET` | `/calendar/events` | ✅ | Get user's calendar events (7 days) |
| `POST` | `/calendar/events` | ✅ | Create new calendar event |

### AI Agent Interaction

| Method | Endpoint | Auth Required | Description |
|--------|----------|---------------|-------------|
| `POST` | `/chat` | ✅ | Chat with AI agent |
| `POST` | `/actions/approve/{action_id}` | ✅ | Approve pending action |
| `POST` | `/actions/reject/{action_id}` | ✅ | Reject pending action |
| `GET` | `/actions/pending` | ✅ | Get pending actions |
| `GET` | `/reflection/prompt` | ✅ | Get daily reflection prompt |

### Testing & Utility

| Method | Endpoint | Auth Required | Description |
|--------|----------|---------------|-------------|
| `GET` | `/health` | ❌ | Health check |
| `POST` | `/test/agent-tools` | ✅ | Test agent capabilities |

### Example API Usage

#### 1. Authentication Flow
```bash
# Get Google OAuth URL
curl -X GET "http://localhost:8000/auth/google"

# Response: {"auth_url": "https://accounts.google.com/o/oauth2/auth?..."}
# User visits URL, completes OAuth, gets redirected with JWT token
```

#### 2. Chat with AI Agent
```bash
# Chat with agent (requires JWT token)
curl -X POST "http://localhost:8000/chat" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "What do I have scheduled today?"}'

# Response: {"response": "You have 3 meetings today...", "requires_approval": false}
```

#### 3. Create Calendar Event
```bash
# Create event directly
curl -X POST "http://localhost:8000/calendar/events" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Team Meeting",
    "start_time": "2024-01-15T10:00:00",
    "end_time": "2024-01-15T11:00:00",
    "description": "Weekly sync"
  }'
```

## Testing Guide

### 1. Environment Testing

```bash
# Test application startup
python -c "from app.main import app; print('✓ Application imports successfully')"

# Test database connection
python -c "from app.database import engine; print('✓ Database connection works')"

# Check health endpoint
curl http://localhost:8000/health
```

### 2. Authentication Testing

#### Step 1: Google OAuth Setup
1. Visit `http://localhost:8000/auth/google`
2. Copy the `auth_url` from response
3. Open URL in browser and complete Google authentication
4. Note the JWT token from redirect URL

#### Step 2: Test Protected Endpoints
```bash
# Test user profile (replace YOUR_JWT_TOKEN)
export JWT_TOKEN="your_actual_jwt_token_here"

# Get user profile
curl -H "Authorization: Bearer $JWT_TOKEN" \
     http://localhost:8000/user/profile

# Get calendar events
curl -H "Authorization: Bearer $JWT_TOKEN" \
     http://localhost:8000/calendar/events
```

### 3. AI Agent Testing

#### Basic Conversation
```bash
# Test different types of queries
echo '# Calendar Reading'
curl -X POST http://localhost:8000/chat \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "What meetings do I have today?"}'

echo '\n# Schedule Analysis'
curl -X POST http://localhost:8000/chat \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "Find me a free hour tomorrow afternoon"}'

echo '\n# Event Creation (requires approval)'
curl -X POST http://localhost:8000/chat \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "Schedule a 1-hour team meeting for tomorrow at 2 PM"}'
```

#### Action Approval Testing
```bash
# Get pending actions (now persistent in database)
curl -H "Authorization: Bearer $JWT_TOKEN" \
     http://localhost:8000/actions/pending

# Sample response with pending action
# {
#   "pending_actions": [
#     {
#       "action_id": "create_1_1672531200",
#       "description": "Create 'Team Meeting' from 2024-01-15 14:00 to 15:00",
#       "type": "create_event",
#       "details": {
#         "title": "Team Meeting",
#         "start_time": "2024-01-15T14:00:00-05:00",
#         "end_time": "2024-01-15T15:00:00-05:00"
#       }
#     }
#   ]
# }

# Approve action (replace ACTION_ID)
curl -X POST http://localhost:8000/actions/approve/create_1_1672531200 \
  -H "Authorization: Bearer $JWT_TOKEN"

# Or reject action
curl -X POST http://localhost:8000/actions/reject/create_1_1672531200 \
  -H "Authorization: Bearer $JWT_TOKEN"

# Note: Actions automatically expire after 30 minutes
```

### 4. Automated Testing

```bash
# Test all agent capabilities
curl -X POST http://localhost:8000/test/agent-tools \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json"
```

## Troubleshooting

### Common Issues

#### 1. "Calendar not connected" Error
- **Cause**: User hasn't completed Google OAuth flow
- **Solution**: Visit `/auth/google` and complete authentication

#### 2. "Could not validate credentials" Error
- **Cause**: Invalid or expired JWT token
- **Solution**: Re-authenticate through Google OAuth flow

#### 3. Database Connection Issues
- **Cause**: Invalid DATABASE_URL or missing database
- **Solution**: Check `.env` file and ensure database exists

#### 4. Google API Errors
- **Cause**: Invalid Google Cloud credentials or API not enabled
- **Solution**: Verify Google Cloud Console setup and API permissions

#### 5. Encryption Key Errors
- **Cause**: Invalid or missing ENCRYPTION_KEY
- **Solution**: Generate new key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`

### Debug Mode

```bash
# Run with debug logging
LOG_LEVEL=DEBUG python -m uvicorn app.main:app --reload

# Check application logs for detailed error information
```

### Environment Validation

```python
# Validate all required environment variables
python -c "
from app.config import *
print('✓ All environment variables loaded successfully')
print(f'Database: {DATABASE_URL[:20]}...')
print(f'Google Client ID: {GOOGLE_CLIENT_ID[:20]}...')
"
```

## Production Deployment

### Security Checklist
- [ ] Use PostgreSQL database with authentication
- [ ] Enable HTTPS with valid SSL certificates
- [ ] Use strong, unique SECRET_KEY and ENCRYPTION_KEY
- [ ] Configure proper CORS origins (remove `allow_origins=["*"]`)
- [ ] Set up proper logging and monitoring
- [ ] Implement rate limiting
- [ ] Regular security updates

### Docker Deployment

```dockerfile
# Example Dockerfile
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## Dependencies

Key dependencies for database and authentication:

- **FastAPI**: Web framework
- **SQLAlchemy**: ORM for database operations
- **Alembic**: Database migration tool
- **python-jose**: JWT token handling
- **passlib**: Password hashing utilities
- **cryptography**: Encryption for sensitive data
- **psycopg2-binary**: PostgreSQL adapter
- **google-auth-oauthlib**: Google OAuth integration
- **pydantic-ai**: AI agent framework
- **google-api-python-client**: Google Calendar API client