from fastapi import FastAPI, Request, Form, Depends, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from cryptography.fernet import Fernet
from imapclient import IMAPClient
import email
from email.header import decode_header
from email.utils import parsedate_to_datetime
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import secrets
import logging

from models import SessionLocal, ManagedEmail, Subject
from translations import get_t, validate_lang, language_selector_html, language_selector_html_post
from config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)
logger = logging.getLogger(__name__)

# Initialize Fernet encryption
try:
    fernet = Fernet(settings.FERNET_KEY)
except Exception as e:
    logger.error(f"Failed to initialize Fernet key: {e}")
    raise

app = FastAPI(title="FikoHouse")

# Add CORS middleware for security
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to your domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ===================== HEALTH CHECK =====================
@app.get("/health")
async def health_check():
    """Health check endpoint for deployment monitoring"""
    return {"status": "healthy", "environment": settings.ENVIRONMENT}

# ===================== PUBLIC HOMEPAGE =====================
@app.get("/", response_class=HTMLResponse)
async def home(lang: str = 'en'):
    lang = validate_lang(lang)
    t = get_t(lang)

    return f"""
    <!DOCTYPE html>
    <html lang="{lang}">
    <head>
        <meta charset="UTF-8">
        <title>FikoHouse</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    </head>
    <body class="bg-gray-950 text-white">
        {language_selector_html(lang)}
        <div class="max-w-6xl mx-auto p-8">
            <div class="text-center mb-12">
                <h1 class="text-5xl font-bold text-emerald-500">{t('home_title')}</h1>
                <p class="text-gray-400 text-xl">{t('home_subtitle')}</p>
            </div>
            <div class="grid grid-cols-1 lg:grid-cols-12 gap-8">
                <div class="lg:col-span-7 bg-gray-900 rounded-3xl p-8">
                    <h2 class="text-2xl mb-6">{t('home_form_label')}</h2>
                    <form method="post" action="/load-mails?lang={lang}" class="space-y-6">
                        <input type="email" name="email_input" placeholder="{t('home_placeholder')}"
                               class="w-full bg-gray-800 border border-gray-700 rounded-2xl px-6 py-5 text-lg" required>
                        <input type="hidden" name="lang" value="{lang}">
                        <button type="submit" class="w-full bg-emerald-600 hover:bg-emerald-700 py-5 rounded-2xl text-xl font-semibold flex items-center justify-center gap-3">
                            <i class="fas fa-envelope"></i> {t('home_button')}
                        </button>
                    </form>
                </div>
                <div class="lg:col-span-5 bg-gray-900 rounded-3xl p-8">
                    <div class="text-emerald-400 font-medium mb-4">{t('preview_label')}</div>
                    <p class="text-gray-400">{t('preview_text')}</p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """

