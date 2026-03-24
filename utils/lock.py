"""
Модуль для защиты от дублирующихся процессов.
Lock-файл хранится в постоянном хранилище /data.
"""

import os
import fcntl
import atexit
import time
import signal

# Путь к постоянному хранилищу Amvera
DATA_DIR = "/data"
LOCK_FILE = os.path.join(DATA_DIR, "nexus_bot.lock")

# Создаём папку /data, если её нет (локально для тестов)
os.makedirs(DATA_DIR, exist_ok=True)

lock_fd = None

def acquire_lock() -> bool:
    """
    Пытается захватить блокировку.
    Возвращает True если блокировка захвачена успешно.
    Возвращает False если процесс уже запущен.
    """
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
        print(f"⚠️ Ошибка при создании блокировки: {e}")
        return False

def release_lock():
    """Освобождает блокировку"""
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
    """
    Убивает другие процессы бота (принудительно).
    """
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
            print(f"🔪 Убит старый процесс бота (PID: {old_pid})")
            time.sleep(2)
        except OSError:
            pass
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
    except (FileNotFoundError, ValueError, OSError):
        pass
    except Exception as e:
        print(f"⚠️ Ошибка при очистке старых процессов: {e}")
