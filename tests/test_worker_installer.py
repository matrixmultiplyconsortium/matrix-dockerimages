"""
Integration and syntax validation tests for worker.sh and worker.ps1 installers.
"""

import os
import shutil
import subprocess
import sys
import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DOCKERIMAGES_DIR = os.path.join(REPO_ROOT, "matrix-dockerimages")
WORKER_SH = os.path.join(DOCKERIMAGES_DIR, "worker.sh")
WORKER_PS1 = os.path.join(DOCKERIMAGES_DIR, "worker.ps1")


def get_bash_bin():
    """Locate real bash binary (prefer Git Bash on Windows over broken WSL system32 stubs)."""
    git_bash_paths = [
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
        r"C:\Git\bin\bash.exe",
    ]
    for p in git_bash_paths:
        if os.path.exists(p):
            return p
    b = shutil.which("bash")
    if b and "system32" not in b.lower():
        return b
    return None


def test_worker_sh_exists_and_shebang():
    assert os.path.isfile(WORKER_SH)
    with open(WORKER_SH, "r", encoding="utf-8") as f:
        first_line = f.readline().strip()
    assert first_line in ("#!/usr/bin/env bash", "#!/bin/bash", "#!/bin/sh")


def test_worker_sh_syntax():
    bash_bin = get_bash_bin()
    if not bash_bin:
        pytest.skip("Bash executable not found in test environment")

    res = subprocess.run(
        [bash_bin, "-n", WORKER_SH],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace",
    )
    assert res.returncode == 0, f"Bash syntax check failed: {res.stderr}"


def test_worker_sh_dry_run_nvidia(tmp_worker_dir):
    bash_bin = get_bash_bin()
    if not bash_bin:
        pytest.skip("Bash executable not found in test environment")

    env_target = os.path.join(tmp_worker_dir, "test.env")
    cmd = [
        bash_bin,
        WORKER_SH,
        "--dry-run",
        "--mock-hardware", "nvidia",
        "--non-interactive",
        "--payout-address", "operator@matrixcompute.io",
        "--env-file", env_target,
    ]
    res = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace",
        cwd=DOCKERIMAGES_DIR,
    )
    assert res.returncode == 0, f"worker.sh dry-run failed: {res.stderr}"
    stdout = res.stdout

    assert "Python runtime verified" in stdout
    assert "NVIDIA GeForce RTX 4090" in stdout
    assert "Dry-Run Active. Generated Docker Execution Command:" in stdout
    assert 'MATRIX_WORKER_NAT_MODE="reverse_tunnel"' in stdout
    assert "matrixcompute/worker:gpu" in stdout
    assert "operator@matrixcompute.io" in stdout
    assert "OPERATOR DASHBOARD" in stdout


def test_worker_sh_dry_run_cpu(tmp_worker_dir):
    bash_bin = get_bash_bin()
    if not bash_bin:
        pytest.skip("Bash executable not found in test environment")

    env_target = os.path.join(tmp_worker_dir, "test_cpu.env")
    cmd = [
        bash_bin,
        WORKER_SH,
        "--dry-run",
        "--mock-hardware", "cpu",
        "--non-interactive",
        "--payout-address", "cpu_worker@matrixcompute.io",
        "--env-file", env_target,
    ]
    res = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace",
        cwd=DOCKERIMAGES_DIR,
    )
    assert res.returncode == 0
    stdout = res.stdout

    assert "CPU Fallback" in stdout or "CPU" in stdout
    assert "matrixcompute/worker:latest" in stdout
    assert "--gpus all" not in stdout


def test_worker_ps1_exists():
    assert os.path.isfile(WORKER_PS1)
    with open(WORKER_PS1, "r", encoding="utf-8") as f:
        content = f.read()
    assert "[CmdletBinding()]" in content
    assert "param" in content


def test_worker_ps1_dry_run_nvidia(tmp_worker_dir):
    pwsh_bin = shutil.which("powershell") or shutil.which("pwsh")
    if not pwsh_bin:
        pytest.skip("PowerShell executable not found")

    env_target = os.path.join(tmp_worker_dir, "ps1_nvidia.env")
    cmd = [
        pwsh_bin,
        "-NoProfile",
        "-File", WORKER_PS1,
        "-DryRun",
        "-MockHardware", "nvidia",
        "-NonInteractive",
        "-PayoutAddress", "ps1_operator@matrixcompute.io",
        "-EnvFile", env_target,
    ]
    res = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace",
        cwd=DOCKERIMAGES_DIR,
    )
    assert res.returncode == 0, f"worker.ps1 failed: {res.stderr}\n{res.stdout}"
    stdout = res.stdout

    assert "Python runtime verified" in stdout
    assert "NVIDIA GeForce RTX 4090" in stdout
    assert "Dry-Run Active. Generated Docker Execution Command:" in stdout
    assert 'MATRIX_WORKER_NAT_MODE="reverse_tunnel"' in stdout
    assert "matrixcompute/worker:gpu" in stdout
    assert "ps1_operator@matrixcompute.io" in stdout
    assert "OPERATOR DASHBOARD" in stdout


