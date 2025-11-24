bind = "0.0.0.0:3000"
workers = 1
threads = 4
timeout = 60
graceful_timeout = 30
preload_app = False


def post_worker_init(worker):
    """
    Start the scheduler after the worker is initialized so it runs
    alongside the web server (one instance because workers=1).
    """
    from app import start_scheduler_once

    start_scheduler_once()


def worker_exit(worker, status):
    """
    Stop the scheduler on worker exit to avoid duplicate runs during restarts.
    """
    try:
        from app import stop_scheduler

        stop_scheduler(reason="worker_exit")
    except Exception:
        # Best effort; avoid crashing gunicorn shutdown.
        pass
