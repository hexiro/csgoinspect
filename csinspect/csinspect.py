from __future__ import annotations

import asyncio
import typing as t

import tweepy
import tweepy.errors
from loguru import logger

from csinspect import redis_, screenshot, twitter
from csinspect.config import (
    DEV_DONT_SEND_TWEETS,
    DEV_ID,
    ENABLE_TWITTER_LIVE,
    ENABLE_TWITTER_SEARCH,
    TWEET_SEARCH_DELAY,
    TWITTER_INSPECT_LINK_QUERY,
    TWITTER_INSPECT_URL_REGEX,
    IS_DEV,
    TWITTER_LIVE_RULES,
    TWEET_MAX_FAILED_ATTEMPTS,
    ONLY_RESPOND_TO_DEV,
    TWEET_EXPANSIONS,
    TWEET_TWEET_FIELDS,
    TWEET_USER_FIELDS,
    TWEET_MAX_IMAGES,
)
from csinspect.item import Item
from csinspect.tweet import TweetWithInspectLink

if t.TYPE_CHECKING:
    import re


class CSInspect:
    def __init__(self: CSInspect) -> None:
        self.screenshot = screenshot.Screenshot()
        self.twitter = twitter.Twitter(on_tweet=self.on_tweet)

    async def on_tweet(self: CSInspect, tweet: tweepy.Tweet) -> None:
        tweet_with_items = await self.parse_tweet(tweet)
        if not tweet_with_items:
            return
        task_set: set[asyncio.Task[None]] = set()
        coro = self.process_tweet(tweet_with_items)
        task = asyncio.create_task(coro)
        task_set.add(task)
        task.add_done_callback(task_set.discard)

    async def find_tweets(self: CSInspect) -> list[TweetWithInspectLink]:
        search_results: tweepy.Response = await self.twitter.v2.search_recent_tweets(
            query=TWITTER_INSPECT_LINK_QUERY,
            expansions=TWEET_EXPANSIONS,
            tweet_fields=TWEET_TWEET_FIELDS,
            user_fields=TWEET_USER_FIELDS,
        )  # type: ignore
        tweets: list[tweepy.Tweet] = search_results.data
        items_tweets: list[TweetWithInspectLink] = []
        for tweet in tweets:
            tweet_with_items = await self.parse_tweet(tweet)
            if not tweet_with_items:
                continue
            items_tweets.append(tweet_with_items)
        return items_tweets

    async def run(self: CSInspect) -> None:
        running_search_task = await self.search_task()
        running_live_task = await self.live_task()
        tasks = filter(None, (running_search_task, running_live_task))
        await asyncio.gather(*tasks)

    async def search_task(self) -> asyncio.Task | None:
        if not ENABLE_TWITTER_SEARCH:
            logger.debug("NOT STARTING: SEARCH TWEETS")
            return None

        async def find_and_process_tweets() -> None:
            logger.info(f"FINDING TWEETS (Past {TWEET_SEARCH_DELAY} Seconds)")

            try:
                items_tweets = await self.find_tweets()
                await self.process_tweets(items_tweets)
            except Exception:
                logger.exception("Error Finding or Processing Tweets")

            logger.info(f"DONE FINDING TWEETS (Past {TWEET_SEARCH_DELAY} Seconds)")

        async def incrementally_find_and_process_tweets() -> None:
            logger.debug("STARTING: SEARCH TWEETS")
            while True:
                await find_and_process_tweets()
                await asyncio.sleep(TWEET_SEARCH_DELAY)

        coro = incrementally_find_and_process_tweets()
        task = asyncio.create_task(coro)
        return task

    async def live_task(self) -> asyncio.Task | None:
        if not ENABLE_TWITTER_LIVE or self.twitter.live is None:
            logger.debug("NOT STARTING: LIVE TWEETS")
            return None

        logger.debug("STARTING: LIVE TWEETS")
        await self.twitter.live.add_rules(TWITTER_LIVE_RULES)
        task = await self.twitter.live.filter(
            expansions=TWEET_EXPANSIONS, tweet_fields=TWEET_TWEET_FIELDS, user_fields=TWEET_USER_FIELDS
        )
        return task

    async def process_tweet(self: CSInspect, tweet: TweetWithInspectLink) -> None:
        logger.info(f"PROCESSING TWEET: {tweet.url}")

        screenshot_responses = await self.screenshot.screenshot_items(tweet.items)

        logger.debug(f"SCREENSHOT RESPONSES: {screenshot_responses}")

        if not any(screenshot_responses):
            logger.info(f"SKIPPING TWEET (Failed To Generate Screenshots): {tweet.url}")

            await redis_.update_tweet_state(tweet, successful=False)
            return

        logger.info(f"REPLYING TO TWEET: {tweet.url}")
        logger.debug(f"{tweet.items=}")

        if DEV_DONT_SEND_TWEETS:
            logger.info("SKIPPING TWEET (DEV_DONT_SEND_TWEETS IS ENABLED)")
            return

        try:
            await self.twitter.reply(tweet)
        except tweepy.errors.HTTPException as exc:
            logger.warning(f"ERROR REPLYING: {tweet.url} - {exc}")
            await redis_.update_tweet_state(tweet, successful=False)
        else:
            logger.success(f"REPLIED TO TWEET: {tweet.url}")
            await redis_.update_tweet_state(tweet, successful=True)

    async def process_tweets(self: CSInspect, tweets: t.Iterable[TweetWithInspectLink]) -> None:
        task_set: set[asyncio.Task[None]] = set()
        for tweet in tweets:
            coro = self.process_tweet(tweet)
            task = asyncio.create_task(coro)
            task_set.add(task)
            task.add_done_callback(task_set.discard)

    async def parse_tweet(self: CSInspect, tweet: tweepy.Tweet) -> TweetWithInspectLink | None:
        matches: list[re.Match] = list(TWITTER_INSPECT_URL_REGEX.finditer(tweet.text))
        matches = matches[:TWEET_MAX_IMAGES]

        if not matches:
            logger.info(f"SKIPPING TWEET (No Inspect Links): {tweet.id} ")
            return None

        if DEV_ID:
            if IS_DEV and ONLY_RESPOND_TO_DEV and tweet.author_id != DEV_ID:
                logger.info(f"SKIPPING TWEET (Dev Mode Enabled & Not Dev): {tweet.id}, {tweet.author_id} ")
                return None
            if not IS_DEV and tweet.author_id == DEV_ID:
                logger.info(f"SKIPPING TWEET (Dev Mode Disabled & Dev): {tweet.id}, {tweet.author_id} ")
                return None

        items = tuple(Item(inspect_link=match.group()) for match in matches)

        tweet_with_items = TweetWithInspectLink(items, tweet)
        tweet_state = await redis_.tweet_state(tweet_with_items)

        if not tweet_state:
            return tweet_with_items

        if tweet_state.failed_attempts > TWEET_MAX_FAILED_ATTEMPTS:
            logger.info(f"SKIPPING TWEET (Too Many Failed Attempts): {tweet.id}")
            return None

        if tweet_state.successful:
            logger.info(f"SKIPPING TWEET (Already Successfully Responded): {tweet.id}")
            return None

        return tweet_with_items