# ===================== FIXED MAIL FETCHING =====================
@app.post("/load-mails", response_class=HTMLResponse)
async def load_mails(email_input: str = Form(...), lang: str = Form('en'), db: Session = Depends(get_db)):
    lang = validate_lang(lang)
    t = get_t(lang)

    managed = db.query(ManagedEmail).filter(ManagedEmail.email_address == email_input.strip()).first()
    if not managed:
        return f"""
        <!DOCTYPE html>
        <html lang="{lang}">
        <head>
            <meta charset="UTF-8">
            <title>FikoHouse</title>
            <script src="https://cdn.tailwindcss.com"></script>
        </head>
        <body class="bg-gray-950 text-white min-h-screen flex items-center justify-center">
            {language_selector_html_post(lang, email_input)}
            <div class="max-w-2xl mx-auto text-center px-4">
                <div class="text-6xl mb-4">❌</div>
                <h1 class="text-4xl font-bold text-red-500 mb-4">{t('load_mails_error_not_registered')}</h1>
                <a href="/?lang={lang}" class="inline-block bg-emerald-600 hover:bg-emerald-700 text-white font-semibold py-3 px-8 rounded-2xl mt-8">
                    ← {t('load_mails_back')}
                </a>
            </div>
        </body>
        </html>
        """

    try:
        app_pass = fernet.decrypt(managed.app_password_encrypted.encode()).decode()
        mail = IMAPClient(managed.imap_server, ssl=True)
        mail.login(managed.email_address, app_pass)
        mail.select_folder(b'INBOX')

        # Ensure capabilities are available for proper charset handling
        if mail._cached_capabilities is None:
            mail._cached_capabilities = mail.capabilities()

        # Build dynamic search query from database subjects
        subjects = db.query(Subject).all()
        if not subjects:
            return f"""
            <!DOCTYPE html>
            <html lang="{lang}">
            <head>
                <meta charset="UTF-8">
                <title>FikoHouse</title>
                <script src="https://cdn.tailwindcss.com"></script>
            </head>
            <body class="bg-gray-950 text-white min-h-screen flex items-center justify-center">
                {language_selector_html_post(lang, email_input)}
                <div class="max-w-2xl mx-auto text-center px-4">
                    <div class="text-6xl mb-4">⚠️</div>
                    <h1 class="text-4xl font-bold text-orange-500 mb-4">{t('load_mails_error_no_subjects')}</h1>
                    <a href="/?lang={lang}" class="inline-block bg-emerald-600 hover:bg-emerald-700 text-white font-semibold py-3 px-8 rounded-2xl mt-8">
                        ← {t('load_mails_back')}
                    </a>
                </div>
            </body>
            </html>
            """

        # Search for each subject and combine results
        mail_ids_set = set()
        for subject in subjects:
            try:
                logger.info(f"Searching for subject: {subject.subject_text}")
                # Explicitly pass charset='UTF-8' to handle German characters
                mail_ids = mail.search(['SUBJECT', subject.subject_text], charset='UTF-8')
                found_count = len(mail_ids) if mail_ids else 0
                logger.info(f"Found {found_count} emails for subject: {subject.subject_text}")
                if mail_ids:
                    mail_ids_set.update(mail_ids)
            except Exception as e:
                logger.error(f"Error searching for subject: {e}", exc_info=True)

        # Batch fetch all matching emails (much faster than one-by-one)
        mails_with_dates = []
        if mail_ids_set:
            try:
                # Fetch all emails in a single batch request
                all_msg_data = mail.fetch(list(mail_ids_set), ['RFC822', 'INTERNALDATE'])
                for mid, data in all_msg_data.items():
                    try:
                        msg = email.message_from_bytes(data[b'RFC822'])
                        # Use INTERNALDATE (server-side date) for reliable sorting
                        date = data.get(b'INTERNALDATE', datetime.min)
                        if not isinstance(date, datetime):
                            date_str = msg.get("Date", "")
                            try:
                                date = parsedate_to_datetime(date_str)
                            except:
                                date = datetime.min
                        mails_with_dates.append((mid, date, msg))
                    except Exception as e:
                        logger.error(f"Error parsing email {mid}: {e}")
            except Exception as e:
                logger.error(f"Error batch fetching emails: {e}")

        # Sort by date, most recent first (newest at top)
        mails_with_dates.sort(key=lambda x: x[1], reverse=True)

        mails_html = ""
        displayed_count = 0
        for mid, date, msg in mails_with_dates:
            subject = decode_header(msg["Subject"])[0][0]
            if isinstance(subject, bytes):
                subject = subject.decode()

            # Skip confirmation messages
            lower_subject = subject.lower()
            if any(word in lower_subject for word in ["bestätigung", "wurde bestätigt", "confirmed", "success", "erfolgreich"]):
                continue

            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/html":
                        body = part.get_payload(decode=True).decode(errors="ignore")
                        break
            else:
                body = msg.get_payload(decode=True).decode(errors="ignore")

            soup = BeautifulSoup(body, "lxml")
            confirm_link = None
            for a in soup.find_all("a", href=True):
                href_lower = a["href"].lower()
                if "netflix.com" in href_lower:
                    # Look for various Netflix verification/confirmation patterns
                    if any(keyword in href_lower for keyword in ["household", "confirm", "verify", "activate", "code", "validate"]):
                        confirm_link = a["href"]
                        break

            # If no specific keywords found, accept any netflix.com link as fallback
            if not confirm_link:
                for a in soup.find_all("a", href=True):
                    if "netflix.com" in a["href"].lower():
                        confirm_link = a["href"]
                        break

            link_html = f'<a href="{confirm_link}" target="_blank" class="inline-block bg-green-600 hover:bg-green-700 text-white px-6 py-3 rounded-2xl text-sm font-semibold">{t("load_mails_confirm")}</a>' if confirm_link else f'<span class="text-amber-400 text-sm">{t("load_mails_no_link")}</span>'

            # Format date for display - use original email Date header (has correct timezone)
            date_str = msg.get("Date", "")
            try:
                email_date = parsedate_to_datetime(date_str)
                date_display = email_date.strftime("%Y-%m-%d %H:%M")
            except:
                date_display = date_str[:16] if date_str else "Unknown"

            mails_html += f"""
            <div class="bg-gradient-to-r from-gray-800 to-gray-700 rounded-2xl p-6 mb-4 shadow-lg hover:shadow-2xl transition-all duration-300 border border-gray-700 hover:border-emerald-500">
                <div class="flex justify-between items-center gap-6">
                    <div class="flex-1">
                        <div class="flex items-center gap-3 mb-2">
                            <span class="inline-block bg-emerald-500/20 text-emerald-400 px-3 py-1 rounded-lg text-xs font-semibold">📧 Netflix</span>
                        </div>
                        <p class="font-semibold text-lg text-white mb-1">{subject}</p>
                        <p class="text-sm text-gray-400">📅 {date_display}</p>
                    </div>
                    <div class="flex-shrink-0">
                        {link_html}
                    </div>
                </div>
            </div>"""

            displayed_count += 1
            if displayed_count >= 10:
                break

        mail.logout()

        empty_message = f'<div class="bg-amber-500/10 border border-amber-500/30 rounded-2xl p-8 text-center"><p class="text-amber-400 text-lg font-medium">{t("load_mails_empty")}</p><p class="text-gray-400 text-sm mt-2">{t("load_mails_empty_note")}</p></div>'

        return f"""
        <!DOCTYPE html>
        <html lang="{lang}">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Netflix Mailler</title>
            <script src="https://cdn.tailwindcss.com"></script>
            <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
        </head>
        <body class="bg-gradient-to-br from-gray-950 via-gray-900 to-gray-950 text-white min-h-screen">
            {language_selector_html_post(lang, email_input)}
            <div class="max-w-4xl mx-auto px-4 py-12">
                <!-- Header -->
                <div class="text-center mb-12">
                    <div class="inline-block bg-emerald-500/10 border border-emerald-500/30 rounded-3xl px-6 py-3 mb-6">
                        <p class="text-emerald-400 font-semibold">{t('load_mails_title')}</p>
                    </div>
                    <h1 class="text-5xl font-bold bg-gradient-to-r from-emerald-400 to-emerald-600 bg-clip-text text-transparent mb-4">{t('load_mails_subtitle')}</h1>
                    <p class="text-gray-400 text-lg">{t('load_mails_description')}</p>
                </div>

                <!-- Mails Container -->
                <div class="space-y-4 mb-12">
                    {mails_html or empty_message}
                </div>

                <!-- Footer -->
                <div class="text-center pt-8 border-t border-gray-800">
                    <a href="/?lang={lang}" class="inline-block bg-emerald-600 hover:bg-emerald-700 text-white font-semibold py-3 px-8 rounded-2xl transition-all duration-200 transform hover:scale-105">
                        <i class="fas fa-arrow-left mr-2"></i> {t('load_mails_back')}
                    </a>
                </div>
            </div>
        </body>
        </html>
        """

    except Exception as e:
        return f"""
        <!DOCTYPE html>
        <html lang="{lang}">
        <head>
            <meta charset="UTF-8">
            <title>FikoHouse</title>
            <script src="https://cdn.tailwindcss.com"></script>
        </head>
        <body class="bg-gray-950 text-white min-h-screen flex items-center justify-center">
            {language_selector_html_post(lang, email_input)}
            <div class="max-w-2xl mx-auto text-center px-4">
                <div class="text-6xl mb-4">❌</div>
                <h1 class="text-4xl font-bold text-red-500 mb-4">{t('load_mails_error_connection')}</h1>
                <p class="text-gray-400 text-lg mb-8 break-all">{str(e)}</p>
                <a href="/?lang={lang}" class="inline-block bg-emerald-600 hover:bg-emerald-700 text-white font-semibold py-3 px-8 rounded-2xl">
                    ← {t('load_mails_back')}
                </a>
            </div>
        </body>
        </html>
        """

