# Contributing to Calendar Agent Backend

Thank you for your interest in contributing to Calendar Agent Backend! This document provides guidelines and instructions for contributing to this project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Making Contributions](#making-contributions)
- [Pull Request Process](#pull-request-process)
- [Coding Standards](#coding-standards)
- [Testing Guidelines](#testing-guidelines)
- [Issue Reporting](#issue-reporting)

## Code of Conduct

This project adheres to a [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code. Please report unacceptable behavior to the project maintainers.

## Getting Started

1. **Fork the repository** on GitHub
2. **Clone your fork** locally:
   ```bash
   git clone https://github.com/your-username/calendar-agent-backend.git
   cd calendar-agent-backend
   ```
3. **Set up the upstream remote**:
   ```bash
   git remote add upstream https://github.com/original-owner/calendar-agent-backend.git
   ```

## Development Setup

### Prerequisites

- Python 3.8 or higher
- Virtual environment tool (venv, conda, etc.)
- Google Cloud Project with Calendar API enabled
- Azure OpenAI account (for AI features)

### Local Development Environment

1. **Create and activate virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   # or
   venv\Scripts\activate     # Windows
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Environment configuration**:
   ```bash
   # Copy the example environment file
   cp .env.example .env
   
   # Edit .env with your configuration values
   # See README.md for detailed setup instructions
   ```

4. **Database setup**:
   ```bash
   # Initialize database (automatic on first run)
   python -c "from app.database import Base, engine; Base.metadata.create_all(bind=engine)"
   
   # Or use Alembic for migrations
   alembic upgrade head
   ```

5. **Run the development server**:
   ```bash
   python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

### Docker Development (Alternative)

If you prefer using Docker:

```bash
# Build and run with docker-compose
docker-compose up --build

# The API will be available at http://localhost:8000
```

## Making Contributions

### Types of Contributions

We welcome various types of contributions:

- **Bug fixes**
- **Feature enhancements**
- **Documentation improvements**
- **Test coverage improvements**
- **Performance optimizations**
- **Security improvements**

### Before Starting

1. **Check existing issues** to see if your contribution is already being worked on
2. **Create an issue** for new features or major changes to discuss the approach
3. **Keep changes focused** - one feature or fix per pull request

### Branch Naming Convention

Use descriptive branch names that clearly indicate the purpose:

- `feature/add-calendar-sync`
- `bugfix/fix-auth-token-expiry`
- `docs/update-api-documentation`
- `refactor/improve-database-queries`

## Pull Request Process

1. **Update from upstream** before creating your PR:
   ```bash
   git fetch upstream
   git checkout main
   git merge upstream/main
   ```

2. **Create a feature branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

3. **Make your changes** and commit with clear, descriptive messages:
   ```bash
   git add .
   git commit -m "Add feature: brief description of changes"
   ```

4. **Run tests and linting** (when available):
   ```bash
   pytest
   # Add any linting commands when implemented
   ```

5. **Push to your fork**:
   ```bash
   git push origin feature/your-feature-name
   ```

6. **Create a Pull Request** on GitHub with:
   - Clear title describing the change
   - Detailed description of what was changed and why
   - Reference to any related issues
   - Screenshots or demos for UI changes

### Pull Request Requirements

- [ ] Code follows the project's coding standards
- [ ] Tests are added for new functionality (when applicable)
- [ ] Documentation is updated if needed
- [ ] No merge conflicts with the main branch
- [ ] All CI checks pass (when implemented)

## Coding Standards

### Python Code Style

- Follow [PEP 8](https://www.python.org/dev/peps/pep-0008/) Python style guidelines
- Use type hints where appropriate
- Write descriptive variable and function names
- Keep functions focused and reasonably sized

### Code Organization

- Follow the existing project structure
- Place new modules in appropriate directories
- Update `__init__.py` files when adding new modules
- Use relative imports within the application

### Documentation

- Add docstrings to all public functions and classes
- Use clear, descriptive commit messages
- Update README.md for significant changes
- Document any new environment variables in `.env.example`

### Security Considerations

- Never commit secrets, API keys, or credentials
- Use environment variables for all configuration
- Follow security best practices for authentication and data handling
- Review the security implications of any changes

## Testing Guidelines

### Writing Tests

- Write tests for new functionality
- Use pytest as the testing framework
- Place tests in appropriate test directories
- Follow existing test patterns and conventions

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app

# Run specific test file
pytest tests/test_specific_module.py
```

### Test Requirements

- Tests should be independent and not rely on external state
- Mock external services (Google APIs, Azure AI, etc.)
- Test both success and error cases
- Ensure tests are deterministic

## Issue Reporting

### Bug Reports

When reporting bugs, please include:

- **Environment details** (Python version, OS, etc.)
- **Steps to reproduce** the issue
- **Expected behavior** vs **actual behavior**
- **Error messages** or logs (with sensitive data removed)
- **Screenshots** if applicable

### Feature Requests

For feature requests, please provide:

- **Clear description** of the proposed feature
- **Use case** and motivation
- **Possible implementation approach** (if you have ideas)
- **Alternatives considered**

## Development Tips

### Working with the Multi-Agent Architecture

- Understand the agent routing system in `main_agent.py`
- Each agent has specific responsibilities (calendar, reflection, profile)
- Follow the existing patterns for agent communication
- Test agent interactions thoroughly

### Database Changes

- Use Alembic migrations for schema changes
- Test migrations with both SQLite (dev) and PostgreSQL (prod)
- Update model documentation when adding new fields

### API Development

- Follow FastAPI conventions and patterns
- Use Pydantic models for request/response validation
- Update API documentation for new endpoints
- Test authentication and authorization

## Getting Help

If you need help with contributing:

- Check the [README.md](README.md) for setup instructions
- Look at existing code for patterns and examples
- Create an issue to ask questions
- Review closed issues for similar problems

## Recognition

Contributors will be recognized in:
- GitHub contributors list
- Release notes for significant contributions
- Project documentation (when applicable)

Thank you for contributing to Calendar Agent Backend! 🎉