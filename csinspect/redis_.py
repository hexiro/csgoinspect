"""A wrapper around redis for cache database interactions"""

from __future__ import annotations

import json
import typing as t
from datetime import datetime
from functools import lru_cache

from loguru import logger
from redis.asyncio import Redis

from csinspect.config import REDIS_DATABASE, REDIS_EX, REDIS_HOST, REDIS_PASSWORD, REDIS_PORT
from csinspect.typings import TweetResponseState

if t.TYPE_CHECKING:
    from csinspect.tweet import TweetWithInspectLink
    from csinspect.typings import TweetResponseRawData


@lru_cache(maxsize=None)
def get_redis() -> Redis[str]:
    return Redis(host=REDIS_HOST, password=REDIS_PASSWORD, port=REDIS_PORT, db=REDIS_DATABASE, decode_responses=True)


async def tweet_state(tweet: TweetWithInspectLink) -> TweetResponseState | None:
    redis_ = get_redis()

    key = f"tweet:{tweet.id}"
    tweet_value = await redis_.get(key)

    if not tweet_value:
        return None

    data: TweetResponseRawData = json.loads(tweet_value)
    return TweetResponseState(successful=data["successful"], failed_attempts=data.get("failed_attempts", 0))


async def update_tweet_state(tweet: TweetWithInspectLink, *, successful: bool) -> None:
    redis_ = get_redis()

    logger.debug(f"STORING TWEET: {tweet.url}")

    data: TweetResponseRawData = {"successful": successful, "time": datetime.now().isoformat()}

    if not successful:
        state = await tweet_state(tweet)
        if state:
            data["failed_attempts"] = state.failed_attempts + 1

    await redis_.set(name=f"tweet:{tweet.id}", value=json.dumps(data), ex=REDIS_EX)
