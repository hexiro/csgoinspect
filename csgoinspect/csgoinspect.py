from __future__ import annotations

import asyncio
import typing as t

import tweepy
from loguru import logger

from csgoinspect import redis_, swapgg, twitter
from csgoinspect.commons import (
    INSPECT_LINK_QUERY,
    INSPECT_URL_REGEX,
    LIVE_RULES,
    TWEET_EXPANSIONS,
    TWEET_TWEET_FIELDS,
    TWEET_USER_FIELDS,
)
from csgoinspect.item import Item
from csgoinspect.tweet import TweetWithItems

if t.TYPE_CHECKING:
    import re


class CSGOInspect:
    def __init__(self) -> None:
        self.swap_gg = swapgg.SwapGG()
        self.twitter = twitter.Twitter()
        self.twitter.live.on_tweet = self.on_tweet

    async def on_tweet(self, tweet: tweepy.Tweet) -> None:
        tweet_with_items = await self._parse_tweet_inspect_links(tweet)
        if not tweet_with_items:
            return
        coro = self.process_tweet(tweet_with_items)
        asyncio.create_task(coro)

    async def find_tweets(self) -> list[TweetWithItems]:
        search_results: tweepy.Response = await self.twitter.v2.search_recent_tweets(
            query=INSPECT_LINK_QUERY,
            expansions=TWEET_EXPANSIONS,
            tweet_fields=TWEET_TWEET_FIELDS,
            user_fields=TWEET_USER_FIELDS,
        )  # type: ignore
        tweets: list[tweepy.Tweet] = search_results.data
        items_tweets: list[TweetWithItems] = []
        for tweet in tweets:
            tweet_with_items = await self._parse_tweet_inspect_links(tweet)
            if not tweet_with_items:
                continue
            items_tweets.append(tweet_with_items)
        return items_tweets

    async def run(self) -> None:
        await self.swap_gg.connect()

        async def incrementally_find_tweets() -> None:
            logger.debug("STARTING: INCREMENTALLY FIND TWEETS")
            while True:
                try:
                    items_tweets = await self.find_tweets()
                    await self.process_tweets(items_tweets)
                except Exception:
                    logger.exception("Error finding tweets")
                await asyncio.sleep(600)

        task_one = asyncio.create_task(incrementally_find_tweets())

        await self.twitter.live.add_rules(LIVE_RULES)

        logger.debug("STARTING: LIVE TWEETS")

        task_two = self.twitter.live.filter(
            expansions=TWEET_EXPANSIONS, tweet_fields=TWEET_TWEET_FIELDS, user_fields=TWEET_USER_FIELDS
        )

        await asyncio.gather(task_one, task_two)

    async def process_tweet(self, tweet: TweetWithItems) -> None:
        logger.info(f"PROCESSING TWEET: {tweet.url}")
        await self.swap_gg.screenshot_tweet(tweet)

        logger.info(f"REPLYING TO TWEET: {tweet.url}")
        logger.debug(f"{tweet.items=}")
        await self.twitter.reply(tweet)
        await redis_.mark_responded(tweet)

    async def process_tweets(self, tweets: t.Iterable[TweetWithItems]) -> None:
        for tweet in tweets:
            coro = self.process_tweet(tweet)
            asyncio.create_task(coro)

    async def _parse_tweet_inspect_links(self, tweet: tweepy.Tweet) -> TweetWithItems | None:
        # Twitter only allows 4 images
        matches: list[re.Match] = list(INSPECT_URL_REGEX.finditer(tweet.text))
        matches = matches[:4]

        if not matches:
            logger.debug(f"SKIPPING TWEET: {tweet.id} (No Inspect Links)")
            return None

        if tweet.attachments:  # potentially already has screenshot
            logger.debug(f"SKIPPING TWEET: {tweet.id} (Has Attachments)")
            return None

        items = tuple(Item(inspect_link=match.group()) for match in matches)
        tweet_with_items = TweetWithItems(items, tweet)

        if await redis_.has_responded(tweet_with_items):
            logger.debug(f"SKIPPING TWEET: {tweet.id} (Already Responded)")
            return None

        return tweet_with_items