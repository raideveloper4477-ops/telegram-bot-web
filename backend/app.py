import os
from flask import Flask, render_template, request, jsonify, session, send_file, abort
from werkzeug.utils import secure_filename
from functools import wraps
import threading
import time
import sqlite3

from auth import login_required, admin_required, signup_user, login_user, logout_user
from models import get_db
from utils import (
    get_user_upload_dir, validate_file_extension, validate_file_size,
    get_current_user, format_timestamp
)
from bot_manager import (
    get_bot_manager, create_bot_manager, delete_bot_manager, user_bots
)
from plan_manager import get_user_limits, upgrade_user_plan, PLANS
from admin import admin_bp
import security

app = Flask(__name__, 
            static_folder='../frontend',
            template_folder='../frontend')
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.permanent_session_lifetime = 86400  # 1 day

app.register_blueprint(admin_bp)

# ------------------ Helper Functions ------------------
def login_required_api(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated

# ------------------ Auth Routes ------------------
@app.route('/')
def index():
    if 'user_id' in session:
        return render_template('dashboard.html')
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'GET':
        return render_template('signup.html')
    data = request.json
    success, msg = signup_user(
        data.get('first_name'),
        data.get('last_name'),
        data.get('username'),
        data.get('email_or_phone'),
        data.get('password')
    )
    return jsonify({'success': success, 'message': msg})

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')
    data = request.json
    success, msg = login_user(data.get('username'), data.get('password'))
    return jsonify({'success': success, 'message': msg})

@app.route('/logout')
def logout():
    logout_user()
    return jsonify({'success': True})

# ------------------ Bot Management Routes ------------------
@app.route('/bot/create', methods=['POST'])
@login_required_api
def create_bot():
    data = request.json
    bot_name = data.get('bot_name', 'My Bot')
    user_id = session['user_id']
    username = session['username']
    
    # Check bot count limit
    limits = get_user_limits(user_id)
    conn = get_db()
    c = conn.cursor()
    count = c.execute('SELECT COUNT(*) as cnt FROM bots WHERE user_id = ?', (user_id,)).fetchone()['cnt']
    if count >= limits['max_bots']:
        conn.close()
        return jsonify({'success': False, 'error': f'Max bots ({limits["max_bots"]}) reached for your plan'}), 400
    
    c.execute('INSERT INTO bots (user_id, bot_name) VALUES (?, ?)', (user_id, bot_name))
    bot_id = c.lastrowid
    conn.commit()
    conn.close()
    
    # Create bot manager
    create_bot_manager(user_id, bot_id, username, bot_name)
    
    return jsonify({'success': True, 'bot_id': bot_id})

@app.route('/my/bots', methods=['GET'])
@login_required_api
def list_bots():
    user_id = session['user_id']
    conn = get_db()
    c = conn.cursor()
    bots = c.execute('SELECT id, bot_name, status FROM bots WHERE user_id = ? ORDER BY created_at DESC', (user_id,)).fetchall()
    conn.close()
    return jsonify([dict(b) for b in bots])

@app.route('/upload', methods=['POST'])
@login_required_api
def upload_files():
    user_id = session['user_id']
    username = session['username']
    bot_id = request.form.get('bot_id')
    if not bot_id:
        return jsonify({'error': 'bot_id required'}), 400
    
    # Verify bot belongs to user
    conn = get_db()
    c = conn.cursor()
    bot = c.execute('SELECT id FROM bots WHERE id = ? AND user_id = ?', (bot_id, user_id)).fetchone()
    conn.close()
    if not bot:
        return jsonify({'error': 'Invalid bot'}), 403
    
    files = request.files
    upload_dir = get_user_upload_dir(username)
    
    for key in files:
        file = files[key]
        if file.filename == '':
            continue
        if not validate_file_extension(file.filename):
            return jsonify({'error': f'Invalid file type: {file.filename}. Only requirements.txt and bot.py allowed'}), 400
        if not validate_file_size(file):
            return jsonify({'error': f'File too large: {file.filename}. Max 1MB'}), 400
        
        filename = secure_filename(file.filename)
        file.save(os.path.join(upload_dir, filename))
    
    return jsonify({'success': True})

@app.route('/bot/start', methods=['POST'])
@login_required_api
@security.rate_limit(lambda: session.get('user_id', 'anon'))
def start_bot_route():
    data = request.json
    bot_id = data.get('bot_id')
    user_id = session['user_id']
    
    # Check suspension
    conn = get_db()
    c = conn.cursor()
    user = c.execute('SELECT suspended FROM users WHERE id = ?', (user_id,)).fetchone()
    if user and user['suspended']:
        conn.close()
        return jsonify({'error': 'Your account is suspended'}), 403
    
    bot = c.execute('SELECT id FROM bots WHERE id = ? AND user_id = ?', (bot_id, user_id)).fetchone()
    conn.close()
    if not bot:
        return jsonify({'error': 'Bot not found'}), 404
    
    manager = get_bot_manager(user_id, bot_id)
    if not manager:
        # Should exist, but if not, create
        manager = create_bot_manager(user_id, bot_id, session['username'], '')
    
    success, msg = manager.start()
    return jsonify({'success': success, 'message': msg})

@app.route('/bot/stop', methods=['POST'])
@login_required_api
@security.rate_limit(lambda: session.get('user_id', 'anon'))
def stop_bot():
    data = request.json
    bot_id = data.get('bot_id')
    user_id = session['user_id']
    manager = get_bot_manager(user_id, bot_id)
    if manager:
        manager.stop()
        return jsonify({'success': True})
    return jsonify({'error': 'Bot not found'}), 404

@app.route('/bot/restart', methods=['POST'])
@login_required_api
def restart_bot():
    data = request.json
    bot_id = data.get('bot_id')
    user_id = session['user_id']
    manager = get_bot_manager(user_id, bot_id)
    if manager:
        if manager.status == 'RUNNING':
            manager.stop()
            # Wait a bit
            import time
            time.sleep(2)
        success, msg = manager.start()
        return jsonify({'success': success, 'message': msg})
    return jsonify({'error': 'Bot not found'}), 404

@app.route('/bot/logs', methods=['GET'])
@login_required_api
def get_logs():
    bot_id = request.args.get('bot_id')
    user_id = session['user_id']
    manager = get_bot_manager(user_id, bot_id)
    if manager:
        limits = get_user_limits(user_id)
        max_lines = limits['max_log_lines']
        logs = manager.get_logs(max_lines)
        return jsonify({'logs': logs})
    return jsonify({'logs': []})

@app.route('/bot/status', methods=['GET'])
@login_required_api
def bot_status():
    bot_id = request.args.get('bot_id')
    user_id = session['user_id']
    manager = get_bot_manager(user_id, bot_id)
    if manager:
        # Also get from DB in case manager not started but DB says running?
        conn = get_db()
        c = conn.cursor()
        db_status = c.execute('SELECT status FROM bots WHERE id = ?', (bot_id,)).fetchone()
        conn.close()
        status = manager.status
        if db_status:
            status = db_status['status']  # Use DB as source of truth
        else:
            status = 'STOPPED'
        return jsonify({
            'status': status,
            'start_time': manager.start_time.isoformat() if manager.start_time else None,
            'restart_count': manager.restart_count,
            'error_reason': manager.error_reason
        })
    else:
        # Check DB for status
        conn = get_db()
        c = conn.cursor()
        db_status = c.execute('SELECT status FROM bots WHERE id = ?', (bot_id,)).fetchone()
        conn.close()
        return jsonify({'status': db_status['status'] if db_status else 'STOPPED'})

@app.route('/bot/resources', methods=['GET'])
@login_required_api
def bot_resources():
    bot_id = request.args.get('bot_id')
    user_id = session['user_id']
    manager = get_bot_manager(user_id, bot_id)
    if manager and manager.status == 'RUNNING':
        return jsonify(manager.get_resources())
    return jsonify({'cpu': 0, 'ram': 0})

@app.route('/bot/command', methods=['POST'])
@login_required_api
def send_command():
    data = request.json
    bot_id = data.get('bot_id')
    cmd = data.get('command')
    user_id = session['user_id']
    manager = get_bot_manager(user_id, bot_id)
    if manager and manager.status == 'RUNNING':
        success = manager.send_command(cmd)
        return jsonify({'success': success})
    return jsonify({'success': False, 'error': 'Bot not running'}), 400

@app.route('/bot/logs/download', methods=['GET'])
@login_required_api
def download_logs():
    bot_id = request.args.get('bot_id')
    user_id = session['user_id']
    manager = get_bot_manager(user_id, bot_id)
    if not manager:
        return jsonify({'error': 'Bot not found'}), 404
    logs = manager.get_logs(manager.log_queue.maxlen)
    content = '\n'.join([f'[{ts}] {"[ERROR]" if err else ""} {line}' for ts, line, err in logs])
    from io import BytesIO
    buffer = BytesIO()
    buffer.write(content.encode('utf-8'))
    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f'bot_{bot_id}_logs.txt',
        mimetype='text/plain'
    )

