import subprocess
import threading
import time
import os
import signal
import queue
import psutil
from datetime import datetime, timedelta
from collections import deque
from flask import session
from utils import get_user_upload_dir, escape_log_output
from plan_manager import get_user_limits, can_start_bot
import security

# Global storage: user_bots[user_id][bot_id] = BotProcess
user_bots = {}
bot_lock = threading.RLock()

class BotProcess:
    def __init__(self, user_id, bot_id, username, bot_name):
        self.user_id = user_id
        self.bot_id = bot_id
        self.username = username
        self.bot_name = bot_name
        self.process = None
        self.status = 'STOPPED'  # RUNNING, STOPPED, ERROR
        self.log_queue = deque(maxlen=5000)  # store (timestamp, line, is_error)
        self.start_time = None
        self.stop_event = threading.Event()
        self.restart_count = 0
        self.max_restarts = get_user_limits(user_id)['max_restarts']
        self.crash_detected = False
        self.error_reason = None
        self.cpu_usage = 0.0
        self.ram_usage = 0
        self.command_queue = queue.Queue()
        self.log_timestamps = deque(maxlen=200)  # for spam detection
        self.auto_stop_timer = None

    def _get_work_dir(self):
        return get_user_upload_dir(self.username)

    def install_requirements(self):
        req_path = os.path.join(self._get_work_dir(), 'requirements.txt')
        if os.path.exists(req_path):
            try:
                subprocess.run(['pip', 'install', '-r', req_path], check=True, capture_output=True, text=True)
                self._add_log('requirements.txt installed successfully', False)
            except subprocess.CalledProcessError as e:
                self._add_log(f'Failed to install requirements: {e.stderr}', True)
                return False
        else:
            self._add_log('No requirements.txt found, skipping', False)
        return True

    def start(self):
        with bot_lock:
            if self.status == 'RUNNING':
                return False, 'Bot already running'
            
            # Check limits
            allowed, msg = can_start_bot(self.user_id)
            if not allowed:
                return False, msg
            
            self.stop_event.clear()
            self.restart_count = 0
            self.crash_detected = False
            self.error_reason = None
            
            # Save bot status to DB
            from models import get_db
            conn = get_db()
            c = conn.cursor()
            c.execute('UPDATE bots SET status = ? WHERE id = ?', ('RUNNING', self.bot_id))
            conn.commit()
            conn.close()
            
            # Start the bot in a thread
            threading.Thread(target=self._run_bot, daemon=True).start()
            # Start resource monitor
            threading.Thread(target=self._monitor_resources, daemon=True).start()
            return True, 'Bot started'

    def _run_bot(self):
        # Install requirements
        if not self.install_requirements():
            self.status = 'ERROR'
            self.error_reason = 'Requirements installation failed'
            self._update_db_status('ERROR')
            return
        
        while not self.stop_event.is_set() and self.restart_count <= self.max_restarts:
            bot_path = os.path.join(self._get_work_dir(), 'bot.py')
            if not os.path.exists(bot_path):
                self._add_log('bot.py not found', True)
                self.status = 'ERROR'
                self.error_reason = 'bot.py missing'
                self._update_db_status('ERROR')
                return
            
            self._add_log(f'Starting bot (attempt {self.restart_count+1})...', False)
            self.status = 'RUNNING'
            self._update_db_status('RUNNING')
            self.start_time = datetime.now()
            
            # Auto-stop after plan runtime
            limits = get_user_limits(self.user_id)
            runtime_seconds = limits['max_runtime_hours'] * 3600
            self.auto_stop_timer = threading.Timer(runtime_seconds, self._auto_stop)
            self.auto_stop_timer.daemon = True
            self.auto_stop_timer.start()
            
            try:
                self.process = subprocess.Popen(
                    ['python', bot_path],
                    cwd=self._get_work_dir(),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    preexec_fn=os.setsid if hasattr(os, 'setsid') else None
                )
                
                # Read output line by line
                for line in iter(self.process.stdout.readline, ''):
                    if self.stop_event.is_set():
                        self.process.terminate()
                        break
                    if line:
                        self._add_log(line.rstrip(), False)
                
                self.process.wait()
                exit_code = self.process.returncode
                self._add_log(f'Bot exited with code {exit_code}', False)
                
                if self.auto_stop_timer:
                    self.auto_stop_timer.cancel()
                
                if not self.stop_event.is_set() and exit_code != 0:
                    # Crash detected
                    self.crash_detected = True
                    self.restart_count += 1
                    if self.restart_count <= self.max_restarts:
                        self._add_log(f'Restarting ({self.restart_count}/{self.max_restarts})...', True)
                        time.sleep(2)  # Wait before restart
                    else:
                        self._add_log('Max restarts exceeded. Bot stopped.', True)
                        self.status = 'ERROR'
                        self.error_reason = 'Max restarts'
                        self._update_db_status('ERROR')
                else:
                    # Normal stop
                    break
                    
            except Exception as e:
                self._add_log(f'Error: {str(e)}', True)
                self.status = 'ERROR'
                self.error_reason = str(e)
                self._update_db_status('ERROR')
                break
        
        if self.status != 'ERROR':
            self.status = 'STOPPED'
            self._update_db_status('STOPPED')
        self._add_log('Bot stopped', False)

    def _auto_stop(self):
        self._add_log('24-hour runtime limit reached. Auto-stopping.', True)
        self.stop()

    def stop(self):
        with bot_lock:
            if self.process and self.process.poll() is None:
                self.stop_event.set()
                try:
                    # Try graceful termination
                    if hasattr(os, 'setsid'):
                        os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                    else:
                        self.process.terminate()
                    self.process.wait(timeout=5)
                except:
                    # Force kill
                    if hasattr(os, 'setsid'):
                        os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
                    else:
                        self.process.kill()
                self.process = None
            self.status = 'STOPPED'
            self._update_db_status('STOPPED')
            if self.auto_stop_timer:
                self.auto_stop_timer.cancel()
            self._add_log('Bot stopped by user', False)

    def _add_log(self, line, is_error=False):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        escaped = escape_log_output(line)
        self.log_queue.append((timestamp, escaped, is_error))
        # For spam detection
        if is_error:
            self.log_timestamps.append(time.time())
            if security.check_spam_logs(self.log_timestamps):
                self._add_log('Spam detected! Bot will be stopped.', True)
                self.stop()

    def get_logs(self, max_lines=500):
        lines = list(self.log_queue)[-max_lines:]
        return lines

    def _monitor_resources(self):
        """Update CPU and RAM usage every 2 seconds."""
        while self.status == 'RUNNING' and self.process and self.process.poll() is None:
            try:
                p = psutil.Process(self.process.pid)
                self.cpu_usage = p.cpu_percent(interval=0.1)
                self.ram_usage = p.memory_info().rss // (1024 * 1024)  # MB
                
                # Check against plan limits
                limits = get_user_limits(self.user_id)
                if self.cpu_usage > limits['max_cpu']:
                    self._add_log(f'CPU usage {self.cpu_usage}% exceeds limit ({limits["max_cpu"]}%). Stopping bot.', True)
                    self.stop()
                if self.ram_usage > limits['max_ram_mb']:
                    self._add_log(f'RAM usage {self.ram_usage}MB exceeds limit ({limits["max_ram_mb"]}MB). Stopping bot.', True)
                    self.stop()
            except:
                pass
            time.sleep(2)

    def _update_db_status(self, status):
        from models import get_db
        conn = get_db()
        c = conn.cursor()
        c.execute('UPDATE bots SET status = ? WHERE id = ?', (status, self.bot_id))
        conn.commit()
        conn.close()

    def send_command(self, cmd):
        if self.process and self.process.poll() is None and self.process.stdin:
            sanitized = security.sanitize_input(cmd)
            self.process.stdin.write(sanitized + '\n')
            self.process.stdin.flush()
            self._add_log(f'> {sanitized}', False)
            return True
        return False

    def get_resources(self):
        return {
            'cpu': round(self.cpu_usage, 1),
            'ram': self.ram_usage
        }

def get_bot_manager(user_id, bot_id):
    with bot_lock:
        if user_id in user_bots and bot_id in user_bots[user_id]:
            return user_bots[user_id][bot_id]
    return None

def create_bot_manager(user_id, bot_id, username, bot_name):
    with bot_lock:
        if user_id not in user_bots:
            user_bots[user_id] = {}
        user_bots[user_id][bot_id] = BotProcess(user_id, bot_id, username, bot_name)
        return user_bots[user_id][bot_id]

def delete_bot_manager(user_id, bot_id):
    with bot_lock:
        if user_id in user_bots and bot_id in user_bots[user_id]:
            # Ensure bot is stopped
            bot = user_bots[user_id][bot_id]
            if bot.status == 'RUNNING':
                bot.stop()
            del user_bots[user_id][bot_id]