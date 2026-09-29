"""Regression test for the 2026-09-29 403 incident.

The image was built from a checkout made under umask 027, COPY preserved the 0640/0750
modes, and nginx (worker user www-data) returned 403 for / and every static asset.
The Dockerfile must make /app/frontend world-readable after copying it.
"""
from pathlib import Path
import re

DOCKERFILE = Path(__file__).resolve().parents[2] / "abct-docker" / "Dockerfile"


def _instructions():
    lines = DOCKERFILE.read_text().splitlines()
    return [l.strip() for l in lines if l.strip() and not l.strip().startswith("#")]


def test_frontend_made_world_readable_after_copy():
    ins = _instructions()
    copy_idx = next(i for i, l in enumerate(ins) if re.match(r"COPY\s+frontend/\s+/app/frontend/?$", l))
    chmod_ok = any(
        re.search(r"chmod\s+-R\s+a\+rX\s+/app/frontend\b", l) for l in ins[copy_idx + 1:] if l.startswith("RUN")
    ) or re.search(r"--chmod=", ins[copy_idx])
    assert chmod_ok, "frontend must be readable by nginx's www-data regardless of build-context umask"


def test_nginx_worker_user_still_needs_this():
    # If nginx ever runs workers as root this test documents why the chmod exists; keep them paired.
    conf = (DOCKERFILE.parent / "nginx.conf").read_text()
    assert "root /app/frontend;" in conf
