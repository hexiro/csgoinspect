from __future__ import annotations

import io
from typing import TYPE_CHECKING

import requests
import tweepy
import tweepy.models
from loguru import logger

from csgoinspect import redis_
from csgoinspect.typings import ItemScreenshotState

if TYPE_CHECKING:
    from csgoinspect.twitter import Twitter
    from csgoinspect.item import Item


class ItemsTweet(tweepy.Tweet):
    """A Tweet that also contains data about CS:GO items."""

    def __init__(self, data):
        super().__init__(data)
        self.items: list[Item] = []
        self._twitter: Twitter | None = None

    def __str__(self):
        return repr(self)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.id!r} url={self.url!r} items={self.items!r}>"

    @property
    def url(self) -> str:
        return f"https://twitter.com/i/web/status/{self.id}"

    def assign_items(self, *items: Item):
        self.items.extend(items)

    def alert_item_updated(self) -> None:
        logger.debug("alerted of item update")
        if any(i.state != ItemScreenshotState.FINISHED for i in self.items):
            logger.debug("not replying")
            return
        self.reply()

    def _upload_items(self) -> list[tweepy.models.Media]:
        media_uploads: list[tweepy.models.Media] = []
        for item in self.items:
            if not item.image_link:
                continue
            screenshot = requests.get(item.image_link)
            screenshot_file = io.BytesIO(screenshot.content)
            media: tweepy.models.Media = self._twitter.media_upload(filename=item.image_link, file=screenshot_file)  # type: ignore
            media_uploads.append(media)
        return media_uploads

    def reply(self):
        logger.success(f"replying to tweet: {self!r}")
        media_uploads = self._upload_items()
        media_ids: list[int | str] = [media.media_id for media in media_uploads]  # type: ignore
        self._twitter.create_tweet(in_reply_to_tweet_id=self.id, media_ids=media_ids)  # type: ignore
        redis_.store_tweet(self)
