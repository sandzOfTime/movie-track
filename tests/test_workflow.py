from datetime import datetime, timedelta, timezone
import httpx
from fastapi.testclient import TestClient
import pytest
from movie_track.db import Database
from movie_track.models import Showtime, AlertRequest, ImportRequest, Listings
from movie_track.alerts import alert
from movie_track.ingest import ingest, download
from movie_track.api import app


def show(**changes):
    values = dict(movie="Dune", cinema="Fusion Superplex", theater_type="IMAX",
                  starts_at=datetime.now(timezone.utc) + timedelta(days=1))
    return Showtime(**(values | changes))


def request(**changes):
    return AlertRequest(**(dict(movie=" dune ", theater_type="imax", channel="email",
                               recipient="person@example.com", dry_run=False) | changes))


def test_matching_and_delivery_idempotency(tmp_path):
    db = Database(str(tmp_path / "db.sqlite"))
    db.save("https://cinema.example/", [], [show(), show(theater_type="4DX"),
            show(movie="Other"), show(starts_at=datetime.now(timezone.utc) - timedelta(days=1))])
    deliveries = []
    sender = lambda *args: deliveries.append(args)
    assert alert(db, request(dry_run=True), sender)["sent"] == 0
    assert not deliveries
    assert alert(db, request(cinema="Elsewhere"), sender)["matches"] == []
    assert alert(db, request(), sender)["sent"] == 1
    assert alert(db, request(), sender)["already_sent"] == 1
    assert len(deliveries) == 1


def test_failed_delivery_can_retry(tmp_path):
    db = Database(str(tmp_path / "db.sqlite"))
    db.save("source", [], [show()])
    def fail(*args):
        raise RuntimeError("transport failed")
    with pytest.raises(RuntimeError):
        alert(db, request(), fail)
    assert alert(db, request(), lambda *args: None)["sent"] == 1


def test_latest_snapshot_replaces_source_not_other_sources(tmp_path):
    db = Database(str(tmp_path / "db.sqlite"))
    db.save("a", [], [show()])
    db.save("b", [], [show(movie="Other")])
    db.save("a", [], [show(movie="New")])
    assert {s["movie"] for s in db.latest()} == {"New", "Other"}


def test_import_downloads_image_and_persists(tmp_path, monkeypatch):
    import io
    from PIL import Image
    import movie_track.ingest as module
    image = io.BytesIO()
    Image.new("RGB", (20, 20)).save(image, format="PNG")
    def route(req):
        return httpx.Response(200, content=image.getvalue() if req.url.path == "/poster.png"
                              else b'<img src="/poster.png">')
    original = httpx.Client
    monkeypatch.setattr(module.httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(route), **kw))
    monkeypatch.setenv("LISTING_ALLOWED_HOSTS", "cinema.example")
    monkeypatch.setenv("MOVIE_TRACK_DATA", str(tmp_path))
    db = Database(str(tmp_path / "db.sqlite"))
    payload = ImportRequest(source_url="https://cinema.example/")
    result = ingest(db, payload, extractor=lambda images, req: Listings(showtimes=[show()]))
    assert result["extracted_showtimes"] == 1
    assert len(db.latest()) == 1
    with pytest.raises(ValueError, match="previous snapshot retained"):
        ingest(db, payload, extractor=lambda images, req: Listings(showtimes=[]))
    assert len(db.latest()) == 1


def test_redirect_to_unapproved_host_is_blocked(monkeypatch):
    monkeypatch.setenv("LISTING_ALLOWED_HOSTS", "cinema.example")
    with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(
            302, headers={"location": "https://other.example/image"}))) as client:
        with pytest.raises(ValueError, match="LISTING_ALLOWED_HOSTS"):
            download(client, "https://cinema.example/")


def test_api_auth_and_listing(tmp_path, monkeypatch):
    monkeypatch.setenv("MOVIE_TRACK_DATA", str(tmp_path))
    monkeypatch.setenv("MOVIE_TRACK_API_TOKEN", "test-token")
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/listings").status_code == 401
        assert client.get("/listings", headers={"Authorization": "Bearer test-token"}).json() == []


def test_vision_uses_structured_output(monkeypatch):
    import io
    import json
    from PIL import Image
    from openai import OpenAI
    import movie_track.ingest as module
    payload = Listings(showtimes=[show()]).model_dump_json()
    def route(req):
        body = json.loads(req.content)
        schema = body["response_format"]["json_schema"]["schema"]
        assert schema["$defs"]["MovieMetadata"]["additionalProperties"] is False
        assert body["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")
        return httpx.Response(200, json={"id": "fixture", "object": "chat.completion", "created": 0,
            "model": "fixture", "choices": [{"index": 0, "finish_reason": "stop",
                "message": {"role": "assistant", "content": payload}}]})
    client = OpenAI(api_key="fixture", http_client=httpx.Client(transport=httpx.MockTransport(route)))
    monkeypatch.setattr(module, "OpenAI", lambda **kwargs: client)
    image = io.BytesIO()
    Image.new("RGB", (20, 20)).save(image, format="PNG")
    result = module.extract([image.getvalue()], ImportRequest(source_url="https://cinema.example/"))
    assert result.showtimes[0].movie == "Dune"
    client.close()


def test_resend_email_transport(monkeypatch):
    import json
    import movie_track.alerts as module
    monkeypatch.setenv("RESEND_API_KEY", "fixture-key")
    monkeypatch.setenv("EMAIL_FROM", "cinema@example.com")
    monkeypatch.setenv("EMAIL_PROVIDER", "resend")
    seen = []
    def route(req):
        assert str(req.url) == "https://api.resend.com/emails"
        payload = json.loads(req.content)
        assert payload["to"] == ["person@example.com"]
        assert payload["text"] == "Movie at 19:00"
        seen.append(payload)
        return httpx.Response(200, json={"id": "fixture"})
    original = httpx.Client
    monkeypatch.setattr(module.httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(route), **kw))
    module.send("email", "person@example.com", "Movie at 19:00")
    assert len(seen) == 1


def test_delivery_deduplicated_after_reimport(tmp_path):
    db = Database(str(tmp_path / "db.sqlite"))
    first = show()
    db.save("source", [], [first])
    assert alert(db, request(), lambda *args: None)["sent"] == 1
    db.save("source", [], [first.model_copy(update={"movie": " DUNE ", "theater_type": " imax "})])
    assert alert(db, request(), lambda *args: None)["already_sent"] == 1