# ===================== FULL ADMIN DASHBOARD =====================
@app.get("/admin", response_class=HTMLResponse)
async def admin_page(lang: str = 'en'):
    lang = validate_lang(lang)
    t = get_t(lang)

    return f"""
    <!DOCTYPE html>
    <html lang="{lang}">
    <head>
        <meta charset="UTF-8">
        <title>FikoHouse Admin</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-gray-950 text-white min-h-screen flex items-center justify-center">
        {language_selector_html(lang)}
        <div class="bg-gray-900 rounded-3xl p-10 w-full max-w-md">
            <h1 class="text-4xl font-bold text-emerald-500 text-center mb-8">FikoHouse Admin</h1>
            <form method="post" action="/admin/login?lang={lang}" class="space-y-6">
                <input type="text" name="username" placeholder="Username" class="w-full bg-gray-800 border border-gray-700 rounded-2xl px-5 py-4" required>
                <input type="password" name="password" placeholder="Password" class="w-full bg-gray-800 border border-gray-700 rounded-2xl px-5 py-4" required>
                <input type="hidden" name="lang" value="{lang}">
                <button type="submit" class="w-full bg-emerald-600 hover:bg-emerald-700 py-4 rounded-2xl text-lg font-semibold">{t('admin_login')}</button>
            </form>
        </div>
    </body>
    </html>
    """

