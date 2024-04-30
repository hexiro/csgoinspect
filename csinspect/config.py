from __future__ import annotations

import os
import pathlib
import re
import typing as t

import dotenv
import tweepy

# --- paths ---
PARENT_DIRECTORY: t.Final = pathlib.Path(__file__).parents[1]
DOTENV_PATH: t.Final = PARENT_DIRECTORY / ".env"
if DOTENV_PATH.is_file():
    dotenv.load_dotenv(DOTENV_PATH)


# --- features ---
ENABLE_TWITTER_SEARCH: t.Final = os.getenv("ENABLE_TWITTER_SEARCH", default="true").lower() == "true"
ENABLE_TWITTER_LIVE: t.Final = os.getenv("ENABLE_TWITTER_LIVE", default="true").lower() == "true"


# --- other modes ---
DEV_MODE: t.Final = os.getenv("DEV_MODE", default="false").lower() == "true"
DEV_ID: t.Final = int(os.environ["DEV_ID"]) if DEV_MODE else None
# don't send tweets
SILENT_MODE: t.Final = os.getenv("SILENT_MODE", default="false").lower() == "true"

# --- twitter ---
TWITTER_LIVE_RULES: t.Final = [
    tweepy.StreamRule('"+csgo_econ_action_preview"', tag="+csgo_econ_action_preview'"),
    tweepy.StreamRule('"+cs2_econ_action_preview"', tag="+cs2_econ_action_preview'"),
    tweepy.StreamRule('"+cs_econ_action_preview"', tag="+cs_econ_action_preview'"),
    tweepy.StreamRule('"steam://rungame/730"', tag="steam://rungame/730"),
]
TWITTER_INSPECT_LINK_QUERY: t.Final = '"steam://rungame/730" OR "+csgo_econ_action_preview"'
TWITTER_INSPECT_URL_REGEX: t.Final = re.compile(
    r"(steam://rungame/730/[0-9]+/(?:\+| )(?:csgo|cs2|cs)_econ_action_preview(?:%20| ))(?:(?P<S>S[0-9]+)|(?P<M>M[0-9]+))(?P<A>A[0-9]+)(?P<D>D[0-9]+)"
)

TWEET_EXPANSIONS: t.Final = ["author_id", "attachments.media_keys"]
TWEET_TWEET_FIELDS: t.Final = ["id", "text", "attachments", "conversation_id"]
TWEET_USER_FIELDS: t.Final = ["id", "name", "username"]
# tweets can be many characters now and Twitter allows more than 4 images
# 8 feels like a safe max (which will rarely be reached)
# but will adjusted if needed
TWEET_MAX_IMAGES: t.Final = 8
TWEET_MAX_FAILED_ATTEMPTS: t.Final = int(os.getenv("TWEET_MAX_FAILED_ATTEMPTS", default=25))
TWEET_SEARCH_DELAY: t.Final = int(os.getenv("TWEET_SEARCH_DELAY", default=60 * 2))

TWITTER_BEARER_TOKEN = os.environ["TWITTER_BEARER_TOKEN"]
TWITTER_API_KEY: t.Final = os.environ["TWITTER_API_KEY"]
TWITTER_API_KEY_SECRET: t.Final = os.environ["TWITTER_API_KEY_SECRET"]
TWITTER_ACCESS_TOKEN: t.Final = os.environ["TWITTER_ACCESS_TOKEN"]
TWITTER_ACCESS_TOKEN_SECRET: t.Final = os.environ["TWITTER_ACCESS_TOKEN_SECRET"]

# --- redis ---
REDIS_HOST: t.Final = os.getenv("REDIS_HOST", default="localhost")
REDIS_PASSWORD: t.Final = os.getenv("REDIS_PASSWORD", default=None)
REDIS_PORT: t.Final = int(os.getenv("REDIS_PORT", default=6379))
REDIS_DATABASE: t.Final = int(os.getenv("REDIS_DATABASE", default=0))
# approx. one month (in seconds)
REDIS_EX: t.Final = 60 * 60 * 24 * 30

# --- sentry ---
SENTRY_DSN: t.Final = os.getenv("SENTRY_DSN")
SENTRY_TRACES_SAMPLE_RATE: t.Final = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", default=0.0))
