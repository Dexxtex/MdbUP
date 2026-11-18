"""The API also serves the compiled SPA (single-port deployment)."""

from __future__ import annotations

from pathlib import Path


def test_api_serves_spa_and_falls_back_to_index(client, app_settings, tmp_path: Path) -> None:
    static = tmp_path / "static"
    assets = static / "assets"
    assets.mkdir(parents=True)
    (static / "index.html").write_text("<html><body>MdbUP</body></html>", encoding="utf-8")
    (static / "theme-init.js").write_text("document.documentElement.dataset.theme='dark';")
    (assets / "app.js").write_text("console.log('ok');", encoding="utf-8")
    app_settings.frontend_dist_dir = str(static)

    root = client.get("/")
    assert root.status_code == 200
    assert "MdbUP" in root.text
    assert root.headers["cache-control"] == "no-store"

    deep_link = client.get("/app/runs/123")
    assert deep_link.status_code == 200
    assert "MdbUP" in deep_link.text

    asset = client.get("/assets/app.js")
    assert asset.status_code == 200
    assert "immutable" in asset.headers["cache-control"]

    theme = client.get("/theme-init.js")
    assert theme.status_code == 200
    assert "dataset.theme" in theme.text

    missing_api = client.get("/api/does-not-exist")
    assert missing_api.status_code == 404
    assert missing_api.json()["error"]["code"] == "HTTP_ERROR"
