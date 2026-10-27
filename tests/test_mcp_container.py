"""Tests for `matrix-dockerimages/mcp/` container definition and Compose integration."""

from pathlib import Path


DOCKERIMAGES_ROOT = Path(__file__).resolve().parent.parent


def test_mcp_dockerfile_structure_and_security():
    dockerfile_path = DOCKERIMAGES_ROOT / "mcp" / "Dockerfile"
    assert dockerfile_path.exists(), "mcp/Dockerfile must exist"

    content = dockerfile_path.read_text(encoding="utf-8")
    assert "FROM python:3.11-slim as builder" in content
    assert "FROM python:3.11-slim as runtime" in content
    assert "COPY matrix-contracts /build/matrix-contracts" in content
    assert "COPY matrix-compute-sdk /build/matrix-compute-sdk" in content
    assert "COPY matrix-compute-mcp /build/matrix-compute-mcp" in content
    assert "USER matrixuser" in content
    assert 'ENTRYPOINT ["matrix-compute-mcp"]' in content


def test_mcp_dockerignore_and_readme():
    dockerignore_path = DOCKERIMAGES_ROOT / "mcp" / ".dockerignore"
    readme_path = DOCKERIMAGES_ROOT / "mcp" / "README.md"

    assert dockerignore_path.exists()
    assert readme_path.exists()

    readme_text = readme_path.read_text(encoding="utf-8")
    assert "matrix-compute-mcp:latest" in readme_text
    assert "mcpServers" in readme_text


def test_docker_compose_includes_mcp_service():
    compose_path = DOCKERIMAGES_ROOT / "docker-compose.yml"
    compose_text = compose_path.read_text(encoding="utf-8")

    assert "dockerfile: matrix-dockerimages/mcp/Dockerfile" in compose_text
    assert "image: matrix-compute-mcp:latest" in compose_text
    assert "container_name: matrix-compute-mcp" in compose_text
    assert "MATRIX_L402_MACAROON" in compose_text