@app.post("/admin/login", response_class=HTMLResponse)
async def admin_login(username: str = Form(...), password: str = Form(...), lang: str = Form('en')):
    lang = validate_lang(lang)
    t = get_t(lang)

    if username == "admin" and password == settings.ADMIN_PASSWORD:
        response = RedirectResponse(url=f"/admin/dashboard?lang={lang}", status_code=302)
        response.set_cookie(key="admin_session", value=secrets.token_hex(16), max_age=86400, httponly=True, samesite="strict")
        return response

    return f"""
    <!DOCTYPE html>
    <html lang="{lang}">
    <head>
        <meta charset="UTF-8">
        <title>FikoHouse Admin</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-gray-950 text-white min-h-screen flex items-center justify-center">
        {language_selector_html(lang)}
        <div class="max-w-2xl mx-auto text-center px-4">
            <div class="text-6xl mb-4">❌</div>
            <h1 class="text-4xl font-bold text-red-500 mb-8">{t('admin_wrong_password')}</h1>
            <a href="/admin?lang={lang}" class="inline-block bg-emerald-600 hover:bg-emerald-700 text-white font-semibold py-3 px-8 rounded-2xl">
                ← {t('load_mails_back')}
            </a>
        </div>
    </body>
    </html>
    """

@app.get("/admin/dashboard", response_class=HTMLResponse)
async def admin_dashboard(request: Request, lang: str = 'en', db: Session = Depends(get_db)):
    lang = validate_lang(lang)
    t = get_t(lang)

    # Check if admin is logged in
    if "admin_session" not in request.cookies:
        return f"""
        <!DOCTYPE html>
        <html lang="{lang}">
        <head>
            <meta charset="UTF-8">
            <title>FikoHouse Admin</title>
            <script src="https://cdn.tailwindcss.com"></script>
        </head>
        <body class="bg-gray-950 text-white min-h-screen flex items-center justify-center">
            {language_selector_html(lang)}
            <div class="max-w-2xl mx-auto text-center px-4">
                <div class="text-6xl mb-4">🔒</div>
                <h1 class="text-4xl font-bold text-amber-500 mb-4">Access Denied</h1>
                <p class="text-gray-400 text-lg mb-8">You must be logged in to access the admin panel.</p>
                <a href="/admin?lang={lang}" class="inline-block bg-emerald-600 hover:bg-emerald-700 text-white font-semibold py-3 px-8 rounded-2xl">
                    ← {t('load_mails_back')}
                </a>
            </div>
        </body>
        </html>
        """

    emails = db.query(ManagedEmail).all()
    subjects = db.query(Subject).all()

    email_list = "".join([f"""
    <div class="flex justify-between items-center bg-gray-800 p-4 rounded-2xl mb-3">
        <div>
            <span class="font-medium">{e.email_address}</span><br>
            <span class="text-xs text-gray-500">{e.imap_server}</span>
        </div>
        <form method="post" action="/admin/delete-email/{e.id}?lang={lang}" style="display:inline;">
            <input type="hidden" name="lang" value="{lang}">
            <button type="submit" class="text-red-500 hover:text-red-600 text-sm">{t('admin_delete')}</button>
        </form>
    </div>""" for e in emails])

    subject_list = "".join([f"""
    <div class="flex justify-between items-center bg-gray-800 p-4 rounded-2xl mb-3">
        <div><span class="text-emerald-400">{s.language}</span>: "{s.subject_text}"</div>
        <form method="post" action="/admin/delete-subject/{s.id}?lang={lang}" style="display:inline;">
            <input type="hidden" name="lang" value="{lang}">
            <button type="submit" class="text-red-500 hover:text-red-600 text-sm">{t('admin_delete')}</button>
        </form>
    </div>""" for s in subjects])

    return f"""
    <!DOCTYPE html>
    <html lang="{lang}">
    <head><meta charset="UTF-8"><title>FikoHouse Admin</title><script src="https://cdn.tailwindcss.com"></script></head>
    <body class="bg-gray-950 text-white p-8">
        {language_selector_html(lang)}
        <div class="max-w-6xl mx-auto">
            <div class="flex justify-between items-center mb-8">
                <h1 class="text-4xl font-bold text-emerald-500">{t('admin_dashboard_title')}</h1>
                <a href="/admin/logout?lang={lang}" class="bg-red-600 hover:bg-red-700 text-white font-semibold py-2 px-6 rounded-lg transition-colors">
                    🚪 {t('admin_logout')}
                </a>
            </div>

            <div class="grid grid-cols-2 gap-8">
                <div class="bg-gray-900 rounded-3xl p-8">
                    <h2 class="text-xl mb-4">{t('admin_add_email')}</h2>
                    <form method="post" action="/admin/add-email?lang={lang}" class="space-y-4">
                        <input type="email" name="email_address" placeholder="{t('admin_add_email_placeholder')}" class="w-full bg-gray-800 border border-gray-700 rounded-2xl px-5 py-4" required>
                        <select name="imap_server" class="w-full bg-gray-800 border border-gray-700 rounded-2xl px-5 py-4">
                            <option value="imap.gmail.com">{t('admin_gmail')}</option>
                            <option value="outlook.office365.com">{t('admin_outlook')}</option>
                        </select>
                        <input type="password" name="app_password" placeholder="{t('admin_app_password')}" class="w-full bg-gray-800 border border-gray-700 rounded-2xl px-5 py-4" required>
                        <input type="hidden" name="lang" value="{lang}">
                        <button type="submit" class="w-full bg-emerald-600 hover:bg-emerald-700 py-4 rounded-2xl text-lg">{t('admin_add_email_button')}</button>
                    </form>
                </div>
                <div class="bg-gray-900 rounded-3xl p-8">
                    <h2 class="text-xl mb-4">{t('admin_add_subject')}</h2>
                    <form method="post" action="/admin/add-subject?lang={lang}" class="space-y-4">
                        <input type="text" name="language" placeholder="{t('admin_language')}" class="w-full bg-gray-800 border border-gray-700 rounded-2xl px-5 py-4" required>
                        <input type="text" name="subject_text" placeholder="{t('admin_subject_text')}" class="w-full bg-gray-800 border border-gray-700 rounded-2xl px-5 py-4" required>
                        <input type="hidden" name="lang" value="{lang}">
                        <button type="submit" class="w-full bg-emerald-600 hover:bg-emerald-700 py-4 rounded-2xl text-lg">{t('admin_add_subject_button')}</button>
                    </form>
                </div>
            </div>

            <div class="mt-12">
                <h2 class="text-2xl mb-4">{t('admin_current_emails')}</h2>
                {email_list or f'<p class="text-gray-400">{t("admin_no_emails")}</p>'}
            </div>

            <div class="mt-12">
                <h2 class="text-2xl mb-4">{t('admin_current_subjects')}</h2>
                {subject_list or f'<p class="text-gray-400">{t("admin_no_subjects")}</p>'}
            </div>
        </div>
    </body>
    </html>
    """

