# FikoHouse

A FastAPI web application for managing Netflix household email verification. Users can look up pending Netflix household confirmation emails by entering their email address, and admins can manage which email accounts and subject filters are active.

## Features

- **Email lookup**: Users enter their Netflix email to fetch matching inbox messages via IMAP.
- **Confirmation links**: The app extracts Netflix household/verify links from emails and presents them directly.
- **Multi-language support**: Interface available in English, German, Russian, Turkish, and more.
- **Admin panel**: Secure admin dashboard to add/remove managed email accounts and subject filters.
- **Encrypted credentials**: Email app-passwords are stored encrypted with Fernet symmetric encryption.
- **Docker ready**: Ships with a `Dockerfile` for easy containerised deployment.

## Requirements

- Python 3.11+
- PostgreSQL (recommended for production) or SQLite (for development)
- A Fernet encryption key (see setup below)
- Gmail or Outlook email accounts with IMAP enabled and App Passwords

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/FC2714/Fikohouse.git
cd Fikohouse
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

Copy the example file and fill in the values:

```bash
cp .env.example .env
```

| Variable | Description | Default |
|---|---|---|
| `DATABASE_URL` | SQLAlchemy database URL | `sqlite:///./fikohouse.db` |
| `FERNET_KEY` | Fernet encryption key for app passwords | *(required)* |
| `SECRET_KEY` | Secret key for session management | `dev-secret-key-change-in-production` |
| `ADMIN_PASSWORD` | Admin panel password | `Fiko070House!` |
| `ENVIRONMENT` | `development` or `production` | `development` |
| `DEBUG` | Enable debug logging | `true` |
| `HOST` | Bind address | `0.0.0.0` |
| `PORT` | Bind port | `8000` |

**Generate a Fernet key:**

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 4. Run the application

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

Or use the provided start script:

```bash
chmod +x start.sh && ./start.sh
```

## Docker

```bash
docker build -t fikohouse .
docker run -p 8000:8000 --env-file .env fikohouse
```

## Application Structure

```
Fikohouse/
├── main.py          # FastAPI routes and business logic
├── models.py        # SQLAlchemy database models
├── config.py        # Settings loaded from environment variables
├── translations.py  # UI translations for all supported languages
├── templates/       # Jinja2 HTML templates
├── requirements.txt # Python dependencies
├── Dockerfile       # Container build instructions
└── start.sh         # Startup script
```

## Admin Panel

Navigate to `/admin` to access the admin login. The default username is `admin` and the password is set via the `ADMIN_PASSWORD` environment variable.

From the admin dashboard you can:
- **Add email accounts**: Register Gmail or Outlook accounts (with App Passwords) that will be searched for Netflix emails.
- **Add subject filters**: Define subject-line keywords used to search the inbox (e.g. Netflix household confirmation subjects in different languages).
- **Delete** existing accounts or filters.

## Security Notes

- Change the default `ADMIN_PASSWORD` before deploying to production.
- Generate a strong `FERNET_KEY` and `SECRET_KEY` for production.
- Restrict `allow_origins` in the CORS middleware to your own domain in production.
- Use PostgreSQL instead of SQLite in production for reliability and concurrency.

## Health Check

The `/health` endpoint returns the application status and environment:

```json
{"status": "healthy", "environment": "production"}
```

## License

This project is provided as-is for personal and educational use.
