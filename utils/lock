"""
Модуль для защиты от дублирующихся процессов.
Использует файл-блокировку (lockfile).
НЕ ЗАВИСИТ ОТ ДРУГИХ МОДУЛЕЙ utils.
"""

import os
import fcntl
import atexit
import time
import signal

LOCK_FILE = "/tmp/nexus_bot.lock"
lock_fd = None

def acquire_lock() -> bool:
    """
    Пытается захватить блокировку.
    Возвращает True если блокировка захвачена успешно.
    Возвращает False если процесс уже запущен.
    """
    global lock_fd
    
    try:
        # Открываем файл блокировки
        lock_fd = open(LOCK_FILE, 'w')
        
        # Пытаемся захватить эксклюзивную блокировку (неблокирующую)
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        
        # Записываем PID процесса
        lock_fd.write(str(os.getpid()))
        lock_fd.flush()
        
        # Регистрируем функцию освобождения блокировки при завершении
        atexit.register(release_lock)
        
        return True
        
    except (IOError, OSError):
        # Блокировка уже захвачена другим процессом
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
    Используется при старте, если нужно гарантированно очистить.
    """
    try:
        # Читаем PID из файла блокировки
        if not os.path.exists(LOCK_FILE):
            return
            
        with open(LOCK_FILE, 'r') as f:
            content = f.read().strip()
            if not content:
                return
            old_pid = int(content)
        
        # Проверяем, существует ли процесс с таким PID
        try:
            os.kill(old_pid, 0)  # Проверка существования
            # Процесс существует — убиваем его
            os.kill(old_pid, signal.SIGTERM)
            print(f"🔪 Убит старый процесс бота (PID: {old_pid})")
            time.sleep(2)  # Ждём завершения
        except OSError:
            # Процесс не существует — просто удаляем блокировку
            pass
        
        # Удаляем старый файл блокировки
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
        
    except (FileNotFoundError, ValueError, OSError):
        pass
    except Exception as e:
        print(f"⚠️ Ошибка при очистке старых процессов: {e}")
