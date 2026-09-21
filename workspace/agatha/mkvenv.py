import subprocess, sys
# create venv with uv
r = subprocess.run(['uv', 'venv', '/workspace/agatha/.venv_pil'], capture_output=True, text=True)
print('venv rc', r.returncode, r.stdout[-500:], r.stderr[-500:])
