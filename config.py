import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()
BASE_DIR=Path(__file__).resolve().parent

def env_bool(name, default=False):
    return os.getenv(name, str(default)).lower() in {'1','true','yes','on'}

class BaseConfig:
    SECRET_KEY=os.getenv('SECRET_KEY','dev-only-change-me')
    _db_url = os.getenv('DATABASE_URL','').strip()
    if _db_url.startswith('postgres://'):
        _db_url = 'postgresql+psycopg2://' + _db_url[len('postgres://'):]
    elif _db_url.startswith('postgresql://'):
        _db_url = 'postgresql+psycopg2://' + _db_url[len('postgresql://'):]
    SQLALCHEMY_DATABASE_URI = _db_url or 'sqlite:///' + str(BASE_DIR/'instance'/'cwhub.db')
    SQLALCHEMY_TRACK_MODIFICATIONS=False
    MAX_CONTENT_LENGTH=int(os.getenv('MAX_CONTENT_LENGTH','33554432'))
    UPLOAD_FOLDER=os.getenv('UPLOAD_FOLDER',str(BASE_DIR/'instance'/'uploads'))
    DEBUG=env_bool('FLASK_DEBUG',False)
    SESSION_COOKIE_HTTPONLY=True
    SESSION_COOKIE_SECURE=env_bool('SESSION_COOKIE_SECURE', False)
    REMEMBER_COOKIE_SECURE=env_bool('REMEMBER_COOKIE_SECURE', False)
    SESSION_COOKIE_SAMESITE='Lax'
    REMEMBER_COOKIE_HTTPONLY=True
    REMEMBER_COOKIE_SAMESITE='Lax'
    WTF_CSRF_TIME_LIMIT=None
    RATELIMIT_DEFAULT='120 per minute'
    ADMIN_EMAIL=os.getenv('ADMIN_EMAIL','admin@cwhub.local')
    ADMIN_USERNAME=os.getenv('ADMIN_USERNAME','admin')
    ADMIN_PASSWORD=os.getenv('ADMIN_PASSWORD','ChangeMe123!')
    STORAGE_BACKEND=os.getenv('STORAGE_BACKEND','local')
    S3_ENDPOINT_URL=os.getenv('S3_ENDPOINT_URL')
    S3_BUCKET=os.getenv('S3_BUCKET')
    S3_ACCESS_KEY=os.getenv('S3_ACCESS_KEY')
    S3_SECRET_KEY=os.getenv('S3_SECRET_KEY')
    S3_REGION=os.getenv('S3_REGION')
    SUPPORT_TELEGRAM=os.getenv('SUPPORT_TELEGRAM','https://t.me/shokirjonshokirov').strip()
    ADMIN_BOOTSTRAP=env_bool('ADMIN_BOOTSTRAP', True)
    SITE_URL=os.getenv('SITE_URL','')
    MAIL_SERVER=os.getenv('MAIL_SERVER','')
    MAIL_PORT=int(os.getenv('MAIL_PORT','587'))
    MAIL_USERNAME=os.getenv('MAIL_USERNAME','')
    MAIL_PASSWORD=os.getenv('MAIL_PASSWORD','')
    MAIL_USE_TLS=env_bool('MAIL_USE_TLS', True)
    MAIL_DEFAULT_SENDER=os.getenv('MAIL_DEFAULT_SENDER', ADMIN_EMAIL)
