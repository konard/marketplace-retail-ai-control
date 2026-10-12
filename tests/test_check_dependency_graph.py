"""Tests for scripts/check-dependency-graph.sh.

Dependency review fails every pull request when the repository's Dependency
graph is disabled. The probe is exercised against a local fake of GitHub's SBOM
endpoint so each answer -- enabled, disabled, unknown -- maps to the right
`enabled` output without touching the real API.
"""

from __future__ import annotations

import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from tests.workflow_helpers import read_workflow, workflow_job_block

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "check-dependency-graph.sh"
REPOSITORY = "example/repo"


class FakeGitHubApi:
    """A scriptable fake of GET /repos/{repo}/dependency-graph/sbom."""

    def __init__(self) -> None:
        self.status = 200
        self.paths: list[str] = []
        self.authorizations: list[str | None] = []
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._build_handler())
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def url(self) -> str:
        host, port = self._server.server_address
        return f"http://{host}:{port}"

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def _build_handler(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args) -> None:
                pass

            def do_GET(self) -> None:  # noqa: N802
                fake.paths.append(self.path)
                fake.authorizations.append(self.headers.get("Authorization"))
                body = b"{}"
                self.send_response(fake.status)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return Handler


@pytest.fixture()
def fake_api():
    fake = FakeGitHubApi()
    yield fake
    fake.stop()


def run_script(
    tmp_path: Path, env: dict[str, str]
) -> tuple[subprocess.CompletedProcess[str], str, str]:
    output = tmp_path / "github_output"
    summary = tmp_path / "step_summary"
    output.touch()
    summary.touch()
    merged_env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"GH_TOKEN", "GITHUB_REPOSITORY"}
    }
    merged_env.update(
        {
            "REPOSITORY": REPOSITORY,
            "GITHUB_OUTPUT": str(output),
            "GITHUB_STEP_SUMMARY": str(summary),
            "DEPENDENCY_GRAPH_CURL_TIMEOUT": "5",
            **env,
        }
    )
    result = subprocess.run(
        ["bash", str(SCRIPT_PATH)],
        cwd=ROOT,
        env=merged_env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return (
        result,
        output.read_text(encoding="utf-8"),
        summary.read_text(encoding="utf-8"),
    )


def test_enabled_dependency_graph_runs_the_review(fake_api, tmp_path) -> None:
    result, output, summary = run_script(
        tmp_path, {"GITHUB_API_URL": fake_api.url, "GH_TOKEN": "fake-token"}
    )

    assert result.returncode == 0, result.stderr
    assert output == "enabled=true\n"
    assert summary == ""
    assert fake_api.paths == [f"/repos/{REPOSITORY}/dependency-graph/sbom"]
    assert fake_api.authorizations == ["Bearer fake-token"]


def test_disabled_dependency_graph_skips_the_review_with_a_warning(
    fake_api, tmp_path
) -> None:
    """The failure this guards against: PR #2's 'Dependency review is not
    supported on this repository' when the repository setting is off."""
    fake_api.status = 404

    result, output, summary = run_script(tmp_path, {"GITHUB_API_URL": fake_api.url})

    assert result.returncode == 0, result.stderr
    assert output == "enabled=false\n"
    settings = f"https://github.com/{REPOSITORY}/settings/security_analysis"
    assert "::warning title=Dependency review skipped::" in result.stdout
    assert settings in result.stdout
    assert settings in summary


@pytest.mark.parametrize("status", [403, 429, 500])
def test_unknown_probe_answers_still_run_the_review(fake_api, tmp_path, status) -> None:
    fake_api.status = status

    result, output, _ = run_script(tmp_path, {"GITHUB_API_URL": fake_api.url})

    assert result.returncode == 0, result.stderr
    assert output == "enabled=true\n"
    assert "::warning" not in result.stdout


def test_unreachable_api_still_runs_the_review(tmp_path) -> None:
    result, output, _ = run_script(tmp_path, {"GITHUB_API_URL": "http://127.0.0.1:9"})

    assert result.returncode == 0, result.stderr
    assert output == "enabled=true\n"


def test_missing_repository_is_a_usage_error(tmp_path) -> None:
    result, output, _ = run_script(tmp_path, {"REPOSITORY": ""})

    assert result.returncode == 2
    assert output == ""


def test_security_workflow_gates_the_review_on_the_probe() -> None:
    job = workflow_job_block(read_workflow("security.yml"), "dependency-review")

    probe = job.index("run: bash scripts/check-dependency-graph.sh")
    review = job.index("uses: actions/dependency-review-action@v5")
    assert probe < review
    assert "id: dependency-graph" in job
    assert "GH_TOKEN: ${{ github.token }}" in job
    assert "REPOSITORY: ${{ github.repository }}" in job
    assert "if: steps.dependency-graph.outputs.enabled == 'true'" in job
