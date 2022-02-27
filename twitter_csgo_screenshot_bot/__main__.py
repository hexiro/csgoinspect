from __future__ import annotations

import io
import os
import pathlib
import re
from collections import defaultdict

import dotenv
import requests
import tweepy
import tweepy.models
from redis import Redis

from twitter_csgo_screenshot_bot import swapgg

dotenv_path = pathlib.Path(__file__).parents[1] / ".env"
dotenv.load_dotenv(dotenv_path)

redis = Redis(
    host=os.environ["REDIS_HOST"],
    password=os.environ["REDIS_PASSWORD"],
    port=int(os.environ["REDIS_PORT"]),
    db=int(os.environ["REDIS_DATABASE"])
)

TWITTER_API_KEY = os.environ["TWITTER_API_KEY"]
TWITTER_API_KEY_SECRET = os.environ["TWITTER_API_KEY_SECRET"]

TWITTER_ACCESS_TOKEN = os.environ["TWITTER_ACCESS_TOKEN"]
TWITTER_ACCESS_TOKEN_SECRET = os.environ["TWITTER_ACCESS_TOKEN_SECRET"]

authentication = tweepy.OAuthHandler(TWITTER_API_KEY, TWITTER_API_KEY_SECRET)
authentication.set_access_token(TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET)

twitter = tweepy.API(authentication)

INSPECT_LINK_QUERY = '"steam://rungame/730" "+csgo_econ_action_preview"'
INSPECT_URL_REGEX = re.compile(
    r"(steam:\/\/rungame\/730\/[0-9]+\/\+csgo_econ_action_preview%20)(?:(?P<S>S[0-9]+)|(?P<M>M[0-9]+))(?P<A>A[0-9]+)(?P<D>D[0-9]+)")


def already_has_screenshot(tweet: tweepy.models.Status) -> bool:
    try:
        if tweet.extended_entities["media"]:
            return True
    except (AttributeError, KeyError):
        pass
    return False


def already_responded(tweet: tweepy.models.Status) -> bool:
    try:
        status_id = tweet.id_str
    except AttributeError:
        return True
    return redis.get(status_id) is not None


def main() -> None:
    search_results: tweepy.models.SearchResults = twitter.search_tweets(q=INSPECT_LINK_QUERY, result_type="recent",
                                                                        count=100, tweet_mode="extended")
    tweets: dict[tweepy.models.Status, list[str]] = defaultdict(list)

    for tweet in search_results:
        already_has_screenshot_result = already_has_screenshot(tweet)
        already_responded_result = already_responded(tweet)
        print(f"{already_responded_result=} {already_has_screenshot_result=}")
        if already_has_screenshot_result:
            continue
        if already_responded_result:
            continue
        text: str = tweet.full_text

        number_of_matches = 0
        for match in INSPECT_URL_REGEX.finditer(text):
            number_of_matches += 1
            if number_of_matches > 4:
                break
            print(f"{match=}")
            inspect_link: str = match.group()
            swapgg.take_screenshot(inspect_link)
            tweets[tweet].append(inspect_link)

    # TODO: finish working with multiple tweets per uwu

    for tweet, inspect_links in tweets.items():
        image_links: list[str] = []
        for inspect_link in inspect_links:
            image_link = swapgg.wait_for_screenshot(inspect_link)
            if not image_link:
                continue
            image_links.append(image_link)
        print(f"{image_links=} {inspect_links=}")

        status_id: str = tweet.id_str
        screen_name: str = tweet.user.screen_name

        if not status_id or not screen_name:
            continue

        media_uploads: list[tweepy.models.Media] = []

        for image_link in image_links:
            screenshot = requests.get(image_link)
            screenshot_file = io.BytesIO(screenshot.content)

            media: tweepy.models.Media = twitter.media_upload(filename=image_link, file=screenshot_file)
            media_uploads.append(media)

        updated_status: tweepy.models.Status = twitter.update_status(
            status=f"@{screen_name}",
            in_reply_to_status_id=status_id,
            media_ids=[media_upload.media_id for media_upload in media_uploads]
        )
        print(updated_status)
        redis.set(name=status_id, value=updated_status.id_str, ex=60 * 60 * 24 * 7)

    swapgg.sio.disconnect()


if __name__ == "__main__":
    main()
