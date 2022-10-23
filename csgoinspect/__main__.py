from __future__ import annotations

from loguru import logger

from csgoinspect import swapgg
from csgoinspect.twitter import Twitter


def main() -> None:
    twitter = Twitter()
    try:
        for tweet in twitter.find_tweets():
            logger.info(f"handling tweet: {tweet!r}")
            for item in tweet.items:
                swapgg.screenshot(item)

        for tweet in twitter.live():
            logger.info(f"handling tweet: {tweet!r}")
            for item in tweet.items:
                swapgg.screenshot(item)
    except Exception as e:
        logger.exception(e)
    finally:
        swapgg.disconnect()


if __name__ == "__main__":
    main()
