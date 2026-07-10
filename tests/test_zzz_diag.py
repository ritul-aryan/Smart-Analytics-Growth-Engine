import pytest

async def test_diag(async_client):
    r = await async_client.get("/health")
    print("URL:", r.request.url, "STATUS:", r.status_code, "BODY:", r.text)
    from backend.main import app
    print("APP ID in test:", id(app))
