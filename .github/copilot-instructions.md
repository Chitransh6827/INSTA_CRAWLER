# AI Agent Instructions for INSTA_CRAWLER

## Project Overview
This is a high-performance Instagram data scraping system with a Flask backend, tiered user system, and Chrome extension frontend. The project consists of three main components:

1. **Backend Scraping Engine** (`enhanced_scraper.py`, `scraper.py`)
   - Uses undetected-chromedriver for Instagram scraping
   - Implements parallel processing and adaptive rate limiting
   - Handles deduplication and batch data saving

2. **Web Application** (`app.py`)
   - Flask-based server handling user authentication and API endpoints
   - Implements tiered access control via `tier_system.py`
   - Templates in `/templates` for web interface

3. **Chrome Extension** (`/chrome_extension`)
   - Manifest V3 extension for direct Instagram interaction
   - Communicates with localhost Flask backend
   - Provides user interface for scraping actions

## Key Patterns & Conventions

### Rate Limiting
- Use `AdaptiveRateLimiter` class in `enhanced_scraper.py` for intelligent request throttling
- Example usage:
```python
rate_limiter = AdaptiveRateLimiter(base_delay=1.0, max_delay=30.0)
rate_limiter.wait()  # Call before making requests
```

### User Tier Management
- All features must respect tier limits defined in `TierSystem.TIERS`
- Check limits using:
```python
tier_info = TierSystem.get_tier_info(user_tier)
max_accounts = tier_info['max_accounts']
```

### Error Handling
- Use structured logging via the configured logger in `enhanced_scraper.py`
- Handle Selenium exceptions with appropriate retries and backoff
- Always provide user-friendly error messages through the Flask endpoints

## Development Workflow

### Setup
1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Local Development:
- Flask backend runs on localhost:5000
- Chrome extension connects to localhost:5000
- Modify `chrome_extension/manifest.json` host permissions if changing ports

### Testing
- Test different tier limitations using demo accounts:
  - Basic: username='demo', password='password123'
  - Premium: username='admin', password='admin123'

## Integration Points

### Backend ↔ Extension Communication
- Extension makes API calls to Flask endpoints
- All requests require active user session
- Response format: `{"success": bool, "data": any, "error": string?}`

### Scraper ↔ Instagram
- Uses undetected-chromedriver to avoid detection
- Implements parallel processing with ThreadPoolExecutor
- Respects Instagram's rate limits via AdaptiveRateLimiter

## Common Pitfalls
- Don't modify tier limits without updating both frontend and backend validations
- Always use AdaptiveRateLimiter to prevent IP blocking
- Remember to synchronize user_session with Flask session state

## Directory Structure
```
/
├── app.py                 # Flask application entry point
├── enhanced_scraper.py    # Main scraping engine
├── tier_system.py        # User tier management
├── chrome_extension/     # Chrome extension source
└── templates/           # Flask HTML templates
```
