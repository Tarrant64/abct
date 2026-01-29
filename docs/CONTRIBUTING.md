# Contributing to ABCT

Thank you for your interest in contributing to the Altcoin and Bitcoin Tracker (ABCT)!

## Documentation Guidelines

### User-Facing Documentation

Place in `docs/` or `docs/guides/`:
- Setup guides
- User manuals
- API documentation
- Architecture overviews
- Migration guides
- Backup/restore guides

These files should be:
- Clear and well-structured
- Aimed at end users or developers setting up the project
- Committed to the repository

### Development Documentation

Place in `docs/development/` (gitignored):
- Implementation summaries
- Testing reports
- Session notes
- Planning documents
- Bug investigation reports
- Security incident reports
- Sync reports

These files:
- Are for internal development use only
- Are NOT committed to the public repository
- Help track development progress and decisions

### Root Directory

Keep clean! Only essential project files belong in root:
- `README.md` - Main project documentation
- `LICENSE` - Project license
- `CHANGELOG.md` - Version history
- `SECURITY.md` - Security policy
- `requirements.txt` - Python dependencies
- `.gitignore` - Git ignore patterns
- `.env.example` - Environment variable template
- Configuration files (e.g., `docker-compose.yml`)
- Startup scripts (e.g., `run.sh`, `stop.sh`)

### File Naming Conventions

To ensure proper organization:

**User Guides** (goes in `docs/guides/`):
- `*_GUIDE.md` - User-facing guides
- Examples: `ENV_BACKUP_GUIDE.md`, `PASSWORD_RESET_GUIDE.md`

**Development Docs** (goes in `docs/development/`, gitignored):
- `*_IMPLEMENTATION.md` - Implementation details
- `*_REPORT*.md` - Testing and bug reports
- `*_SUMMARY.md` - Session summaries
- `TODO.md`, `STATUS.md`, `PROJECT_PLAN.md` - Planning docs
- `RELEASE_NOTES_*.md`, `GITHUB_RELEASE_*.md` - Release preparation

### Organizing Documentation

If you accidentally create documentation in the root directory, use the provided script:

```bash
./scripts/organize_docs.sh
```

This will automatically move files to their proper locations based on naming patterns.

## Code Contribution Guidelines

### Security First

1. Never commit sensitive data:
   - API keys
   - Passwords
   - Private keys
   - Database credentials
   - Wallet data

2. Use `.env` files for configuration (gitignored)
3. Follow the security guidelines in `SECURITY.md`

### Code Style

1. Follow PEP 8 for Python code
2. Use meaningful variable and function names
3. Add comments for complex logic
4. Write docstrings for functions and classes

### Testing

1. Test your changes locally before submitting
2. Ensure no breaking changes to existing functionality
3. Add tests for new features
4. Document test results in `docs/development/testing/`

### Git Workflow

1. Create a feature branch from `main`
2. Make your changes
3. Test thoroughly
4. Commit with clear, descriptive messages
5. Push to your fork
6. Submit a pull request

### Commit Messages

Follow conventional commit format:

```
type(scope): brief description

Detailed explanation if needed

Co-Authored-By: Name <email>
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code formatting (no logic change)
- `refactor`: Code restructuring (no logic change)
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

Examples:
```
feat(api): Add rate limiting for API endpoints
fix(frontend): Resolve XSS vulnerability in menu display
docs: Update installation instructions for Docker
chore: Organize documentation and clean up repository root
```

## Questions?

If you have questions about contributing, please:
1. Check existing documentation in `docs/`
2. Review open and closed issues on GitHub
3. Open a new issue with your question

Thank you for contributing to ABCT!
