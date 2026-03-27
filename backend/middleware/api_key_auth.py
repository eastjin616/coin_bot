from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

SKIP_PATHS = {"/", "/docs", "/openapi.json", "/redoc"}

class APIKeyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, api_key: str):
        super().__init__(app)
        self.api_key = api_key

    async def dispatch(self, request: Request, call_next):
        if request.url.path in SKIP_PATHS or not self.api_key:
            return await call_next(request)
        key = request.headers.get("X-API-Key", "")
        if key != self.api_key:
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        return await call_next(request)
