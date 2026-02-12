import sqlite3
import os
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = os.path.join(os.path.dirname(__file__), 'app.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    
    # Users table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            username TEXT UNIQUE NOT NULL,
            email_or_phone TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'USER',
            plan TEXT DEFAULT 'FREE',
            suspended BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Bots table
    c.execute('''
        CREATE TABLE IF NOT EXISTS bots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            bot_name TEXT NOT NULL,
            status TEXT DEFAULT 'STOPPED',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')
    
    # System config table
    c.execute('''
        CREATE TABLE IF NOT EXISTS system_config (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    # Insert default admin if not exists
    admin = c.execute("SELECT * FROM users WHERE role='ADMIN'").fetchone()
    if not admin:
        admin_hash = generate_password_hash('admin123')
        c.execute('''
            INSERT INTO users (first_name, last_name, username, email_or_phone, password_hash, role)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', ('Admin', 'User', 'admin', 'admin@example.com', admin_hash, 'ADMIN'))
    
    # Insert default system configs
    default_configs = [
        ('max_running_bots_per_user_free', '1'),
        ('max_runtime_hours_free', '24'),
        ('max_restarts_free', '3'),
        ('max_log_lines_free', '500'),
        ('max_cpu_percent_free', '50'),
        ('max_ram_mb_free', '200'),
        ('max_running_bots_per_user_pro', '3'),
        ('max_runtime_hours_pro', '72'),
        ('max_restarts_pro', '10'),
        ('max_log_lines_pro', '5000'),
        ('max_cpu_percent_pro', '80'),
        ('max_ram_mb_pro', '500'),
        ('max_running_bots_per_user_ultra', '10'),
        ('max_runtime_hours_ultra', '8760'),  # 1 year
        ('max_restarts_ultra', '9999'),
        ('max_log_lines_ultra', '50000'),
        ('max_cpu_percent_ultra', '95'),
        ('max_ram_mb_ultra', '1000'),
        ('global_max_running_bots', '50')
    ]
    for key, val in default_configs:
        c.execute('INSERT OR IGNORE INTO system_config (key, value) VALUES (?, ?)', (key, val))
    
    conn.commit()
    conn.close()

init_db()