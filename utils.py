import os
import re
from werkzeug.utils import secure_filename
from flask import session

UPLOAD_BASE = os.path.join(os.path.dirname(__file__), 'uploads')
ALLOWED_FILES = {'requirements.txt', 'bot.py'}
MAX_FILE_SIZE = 1 * 1024 * 1024  # 1MB

def get_user_upload_dir(username):
    user_dir = os.path.join(UPLOAD_BASE, secure_filename(username))
    os.makedirs(user_dir, exist_ok=True)
    return user_dir

def validate_file_extension(filename):
    return filename in ALLOWED_FILES

def validate_file_size(file):
    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    return size <= MAX_FILE_SIZE

def sanitize_filename(filename):
    return secure_filename(filename)

def get_current_user():
    return session.get('user_id'), session.get('username'), session.get('role')

def format_timestamp():
    from datetime import datetime
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def escape_log_output(text):
    """Prevent XSS in console logs."""
    import html
    return html.escape(text)

def is_safe_path(basedir, path):
    """Prevent path traversal."""
    real_basedir = os.path.realpath(basedir)
    real_path = os.path.realpath(path)
    return os.path.commonpath([real_basedir, real_path]) == real_basedir

def detect_infinite_loop(code):
    """Very basic suspicious pattern detection."""
    patterns = [
        r'while\s+True\s*:\s*(?!.*(break|return|exit))',
        r'for\s+.*\s+in\s+range\(\d{6,}\)',
    ]
    for pattern in patterns:
        if re.search(pattern, code, re.IGNORECASE):
            return True
    return False