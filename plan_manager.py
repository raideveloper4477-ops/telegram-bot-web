from models import get_db
from flask import session

PLANS = {
    'FREE': {
        'name': 'Free',
        'max_bots': 1,
        'max_runtime_hours': 24,
        'max_restarts': 3,
        'max_log_lines': 500,
        'max_cpu': 50,
        'max_ram_mb': 200,
    },
    'PRO': {
        'name': 'Pro',
        'max_bots': 3,
        'max_runtime_hours': 72,
        'max_restarts': 10,
        'max_log_lines': 5000,
        'max_cpu': 80,
        'max_ram_mb': 500,
    },
    'ULTRA': {
        'name': 'Ultra',
        'max_bots': 10,
        'max_runtime_hours': 8760,
        'max_restarts': 9999,
        'max_log_lines': 50000,
        'max_cpu': 95,
        'max_ram_mb': 1000,
    }
}

def get_user_plan(user_id):
    conn = get_db()
    c = conn.cursor()
    user = c.execute('SELECT plan FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    if not user:
        return 'FREE'
    return user['plan']

def get_plan_limits(plan_name):
    return PLANS.get(plan_name, PLANS['FREE'])

def get_user_limits(user_id):
    plan = get_user_plan(user_id)
    return get_plan_limits(plan)

def can_start_bot(user_id):
    limits = get_user_limits(user_id)
    # Check bot count
    conn = get_db()
    c = conn.cursor()
    count = c.execute('SELECT COUNT(*) as cnt FROM bots WHERE user_id = ? AND status != "STOPPED"', (user_id,)).fetchone()['cnt']
    conn.close()
    if count >= limits['max_bots']:
        return False, f'Bot limit reached ({limits["max_bots"]}) for your plan'
    return True, 'OK'

def upgrade_user_plan(user_id, new_plan):
    if new_plan not in PLANS:
        return False, 'Invalid plan'
    conn = get_db()
    c = conn.cursor()
    c.execute('UPDATE users SET plan = ? WHERE id = ?', (new_plan, user_id))
    conn.commit()
    conn.close()
    return True, 'Plan upgraded'