# Add & Delete routes
@app.post("/admin/add-email", response_class=HTMLResponse)
async def add_email(request: Request, email_address: str = Form(...), imap_server: str = Form(...), app_password: str = Form(...), lang: str = Form('en'), db: Session = Depends(get_db)):
    lang = validate_lang(lang)
    t = get_t(lang)

    # Check authentication
    if "admin_session" not in request.cookies:
        return RedirectResponse(url=f"/admin?lang={lang}", status_code=302)

    try:
        encrypted = fernet.encrypt(app_password.encode()).decode()
        new_email = ManagedEmail(email_address=email_address, imap_server=imap_server, app_password_encrypted=encrypted)
        db.add(new_email)
        db.commit()
        return f"""
        <!DOCTYPE html>
        <html lang="{lang}">
        <head><meta charset="UTF-8"><title>FikoHouse Admin</title><script src="https://cdn.tailwindcss.com"></script></head>
        <body class="bg-gray-950 text-white min-h-screen flex items-center justify-center">
            {language_selector_html(lang)}
            <div class="max-w-2xl mx-auto text-center px-4">
                <div class="text-6xl mb-4">✅</div>
                <h1 class="text-4xl font-bold text-emerald-500 mb-8">{t('success_email_added')}</h1>
                <a href="/admin/dashboard?lang={lang}" class="inline-block bg-emerald-600 hover:bg-emerald-700 text-white font-semibold py-3 px-8 rounded-2xl">
                    ← {t('admin_back')}
                </a>
            </div>
        </body>
        </html>
        """
    except:
        return f"""
        <!DOCTYPE html>
        <html lang="{lang}">
        <head><meta charset="UTF-8"><title>FikoHouse Admin</title><script src="https://cdn.tailwindcss.com"></script></head>
        <body class="bg-gray-950 text-white min-h-screen flex items-center justify-center">
            {language_selector_html(lang)}
            <div class="max-w-2xl mx-auto text-center px-4">
                <div class="text-6xl mb-4">❌</div>
                <h1 class="text-4xl font-bold text-red-500 mb-8">{t('success_email_already_exists')}</h1>
                <a href="/admin/dashboard?lang={lang}" class="inline-block bg-emerald-600 hover:bg-emerald-700 text-white font-semibold py-3 px-8 rounded-2xl">
                    ← {t('admin_back')}
                </a>
            </div>
        </body>
        </html>
        """

