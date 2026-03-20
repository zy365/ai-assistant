import httpx
from config import settings


class JavaClient:
    """统一封装对内部 Java 微服务的 HTTP 调用"""

    def __init__(self):
        self._base_url = settings.java_base_url
        self._timeout = httpx.Timeout(10.0, read=30.0)

    async def get(self, path: str, params: dict | None = None) -> dict:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(
                f"{self._base_url}{path}", params=params or {}
            )
            resp.raise_for_status()
            return resp.json()

    async def post(self, path: str, body: dict | None = None) -> dict:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base_url}{path}", json=body or {}
            )
            resp.raise_for_status()
            return resp.json()

    async def verify_token(self, token: str) -> dict:
        """调用 Java 权限服务验证 JWT，返回用户信息 + 权限列表"""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{settings.java_auth_url}/api/auth/verify",
                json={"token": token},
            )
            resp.raise_for_status()
            return resp.json()


java_client = JavaClient()
