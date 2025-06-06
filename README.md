# Calendar Agent Backend

A FastAPI-based backend service for a calendar AI agent that integrates with Google Calendar and provides conversational AI capabilities.

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

<!-- ## Authentication System

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

The application integrates with Google OAuth for user authentication:

- **Scopes**: `https://www.googleapis.com/auth/calendar`
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
``` -->

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