@app.post("/admin/add-subject", response_class=HTMLResponse)
async def add_subject(request: Request, language: str = Form(...), subject_text: str = Form(...), lang: str = Form('en'), db: Session = Depends(get_db)):
    lang = validate_lang(lang)
    t = get_t(lang)

    # Check authentication
    if "admin_session" not in request.cookies:
        return RedirectResponse(url=f"/admin?lang={lang}", status_code=302)

    new_subject = Subject(language=language, subject_text=subject_text)
    db.add(new_subject)
    db.commit()
    return f"""
    <!DOCTYPE html>
    <html lang="{lang}">
    <head><meta charset="UTF-8"><title>FikoHouse Admin</title><script src="https://cdn.tailwindcss.com"></script></head>
    <body class="bg-gray-950 text-white min-h-screen flex items-center justify-center">
        {language_selector_html(lang)}
        <div class="max-w-2xl mx-auto text-center px-4">
            <div class="text-6xl mb-4">✅</div>
            <h1 class="text-4xl font-bold text-emerald-500 mb-8">{t('success_subject_added')}</h1>
            <a href="/admin/dashboard?lang={lang}" class="inline-block bg-emerald-600 hover:bg-emerald-700 text-white font-semibold py-3 px-8 rounded-2xl">
                ← {t('admin_back')}
            </a>
        </div>
    </body>
    </html>
    """

