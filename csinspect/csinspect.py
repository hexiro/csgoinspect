from __future__ import annotations

import asyncio
import typing as t

import tweepy
import tweepy.errors
from loguru import logger

from csinspect import redis_, screenshot, twitter
from csinspect.config import (
    DEV_ID,
    DEV_MODE,
    ENABLE_TWITTER_LIVE,
    ENABLE_TWITTER_SEARCH,
    SILENT_MODE,
    TWEET_EXPANSIONS,
    TWEET_MAX_FAILED_ATTEMPTS,
    TWEET_MAX_IMAGES,
    TWEET_SEARCH_DELAY,
    TWEET_TWEET_FIELDS,
    TWEET_USER_FIELDS,
    TWITTER_INSPECT_LINK_QUERY,
    TWITTER_INSPECT_URL_REGEX,
    TWITTER_INSPECT_URL_TEMPLATE,
    TWITTER_LIVE_RULES,
)
from csinspect.item import Item
from csinspect.tweet import TweetWithInspectLink

if t.TYPE_CHECKING:
    import re


class CSInspect:
    def __init__(self: CSInspect) -> None:
        self.screenshot = screenshot.Screenshot()
        self.twitter = twitter.Twitter(on_tweet=self.on_tweet)
        self.lock = asyncio.Semaphore(value=3)

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
            max_results=50,
        )  # type: ignore

        tweets: list[tweepy.Tweet] = search_results.data or []
        tasks: list[asyncio.Task[TweetWithInspectLink | None]] = []

        for tweet in tweets:
            coro = self.parse_tweet(tweet)
            task = asyncio.create_task(coro)
            tasks.append(task)

        inspect_link_tweets = await asyncio.gather(*tasks)
        filtered_inspect_link_tweets = [t for t in inspect_link_tweets if t is not None]

        return filtered_inspect_link_tweets

    async def run(self: CSInspect) -> None:
        running_search_task = await self.search_task()
        running_live_task = await self.live_task()
        tasks = filter(None, (running_search_task, running_live_task))
        await asyncio.gather(*tasks)

    async def search_task(self: CSInspect) -> asyncio.Task[None] | None:
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
                return

            logger.info(f"DONE FINDING TWEETS ({len(items_tweets)} TWEETS FOUND)")

        async def incrementally_find_and_process_tweets() -> None:
            logger.debug("STARTING: SEARCH TWEETS")
            while True:
                await find_and_process_tweets()
                await asyncio.sleep(TWEET_SEARCH_DELAY)

        coro = incrementally_find_and_process_tweets()
        task = asyncio.create_task(coro)
        return task

    async def live_task(self: CSInspect) -> asyncio.Task[None] | None:
        if not ENABLE_TWITTER_LIVE or self.twitter.live is None:
            logger.debug("NOT STARTING: LIVE TWEETS")
            return None

        logger.debug("STARTING: LIVE TWEETS")
        await self.twitter.live.add_rules(TWITTER_LIVE_RULES)
        task: asyncio.Task[None] = await self.twitter.live.filter(
            expansions=TWEET_EXPANSIONS, tweet_fields=TWEET_TWEET_FIELDS, user_fields=TWEET_USER_FIELDS
        )  # type: ignore
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

        if SILENT_MODE:
            logger.success("SKIPPING TWEET (SILENT_MODE IS ENABLED)")
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

    def parse_match(self: CSInspect, match: re.Match) -> str:
        group_dict = match.groupdict()

        s = group_dict.get("S")
        m = group_dict.get("M")
        a = group_dict.get("A")
        d = group_dict.get("D")

        inspect_link = TWITTER_INSPECT_URL_TEMPLATE.format(s or m, a, d)
        return inspect_link

    async def parse_tweet(self: CSInspect, tweet: tweepy.Tweet) -> TweetWithInspectLink | None:
        matches: list[re.Match] = list(TWITTER_INSPECT_URL_REGEX.finditer(tweet.text))
        matches = matches[:TWEET_MAX_IMAGES]

        if not matches:
            # sometimes bc the tweet actually contains a demo link
            # sometimes bc the tweet is a retweet and is truncated (the original will be queried)
            logger.info(f"SKIPPING TWEET (No Inspect Links): {tweet.id}")
            return None

        if DEV_MODE and tweet.author_id != DEV_ID:
            logger.info(f"SKIPPING TWEET (DEV_MODE Enabled & Tweet Author isn't Dev): {tweet.id}, {tweet.author_id} ")
            return None
        if not DEV_MODE and tweet.author_id == DEV_ID:
            logger.info(f"SKIPPING TWEET (DEV_Mode Disabled & Tweet Author is Dev): {tweet.id}, {tweet.author_id} ")
            return None

        async with self.lock:
            items = tuple(Item(inspect_link=self.parse_match(match)) for match in matches)

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
