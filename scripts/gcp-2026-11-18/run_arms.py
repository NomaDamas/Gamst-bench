"""Run FastBench arms from the frozen manifest against an alternate root (subset or full)."""
import json
import pathlib
import subprocess
import sys
import time

root = pathlib.Path(sys.argv[1])
arms = sys.argv[2].split(",")
man = json.load(open("/srv/manifests/frozen-fastbench-2026-11-18.json"))


GEMINI = "google/gemini-3-flash-preview"


def command(arm: str) -> str:
    if arm == "D-periodic":
        # Matched ablation of C-gamst: same backbone, same 5 s semantic interval,
        # but no change-triggered selection (CallPolicy mode=periodic).
        cmd = man["arms"]["C-gamst"]["command"]
        cmd = cmd.replace("GAMST_EXTENSION_POLICY=sentinel", "GAMST_EXTENSION_POLICY=periodic")
        cmd = cmd.replace("C-gamst", "D-periodic").replace("c-gamst", "d-periodic")
        assert "POLICY=periodic" in cmd
        return cmd
    if arm == "A-gemini":
        # Native baseline runner; backbone is Gemini on Vertex via loopback proxy :8091.
        # The judge stays the local Qwen3-VL-8B server (:8080) for every arm.
        cmd = man["arms"]["A-baseline"]["command"]
        cmd = cmd.replace("STREAMEVAL_QWEN3_VL_API_BASE=http://127.0.0.1:8080/v1",
                          f"STREAMEVAL_QWEN3_VL_API_BASE=http://127.0.0.1:8091/v1 STREAMEVAL_QWEN3_VL_MODEL={GEMINI}")
        cmd = cmd.replace("BASE_PORT=8080", "BASE_PORT=8091")
        cmd = cmd.replace("A-baseline", "A-gemini").replace("a-baseline", "a-gemini")
        assert "8091" in cmd and GEMINI in cmd
        return cmd
    if arm == "C-gemini":
        # The extension takes api_base/model from the native YAML (env-expanded) and
        # --api-bases, so every backbone endpoint moves to proxy :8092; judge stays :8080.
        cmd = man["arms"]["C-gamst"]["command"]
        cmd = cmd.replace("STREAMEVAL_QWEN3_VL_API_BASE=http://127.0.0.1:8080/v1",
                          f"STREAMEVAL_QWEN3_VL_API_BASE=http://127.0.0.1:8092/v1 STREAMEVAL_QWEN3_VL_MODEL={GEMINI}")
        cmd = cmd.replace("GAMST_EXTENSION_VLM_URL=http://127.0.0.1:8080/v1",
                          "GAMST_EXTENSION_VLM_URL=http://127.0.0.1:8092/v1")
        cmd = cmd.replace("--api-bases http://127.0.0.1:8080/v1", "--api-bases http://127.0.0.1:8092/v1")
        cmd = cmd.replace("GAMST_EXTENSION_MODEL=Qwen/Qwen3-VL-8B-Instruct", f"GAMST_EXTENSION_MODEL={GEMINI}")
        cmd = cmd.replace("C-gamst", "C-gemini").replace("c-gamst", "c-gemini")
        assert cmd.count("8092") == 3 and "JUDGER_API_BASE=http://127.0.0.1:8080/v1" in cmd
        return cmd
    return man["arms"][arm]["command"]


for arm in arms:
    cmd = command(arm)
    for name in ["baseline", "proactive"]:
        cmd = cmd.replace(f"/srv/gamst-runs/fastbench-measured/configs/{name}.yaml", str(root / f"{name}.yaml"))
    cmd = cmd.replace(f"/srv/gamst-runs/fastbench-measured/{arm}", str(root / arm))
    d = root / arm
    d.mkdir(parents=True, exist_ok=True)
    partial = list(d.glob("qwen3_vl_*/inference/phostream.jsonl"))
    if partial and partial[0].stat().st_size > 0:
        cmd += " --resume"
    (d / "command.txt").write_text(cmd + "\n")
    t = time.time()
    with open(d / "run.log", "a") as log:
        rc = subprocess.run(
            ["bash", "-lc", cmd], stdout=log, stderr=subprocess.STDOUT,
            env={"PATH": "/srv/venv-fastbench/bin:/usr/local/bin:/usr/bin:/bin",
                 "HOME": "/home/jinminseong", "PYTHONUNBUFFERED": "1"}).returncode
    (d / "status.json").write_text(json.dumps({"arm": arm, "exit_code": rc, "wall_s": time.time() - t}) + "\n")
    print(arm, rc, round(time.time() - t, 1), flush=True)