# ------------------ Account Management ------------------
@app.route('/account/change-password', methods=['POST'])
@login_required_api
def change_password():
    data = request.json
    old = data.get('old_password')
    new = data.get('new_password')
    user_id = session['user_id']
    conn = get_db()
    c = conn.cursor()
    user = c.execute('SELECT password_hash FROM users WHERE id = ?', (user_id,)).fetchone()
    from werkzeug.security import check_password_hash, generate_password_hash
    if not check_password_hash(user['password_hash'], old):
        conn.close()
        return jsonify({'success': False, 'message': 'Old password incorrect'}), 400
    new_hash = generate_password_hash(new)
    c.execute('UPDATE users SET password_hash = ? WHERE id = ?', (new_hash, user_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/account/delete', methods=['POST'])
@login_required_api
def delete_account():
    user_id = session['user_id']
    username = session['username']
    # Stop all bots
    if user_id in user_bots:
        for bot in user_bots[user_id].values():
            if bot.status == 'RUNNING':
                bot.stop()
        del user_bots[user_id]
    # Delete from DB
    conn = get_db()
    c = conn.cursor()
    c.execute('DELETE FROM bots WHERE user_id = ?', (user_id,))
    c.execute('DELETE FROM users WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    # Delete upload directory
    import shutil
    upload_dir = get_user_upload_dir(username)
    try:
        shutil.rmtree(upload_dir)
    except:
        pass
    logout_user()
    return jsonify({'success': True})

# ------------------ Plan Routes ------------------
@app.route('/plan/info', methods=['GET'])
@login_required_api
def plan_info():
    user_id = session['user_id']
    from plan_manager import get_user_plan, get_plan_limits
    plan = get_user_plan(user_id)
    limits = get_plan_limits(plan)
    return jsonify({
        'plan': plan,
        'limits': limits
    })

@app.route('/upgrade-plan', methods=['POST'])
@login_required_api
def upgrade_plan():
    data = request.json
    new_plan = data.get('plan')
    user_id = session['user_id']
    success, msg = upgrade_user_plan(user_id, new_plan)
    return jsonify({'success': success, 'message': msg})

# ------------------ Security ------------------
@app.route('/security/warnings', methods=['GET'])
@login_required_api
def security_warnings():
    # Placeholder for security alerts
    return jsonify({'warnings': []})

# ------------------ App Info ------------------
@app.route('/app/version', methods=['GET'])
def app_version():
    return jsonify({'version': '5.0.0', 'name': 'Telegram Bot Hosting Panel'})

# ------------------ Frontend Routes ------------------
@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

@app.route('/admin')
@admin_required
def admin_dashboard():
    return render_template('admin_dashboard.html')

@app.route('/upgrade')
@login_required
def upgrade_page():
    return render_template('upgrade.html')

# ------------------ Run ------------------
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
