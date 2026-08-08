"""Case B fixture: the API process.

Started independently of worker/worker.py -- see ../docker-compose.yaml for
the distinct start command, restart policy, and scaling for this service.
"""
from flask import Flask

app = Flask(__name__)


@app.route("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
