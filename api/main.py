"""Local API with opt-in offline verification; no production model is loaded."""
import argparse
from pathlib import Path
from typing import Literal
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.exceptions import HTTPException

from api.settings import Settings
from src import __version__


class ComponentsStatus(BaseModel):
    database: Literal["not_initialized", "ready"] = "not_initialized"
    worker: Literal["not_started", "ready"] = "not_started"


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["novel2voice-api"] = "novel2voice-api"
    version: str
    scope: Literal["T27"] = "T27"
    verification_mode: bool = False
    components: ComponentsStatus = ComponentsStatus()


def error_response(status, code, message):
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def create_app(settings=None):
    settings = settings or Settings()
    @asynccontextmanager
    async def lifespan(app):
        yield
        repository = getattr(app.state, 'repository', None)
        if repository is not None:
            repository.engine.dispose()

    app = FastAPI(lifespan=lifespan, title="novel2voice API", version=__version__, docs_url=None,
                  redoc_url=None, openapi_url="/openapi.json")
    app.add_middleware(CORSMiddleware, allow_origins=settings.origins,
                       allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
                       allow_headers=["Content-Type", "X-Novel2Voice-Client"],
                       allow_credentials=False)

    @app.middleware("http")
    async def local_boundary(request: Request, call_next):
        if request.headers.get("host", "").lower() not in settings.api_hosts:
            return error_response(400, "INVALID_HOST", "Host không được phép.")
        origin = request.headers.get("origin")
        if origin is not None and origin not in settings.trusted_origins:
            return error_response(403, "INVALID_ORIGIN", "Nguồn truy cập không được phép.")
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            if origin not in settings.trusted_origins or request.headers.get("x-novel2voice-client") != "web":
                return error_response(403, "LOCAL_CLIENT_REQUIRED", "Thao tác phải đến từ ứng dụng local.")
            if request.headers.get("content-type", "").split(";", 1)[0].strip() != "application/json":
                return error_response(415, "JSON_REQUIRED", "Yêu cầu nội dung JSON.")
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 8 * 1024 * 1024:
                    return error_response(413, "BODY_TOO_LARGE", "Nội dung yêu cầu vượt quá 8 MiB.")
            request._body = bytes(body)
        from api.maintenance import gate
        from api.books import BookError
        from api.verification.workspace import PROJECT_ROOT
        root=settings.data_dir or PROJECT_ROOT/('.verification/web' if settings.verification_enabled else '.novel2voice')
        try:
            with gate(root):response = await call_next(request)
        except BookError as exc:
            return error_response(exc.status,'MAINTENANCE',str(exc))
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        labels = {404: ("NOT_FOUND", "Chức năng hoặc đường dẫn chưa có."),
                  405: ("METHOD_NOT_ALLOWED", "Phương thức không được hỗ trợ.")}
        code, message = labels.get(exc.status_code, ("REQUEST_FAILED", "Không thể thực hiện yêu cầu."))
        if exc.status_code in {409, 413, 422, 403} and isinstance(exc.detail, str):
            code, message = {409:"CONFLICT",413:"PAYLOAD_TOO_LARGE",422:"INVALID_REQUEST",403:"FORBIDDEN"}[exc.status_code], str(exc.detail)
        return error_response(exc.status_code, code, message)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return error_response(422, "INVALID_REQUEST", "Dữ liệu gửi lên không hợp lệ.")

    @app.exception_handler(Exception)
    async def unexpected_error(request, exc):
        return error_response(500, "INTERNAL_ERROR", "Có lỗi phía máy chủ. Kiểm tra nhật ký API.")

    swagger_assets = Path(__file__).resolve().parent.parent / "app" / "node_modules" / "swagger-ui-dist"
    if swagger_assets.is_dir():
        app.mount("/docs-assets", StaticFiles(directory=swagger_assets), name="swagger-assets")

    @app.get("/docs", include_in_schema=False)
    async def swagger_docs():
        if not swagger_assets.is_dir():
            return error_response(503, "DOCS_ASSETS_MISSING", "Cài pnpm --dir app install --frozen-lockfile để mở Swagger UI.")
        html = get_swagger_ui_html(
            openapi_url="/openapi.json", title="novel2voice API — Swagger UI",
            swagger_js_url="/docs-assets/swagger-ui-bundle.js",
            swagger_css_url="/docs-assets/swagger-ui.css",
            swagger_favicon_url="/docs-assets/favicon-32x32.png",
            swagger_ui_parameters={"validatorUrl": None, "persistAuthorization": False},
        )
        return HTMLResponse(html.body.decode().replace(
            "SwaggerUIBundle({",
            'SwaggerUIBundle({requestInterceptor: (request) => { request.headers["X-Novel2Voice-Client"] = "web"; return request; },',
        ))

    from api.books import create_router as books_router, RepositoryProvider
    repository_provider = RepositoryProvider(settings)
    app.include_router(books_router(settings, repository_provider))
    from api.jobs import create_router as jobs_router
    app.include_router(jobs_router(settings, repository_provider))
    from api.overview import create_router as overview_router
    app.include_router(overview_router(settings, repository_provider))
    from api.job_plans import create_router as plans_router
    app.include_router(plans_router(settings, repository_provider))

    from api.environment import create_router as environment_router
    app.include_router(environment_router(settings.verification_enabled))

    if settings.verification_enabled:
        from api.verification.routes import create_router
        from api.verification import WorkspaceError

        @app.exception_handler(WorkspaceError)
        async def workspace_error(request, exc):
            return error_response(exc.status, exc.code, str(exc))

        app.include_router(create_router())

    @app.get("/api/v1/health", response_model=HealthResponse, tags=["Infrastructure"])
    async def health() -> HealthResponse:
        import time, json
        from api.verification.workspace import PROJECT_ROOT
        root = settings.data_dir or PROJECT_ROOT / ('.verification/web' if settings.verification_enabled else '.novel2voice')
        worker_status = 'not_started'
        heartbeat = root / 'worker-heartbeat.json'
        if heartbeat.is_file() and not heartbeat.is_symlink() and heartbeat.stat().st_size < 1024:
            try:
                if 0 <= time.time() - json.loads(heartbeat.read_text())['updated_at'] < 5:
                    worker_status = 'ready'
            except (ValueError, KeyError, TypeError, OSError):
                pass
        return HealthResponse(version=__version__, verification_mode=settings.verification_enabled,
                              components=ComponentsStatus(database="ready" if getattr(app.state, "repository", None) is not None else "not_initialized", worker=worker_status))

    return app


def main():
    parser = argparse.ArgumentParser(description="Chạy riêng API local novel2voice.")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--app-port", type=int, default=8000)
    parser.add_argument("--verification", action="store_true", help="Bật API kiểm thử offline, không dùng kho truyện thật.")
    parser.add_argument("--data-dir", type=Path, help="Kho thư viện riêng, ví dụ bản restore mới.")
    args = parser.parse_args()
    settings = Settings(app_port=args.app_port, api_port=args.port, verification_enabled=args.verification, data_dir=args.data_dir.resolve() if args.data_dir else None)
    import uvicorn
    uvicorn.run(create_app(settings), host="127.0.0.1", port=settings.api_port,
                proxy_headers=False, server_header=False, access_log=False)


if __name__ == "__main__":
    main()
