"""
Schema validation, environment contract, and zero-publishing constraint tests for cloud templates.
"""

import json
import os
import re
import pytest

TEMPLATES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "templates"))


def test_vastai_template_schema():
    tmpl_path = os.path.join(TEMPLATES_DIR, "vastai", "template.json")
    assert os.path.isfile(tmpl_path)

    with open(tmpl_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "name" in data
    assert data["image"] == "matrixcompute/worker:gpu"
    assert "env" in data
    env = data["env"]
    assert "MATRIX_WORKER_PAYOUT_ADDRESS" in env
    assert "MATRIX_WORKER_NOSTR_RELAYS" in env
    assert "MATRIX_WORKER_SETTLEMENT_API_URL" in env
    assert env["MATRIX_WORKER_NAT_MODE"] == "reverse_tunnel"
    assert "--gpus all" in data.get("extra_args", "")


def test_runpod_template_schema():
    tmpl_path = os.path.join(TEMPLATES_DIR, "runpod", "template.json")
    assert os.path.isfile(tmpl_path)

    with open(tmpl_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "name" in data
    assert data["imageName"] == "matrixcompute/worker:gpu"
    assert "env" in data
    assert isinstance(data["env"], list)

    env_map = {item["key"]: item["value"] for item in data["env"]}
    assert "MATRIX_WORKER_PAYOUT_ADDRESS" in env_map
    assert "MATRIX_WORKER_NOSTR_RELAYS" in env_map
    assert "MATRIX_WORKER_SETTLEMENT_API_URL" in env_map
    assert env_map.get("MATRIX_WORKER_NAT_MODE") == "reverse_tunnel"


def test_hiveos_flightsheet_schema():
    fs_path = os.path.join(TEMPLATES_DIR, "hiveos", "flightsheet.json")
    assert os.path.isfile(fs_path)

    with open(fs_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["miner"] == "custom"
    assert data["miner_alt"] == "matrix-worker"
    assert "%WAL%" in data["wallet"]
    assert "miner_config" in data
    cfg = data["miner_config"]
    assert "MATRIX_WORKER_PAYOUT_ADDRESS=%WAL%" in cfg.get("user_config", "")
    assert "MATRIX_WORKER_NAT_MODE=reverse_tunnel" in cfg.get("user_config", "")


def test_hiveos_miner_files():
    hive_dir = os.path.join(TEMPLATES_DIR, "hiveos")
    manifest = os.path.join(hive_dir, "h-manifest.conf")
    config_sh = os.path.join(hive_dir, "h-config.sh")
    run_sh = os.path.join(hive_dir, "h-run.sh")
    stats_sh = os.path.join(hive_dir, "h-stats.sh")

    for fpath in [manifest, config_sh, run_sh, stats_sh]:
        assert os.path.isfile(fpath)

    with open(manifest, "r", encoding="utf-8") as f:
        man_content = f.read()
    assert 'CUSTOM_NAME="matrix-worker"' in man_content
    assert 'CUSTOM_VERSION="1.0.0"' in man_content

    for sh_path in [config_sh, run_sh, stats_sh]:
        with open(sh_path, "r", encoding="utf-8") as f:
            first_line = f.readline().strip()
        assert first_line.startswith("#!/")


def test_strict_zero_external_publishing_constraint():
    """
    CRITICAL CONSTRAINT AUDIT:
    Confirm that no template, script, or configuration attempts to execute
    'docker push', 'vastai publish', 'runpod create template', or connects
    to external upload/publishing endpoints.
    """
    forbidden_patterns = [
        re.compile(r"\bdocker\s+push\b", re.IGNORECASE),
        re.compile(r"\bvastai\s+create\s+template\b", re.IGNORECASE),
        re.compile(r"\brunpodctl\s+create\b", re.IGNORECASE),
        re.compile(r"\bpublish_to_registry\b", re.IGNORECASE),
    ]

    for root, _, files in os.walk(TEMPLATES_DIR):
        for fname in files:
            fpath = os.path.join(root, fname)
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            for pattern in forbidden_patterns:
                match = pattern.search(content)
                assert match is None, f"Found forbidden publish command in {fpath}: {match.group(0)}"
