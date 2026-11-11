import asyncio
import os
from uuid import uuid4
import pytest
from redis.asyncio import Redis
from app.core.config import settings
from app.middleware import RequestControlsMiddleware

@pytest.mark.skipif(not os.getenv('TEST_REDIS_URL'), reason='Set TEST_REDIS_URL to disposable Redis')
def test_rate_limit_is_shared_between_process_instances_and_expires(monkeypatch):
    monkeypatch.setattr(settings,'rate_limit_redis_url',os.environ['TEST_REDIS_URL'])
    async def scenario():
        first, second = RequestControlsMiddleware(None), RequestControlsMiddleware(None)
        key = ('test',str(uuid4()))
        try:
            assert await first._limit(key,2) is None
            assert await second._limit(key,2) is None
            retry = await first._limit(key,2)
            assert 1 <= retry <= 60
        finally:
            for item in (first,second):
                if item._redis: await item._redis.aclose()
    asyncio.run(scenario())
