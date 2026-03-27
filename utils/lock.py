import os
import fcntl
import atexit

DATA_DIR = "/data"
LOCK_FILE = os.path.join(DATA_DIR, "nexus_bot.lock")
os.makedirs(DATA_DIR, exist_ok=True)

lock_fd = None

def acquire_lock():
    global lock_fd
    try:
        lock_fd = open(LOCK_FILE, 'w')
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_fd.write(str(os.getpid()))
        lock_fd.flush()
        atexit.register(release_lock)
        return True
    except:
        return False

def release_lock():
    global lock_fd
    if lock_fd:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()
        except:
            pass
