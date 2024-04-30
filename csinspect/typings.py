from __future__ import annotations

from typing import NamedTuple, TypedDict


class _BaseTweetResponseRawData(TypedDict):
    time: str
    successful: bool


class TweetResponseRawData(_BaseTweetResponseRawData, total=False):
    failed_attempts: int


class TweetResponseState(NamedTuple):
    successful: bool
    failed_attempts: int = 0
