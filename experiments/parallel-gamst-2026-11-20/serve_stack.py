"""Start (or restart) the stack's model servers exactly as declared, one after another.

    python serve_stack.py stack.json [--stop]

Used when servers stay up across many crew runs (run_crew.py --keep-servers). PIDs go to
/srv/par/servers.json; logs to /srv/par/logs/<name>.log.
"""
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

STATE = Path("/srv/par/servers.json")


def stop():
    if STATE.exists():
        for name, pid in json.loads(STATE.read_text()).items():
            try:
                os.killpg(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        time.sleep(10)
        STATE.unlink()


def main():
    stack = json.loads(Path(sys.argv[1]).read_text())
    stop()
    if "--stop" in sys.argv:
        return
    pids = {}
    for spec in stack["servers"]:
        log = open(f"/srv/par/logs/{spec['name']}.log", "a")
        proc = subprocess.Popen(spec["argv"], stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
                                env={**os.environ, **spec.get("env", {})})
        pids[spec["name"]] = proc.pid
        STATE.write_text(json.dumps(pids))
        deadline = time.time() + spec.get("startup_timeout_s", 900)
        while time.time() < deadline:
            if proc.poll() is not None:
                raise SystemExit(f"{spec['name']} exited {proc.returncode}")
            try:
                urllib.request.urlopen(spec["health_url"], timeout=2)
                print(spec["name"], "ready", flush=True)
                break
            except Exception:
                time.sleep(3)
        else:
            raise SystemExit(f"{spec['name']} not ready")


if __name__ == "__main__":
    main()
