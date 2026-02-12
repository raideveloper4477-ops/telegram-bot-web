from flask import Blueprint, request, jsonify, session
from models import get_db
from auth import admin_required
from bot_manager import user_bots, get_bot_manager
import json

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/admin/login', methods=['POST'])
def admin_login():
    """Admin login (separate from regular login) - same endpoint but role check happens later."""
    from auth import login_user
    data = request.json
    success, msg = login_user(data.get('username'), data.get('password'))
    if success and session.get('role') != 'ADMIN':
        session.clear()
        return jsonify({'error': 'Not an admin'}), 403
    return jsonify({'success': success, 'message': msg})

@admin_bp.route('/admin/users', methods=['GET'])
@admin_required
def get_users():
    conn = get_db()
    c = conn.cursor()
    users = c.execute('SELECT id, username, first_name, last_name, email_or_phone, role, plan, suspended FROM users').fetchall()
    conn.close()
    return jsonify([dict(u) for u in users])

@admin_bp.route('/admin/user/suspend', methods=['POST'])
@admin_required
def suspend_user():
    data = request.json
    user_id = data.get('user_id')
    suspend = data.get('suspend', True)
    conn = get_db()
    c = conn.cursor()
    c.execute('UPDATE users SET suspended = ? WHERE id = ?', (1 if suspend else 0, user_id))
    conn.commit()
    # Force stop all bots of this user
    if user_id in user_bots:
        for bot in user_bots[user_id].values():
            if bot.status == 'RUNNING':
                bot.stop()
    conn.close()
    return jsonify({'success': True})

@admin_bp.route('/admin/user/delete', methods=['POST'])
@admin_required
def delete_user():
    data = request.json
    user_id = data.get('user_id')
    conn = get_db()
    c = conn.cursor()
    # Stop all bots
    if user_id in user_bots:
        for bot in user_bots[user_id].values():
            if bot.status == 'RUNNING':
                bot.stop()
        del user_bots[user_id]
    # Delete user's bots from DB
    c.execute('DELETE FROM bots WHERE user_id = ?', (user_id,))
    # Delete user
    c.execute('DELETE FROM users WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@admin_bp.route('/admin/user/change-plan', methods=['POST'])
@admin_required
def change_plan():
    data = request.json
    user_id = data.get('user_id')
    plan = data.get('plan')
    conn = get_db()
    c = conn.cursor()
    c.execute('UPDATE users SET plan = ? WHERE id = ?', (plan, user_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@admin_bp.route('/admin/bots', methods=['GET'])
@admin_required
def get_all_bots():
    conn = get_db()
    c = conn.cursor()
    bots = c.execute('''
        SELECT bots.*, users.username as owner_username
        FROM bots
        JOIN users ON bots.user_id = users.id
    ''').fetchall()
    conn.close()
    result = []
    for b in bots:
        bdict = dict(b)
        if b['user_id'] in user_bots and b['id'] in user_bots[b['user_id']]:
            bdict['running'] = user_bots[b['user_id']][b['id']].status == 'RUNNING'
        else:
            bdict['running'] = False
        result.append(bdict)
    return jsonify(result)

@admin_bp.route('/admin/bot/force-stop', methods=['POST'])
@admin_required
def force_stop_bot():
    data = request.json
    bot_id = data.get('bot_id')
    conn = get_db()
    c = conn.cursor()
    bot = c.execute('SELECT user_id FROM bots WHERE id = ?', (bot_id,)).fetchone()
    if bot:
        user_id = bot['user_id']
        if user_id in user_bots and bot_id in user_bots[user_id]:
            user_bots[user_id][bot_id].stop()
    conn.close()
    return jsonify({'success': True})

@admin_bp.route('/admin/system-stats', methods=['GET'])
@admin_required
def system_stats():
    conn = get_db()
    c = conn.cursor()
    total_users = c.execute('SELECT COUNT(*) as cnt FROM users').fetchone()['cnt']
    total_bots = c.execute('SELECT COUNT(*) as cnt FROM bots').fetchone()['cnt']
    running_bots = sum(1 for u in user_bots for b in user_bots[u] if user_bots[u][b].status == 'RUNNING')
    conn.close()
    return jsonify({
        'total_users': total_users,
        'total_bots': total_bots,
        'running_bots': running_bots
    })