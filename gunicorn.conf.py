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
    from app import start_scheduler_once, register_signal_handlers

    register_signal_handlers()
    start_scheduler_once()
