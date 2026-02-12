import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from flask import session, redirect, url_for, flash, request
from functools import wraps
from models import get_db

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return {'error': 'Unauthorized'}, 401
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'ADMIN':
            return {'error': 'Forbidden'}, 403
        return f(*args, **kwargs)
    return decorated_function

def signup_user(first_name, last_name, username, email_or_phone, password):
    conn = get_db()
    c = conn.cursor()
    
    # Check if username exists
    existing = c.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
    if existing:
        conn.close()
        return False, 'Username already taken'
    
    password_hash = generate_password_hash(password)
    try:
        c.execute('''
            INSERT INTO users (first_name, last_name, username, email_or_phone, password_hash)
            VALUES (?, ?, ?, ?, ?)
        ''', (first_name, last_name, username, email_or_phone, password_hash))
        conn.commit()
    except Exception as e:
        conn.close()
        return False, str(e)
    conn.close()
    return True, 'User created'

def login_user(username, password):
    conn = get_db()
    c = conn.cursor()
    user = c.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    conn.close()
    
    if not user:
        return False, 'Invalid credentials'
    
    if not check_password_hash(user['password_hash'], password):
        return False, 'Invalid credentials'
    
    if user['suspended']:
        return False, 'Your account has been suspended'
    
    session['user_id'] = user['id']
    session['username'] = user['username']
    session['role'] = user['role']
    session.permanent = True
    return True, 'Logged in'

def logout_user():
    session.clear()