"""T01: contract and local access boundaries; no model/network required."""
import unittest
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient
from api.main import create_app
from api.settings import Settings


class WebShellTests(unittest.TestCase):
    def setUp(self):
        directory=tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup)
        app = create_app(Settings(data_dir=Path(directory.name).resolve()))

        @app.post("/api/v1/test-mutation")
        async def mutate():
            return {"accepted": True}

        self.client = TestClient(app, base_url="http://127.0.0.1:8001")
        self.addCleanup(self.client.close)

    def test_health_is_live_without_database_or_worker(self):
        response = self.client.get("/api/v1/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["service"], "novel2voice-api")
        self.assertEqual(response.json()["components"], {
            "database": "not_initialized", "worker": "not_started"})
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_rebinding_host_and_wrong_ports_are_rejected(self):
        for host in ("evil.example:8001", "127.0.0.1.evil.example:8001", "127.0.0.1:9001"):
            with self.subTest(host=host):
                response = self.client.get("/api/v1/health", headers={"host": host})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["error"]["code"], "INVALID_HOST")

    def test_only_exact_local_origins_are_accepted(self):
        for origin in ("null", "https://evil.example", "http://localhost:9000", "http://127.0.0.1:8000.evil.example"):
            with self.subTest(origin=origin):
                response = self.client.get("/api/v1/health", headers={"origin": origin})
                self.assertEqual(response.status_code, 403)
                self.assertNotIn("access-control-allow-origin", response.headers)
        for origin in Settings().origins:
            response = self.client.get("/api/v1/health", headers={"origin": origin})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["access-control-allow-origin"], origin)

    def test_mutations_require_local_origin_and_client_header(self):
        for headers in ({}, {"origin": "http://127.0.0.1:8000"}, {"x-novel2voice-client": "web"}):
            response = self.client.post("/api/v1/test-mutation", json={}, headers=headers)
            self.assertEqual(response.status_code, 403)
        valid = {"origin": "http://127.0.0.1:8000", "x-novel2voice-client": "web"}
        self.assertEqual(self.client.post("/api/v1/test-mutation", json={}, headers=valid).status_code, 200)
        self.assertEqual(self.client.post("/api/v1/test-mutation", content="test", headers=valid).status_code, 415)

    def test_preflight_is_scoped_and_never_wildcard(self):
        response = self.client.options("/api/v1/test-mutation", headers={
            "origin": "http://127.0.0.1:8000", "access-control-request-method": "POST",
            "access-control-request-headers": "content-type,x-novel2voice-client"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["access-control-allow-origin"], "http://127.0.0.1:8000")
        self.assertNotIn("access-control-allow-credentials", response.headers)

    def test_unknown_paths_return_safe_error_contract(self):
        response = self.client.get("/.env")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"error": {"code": "NOT_FOUND", "message": "Chức năng hoặc đường dẫn chưa có."}})

    def test_custom_ports_update_boundaries(self):
        with TestClient(create_app(Settings(8100, 8101)), base_url="http://localhost:8101") as client:
            self.assertEqual(client.get("/api/v1/health", headers={"origin": "http://localhost:8100"}).status_code, 200)
            self.assertEqual(client.get("/api/v1/health", headers={"origin": "http://localhost:8000"}).status_code, 403)

    def test_openapi_schema_has_typed_health_response(self):
        response = self.client.get("/openapi.json")
        self.assertEqual(response.status_code, 200)
        schema = response.json()
        health = schema["paths"]["/api/v1/health"]["get"]
        self.assertEqual(health["responses"]["200"]["content"]["application/json"]["schema"],
                         {"$ref": "#/components/schemas/HealthResponse"})
        self.assertIn("version", schema["components"]["schemas"]["HealthResponse"]["properties"])

    def test_swagger_uses_local_assets_and_header_for_try_it_out(self):
        response = self.client.get("/docs")
        if response.status_code == 503:
            self.assertEqual(response.json()["error"]["code"], "DOCS_ASSETS_MISSING")
        else:
            self.assertEqual(response.status_code, 200)
            self.assertIn('/docs-assets/swagger-ui-bundle.js', response.text)
            self.assertNotIn('cdn.jsdelivr.net', response.text)
            self.assertIn('X-Novel2Voice-Client', response.text)
            self.assertEqual(self.client.get('/docs-assets/swagger-ui-bundle.js').status_code, 200)
        # Swagger is served by API, so its same-origin JSON mutations must also work.
        response = self.client.post("/api/v1/test-mutation", json={}, headers={
            "origin": "http://127.0.0.1:8001", "x-novel2voice-client": "web"})
        self.assertEqual(response.status_code, 200)

    def test_sqlmodel_sqlite_stack_without_touching_project_data(self):
        from sqlmodel import SQLModel, Field, Session, create_engine, select

        class T01StackProbe(SQLModel, table=True):
            id: int | None = Field(default=None, primary_key=True)
            name: str

        engine = create_engine("sqlite://")
        try:
            SQLModel.metadata.create_all(engine, tables=[T01StackProbe.__table__])
            with Session(engine) as session:
                session.add(T01StackProbe(name="stack-check"))
                session.commit()
                self.assertEqual(session.exec(select(T01StackProbe)).one().name, "stack-check")
        finally:
            engine.dispose()

    def test_ports_must_be_valid_and_distinct(self):
        for ports in ((8000, 8000), (0, 8001), (8000, 65536)):
            with self.subTest(ports=ports), self.assertRaises(ValueError):
                Settings(*ports)


if __name__ == "__main__":
    unittest.main()
