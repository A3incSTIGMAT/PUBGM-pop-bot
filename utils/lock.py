"""
Модуль для защиты от дублирующихся процессов.
"""

import os
import fcntl
import atexit
import time
import signal

LOCK_FILE = "/tmp/nexus_bot.lock"
lock_fd = None

def acquire_lock() -> bool:
    global lock_fd
    try:
        lock_fd = open(LOCK_FILE, 'w')
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_fd.write(str(os.getpid()))
        lock_fd.flush()
        atexit.register(release_lock)
        return True
    except (IOError, OSError):
        return False
    except Exception as e:
        print(f"⚠️ Ошибка: {e}")
        return False

def release_lock():
    global lock_fd
    if lock_fd:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()
        except:
            pass
        try:
            if os.path.exists(LOCK_FILE):
                os.remove(LOCK_FILE)
        except:
            pass

def kill_other_processes():
    try:
        if not os.path.exists(LOCK_FILE):
            return
        with open(LOCK_FILE, 'r') as f:
            content = f.read().strip()
            if not content:
                return
            old_pid = int(content)
        try:
            os.kill(old_pid, 0)
            os.kill(old_pid, signal.SIGTERM)
            print(f"🔪 Убит старый процесс (PID: {old_pid})")
            time.sleep(2)
        except OSError:
            pass
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
    except:
        pass