def test_worker_ps1_dry_run_cpu(tmp_worker_dir):
    pwsh_bin = shutil.which("powershell") or shutil.which("pwsh")
    if not pwsh_bin:
        pytest.skip("PowerShell executable not found")

    env_target = os.path.join(tmp_worker_dir, "ps1_cpu.env")
    cmd = [
        pwsh_bin,
        "-NoProfile",
        "-File", WORKER_PS1,
        "-DryRun",
        "-MockHardware", "cpu",
        "-NonInteractive",
        "-PayoutAddress", "cpu_ps1@matrixcompute.io",
        "-EnvFile", env_target,
    ]
    res = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace",
        cwd=DOCKERIMAGES_DIR,
    )
    assert res.returncode == 0, f"worker.ps1 failed: {res.stderr}\n{res.stdout}"
    stdout = res.stdout

    assert "CPU" in stdout
    assert "matrixcompute/worker:latest" in stdout
    assert "--gpus all" not in stdout


def test_worker_sh_dry_run_rocm(tmp_worker_dir):
    bash_bin = get_bash_bin()
    if not bash_bin:
        pytest.skip("Bash executable not found")

    env_target = os.path.join(tmp_worker_dir, "rocm.env")
    cmd = [
        bash_bin, WORKER_SH, "--dry-run", "--mock-hardware", "rocm",
        "--non-interactive", "--env-file", env_target,
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8", errors="replace", cwd=DOCKERIMAGES_DIR)
    assert res.returncode == 0
    assert "matrixcompute/worker:gpu" in res.stdout
    assert "--device=/dev/kfd --device=/dev/dri --ipc=host" in res.stdout


def test_worker_sh_dry_run_sev_snp(tmp_worker_dir):
    bash_bin = get_bash_bin()
    if not bash_bin:
        pytest.skip("Bash executable not found")

    env_target = os.path.join(tmp_worker_dir, "sev.env")
    cmd = [
        bash_bin, WORKER_SH, "--dry-run", "--mock-hardware", "sev-snp",
        "--non-interactive", "--env-file", env_target,
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8", errors="replace", cwd=DOCKERIMAGES_DIR)
    assert res.returncode == 0
    assert "matrixcompute/worker:latest" in res.stdout
    assert "--device=/dev/sev-guest" in res.stdout
    assert "--device=/dev/kfd" not in res.stdout


def test_worker_ps1_dry_run_rocm(tmp_worker_dir):
    pwsh_bin = shutil.which("powershell") or shutil.which("pwsh")
    if not pwsh_bin:
        pytest.skip("PowerShell executable not found")

    env_target = os.path.join(tmp_worker_dir, "ps1_rocm.env")
    cmd = [
        pwsh_bin,
        "-NoProfile",
        "-File", WORKER_PS1,
        "-DryRun",
        "-MockHardware", "rocm",
        "-NonInteractive",
        "-PayoutAddress", "rocm_ps1@matrixcompute.io",
        "-EnvFile", env_target,
    ]
    res = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace",
        cwd=DOCKERIMAGES_DIR,
    )
    assert res.returncode == 0, f"worker.ps1 failed: {res.stderr}\n{res.stdout}"
    assert "matrixcompute/worker:gpu" in res.stdout
    assert "--device=/dev/kfd --device=/dev/dri --ipc=host" in res.stdout


def test_worker_ps1_dry_run_sev_snp(tmp_worker_dir):
    pwsh_bin = shutil.which("powershell") or shutil.which("pwsh")
    if not pwsh_bin:
        pytest.skip("PowerShell executable not found")

    env_target = os.path.join(tmp_worker_dir, "ps1_sev.env")
    cmd = [
        pwsh_bin,
        "-NoProfile",
        "-File", WORKER_PS1,
        "-DryRun",
        "-MockHardware", "sev-snp",
        "-NonInteractive",
        "-PayoutAddress", "sev_ps1@matrixcompute.io",
        "-EnvFile", env_target,
    ]
    res = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace",
        cwd=DOCKERIMAGES_DIR,
    )
    assert res.returncode == 0, f"worker.ps1 failed: {res.stderr}\n{res.stdout}"
    assert "matrixcompute/worker:latest" in res.stdout
    assert "--device=/dev/sev-guest" in res.stdout
    assert "--device=/dev/kfd" not in res.stdout

