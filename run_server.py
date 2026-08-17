"""
Start the TASL dashboard server.

    python run_server.py

Then open http://localhost:8000 in a browser.

host="0.0.0.0" means "listen on every network interface", which is what lets
real ESP32s on the venue Wi-Fi reach this laptop. On localhost-only it would
work in testing and then mysteriously fail with hardware.
"""

import os

import uvicorn

if __name__ == "__main__":
    # 8000 on the day. PORT only exists so a second copy can be run alongside
    # the first while rehearsing or developing - the nodes are flashed with the
    # laptop's address and port 8000 and nothing about that should change.
    uvicorn.run(
        "server.app:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
        log_level="warning",
    )
