"""Case B fixture: the background worker process.

Started independently of api/app.py -- see ../docker-compose.yaml for the
distinct start command, restart policy, and scaling for this service.
Neither process imports, starts, stops, or supervises the other.
"""
import time


def process_queue():
    while True:
        time.sleep(5)


if __name__ == "__main__":
    process_queue()