@app.post("/admin/delete-email/{email_id}", response_class=HTMLResponse)
async def delete_email(request: Request, email_id: int, lang: str = Form('en'), db: Session = Depends(get_db)):
    lang = validate_lang(lang)
    t = get_t(lang)

    # Check authentication
    if "admin_session" not in request.cookies:
        return RedirectResponse(url=f"/admin?lang={lang}", status_code=302)

    email = db.query(ManagedEmail).filter(ManagedEmail.id == email_id).first()
    if email:
        db.delete(email)
        db.commit()

    return f"""
    <!DOCTYPE html>
    <html lang="{lang}">
    <head><meta charset="UTF-8"><title>FikoHouse Admin</title><script src="https://cdn.tailwindcss.com"></script></head>
    <body class="bg-gray-950 text-white min-h-screen flex items-center justify-center">
        {language_selector_html(lang)}
        <div class="max-w-2xl mx-auto text-center px-4">
            <div class="text-6xl mb-4">✅</div>
            <h1 class="text-4xl font-bold text-emerald-500 mb-8">{t('success_email_deleted')}</h1>
            <a href="/admin/dashboard?lang={lang}" class="inline-block bg-emerald-600 hover:bg-emerald-700 text-white font-semibold py-3 px-8 rounded-2xl">
                ← {t('admin_back')}
            </a>
        </div>
    </body>
    </html>
    """

@app.post("/admin/delete-subject/{subject_id}", response_class=HTMLResponse)
async def delete_subject(request: Request, subject_id: int, lang: str = Form('en'), db: Session = Depends(get_db)):
    lang = validate_lang(lang)
    t = get_t(lang)

    # Check authentication
    if "admin_session" not in request.cookies:
        return RedirectResponse(url=f"/admin?lang={lang}", status_code=302)

    subject = db.query(Subject).filter(Subject.id == subject_id).first()
    if subject:
        db.delete(subject)
        db.commit()

    return f"""
    <!DOCTYPE html>
    <html lang="{lang}">
    <head><meta charset="UTF-8"><title>FikoHouse Admin</title><script src="https://cdn.tailwindcss.com"></script></head>
    <body class="bg-gray-950 text-white min-h-screen flex items-center justify-center">
        {language_selector_html(lang)}
        <div class="max-w-2xl mx-auto text-center px-4">
            <div class="text-6xl mb-4">✅</div>
            <h1 class="text-4xl font-bold text-emerald-500 mb-8">{t('success_subject_deleted')}</h1>
            <a href="/admin/dashboard?lang={lang}" class="inline-block bg-emerald-600 hover:bg-emerald-700 text-white font-semibold py-3 px-8 rounded-2xl">
                ← {t('admin_back')}
            </a>
        </div>
    </body>
    </html>
    """

@app.get("/admin/logout")
async def logout(lang: str = 'en'):
    lang = validate_lang(lang)
    response = RedirectResponse(url=f"/admin?lang={lang}", status_code=302)
    response.delete_cookie(key="admin_session", httponly=True, samesite="strict")
    return response

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)