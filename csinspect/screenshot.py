from __future__ import annotations

import asyncio
import json
import typing as t
from sys import version_info

import httpx
from loguru import logger

if t.TYPE_CHECKING:
    from csinspect.item import Item


class Screenshot:
    USER_AGENT = f"csinspect/1.0.0 (https://github.com/hexiro/csinspect), Python/{version_info.major}.{version_info.minor}, httpx/{httpx.__version__}"
    HEADERS: t.ClassVar = {
        "Upgrade-Insecure-Requests": "1",
        "User-Agent": USER_AGENT,
    }

    async def skinport_screenshot(self: Screenshot, item: Item) -> bool:
        """
        Unlike swap.gg, Skinport does not use a WebSocket connection to get the screenshot.
        """
        try:
            async with httpx.AsyncClient(timeout=300, follow_redirects=False) as session:
                params = {"link": item.unquoted_inspect_link}
                response = await session.get("https://screenshot.skinport.com/direct", params=params)

                # redirects and format inspect link
                if response.status_code == 308 and response.next_request:
                    logger.debug(f"SKINPORT SCREENSHOT REDIRECT: {response.next_request.url}")
                    response = await session.send(response.next_request)

            # redirects to the image link
            # (no need to follow request at this point in time)
            if response.next_request:
                item.image_link = str(response.next_request.url)
                return True
            else:
                logger.debug(f"SKINPORT SCREENSHOT FAILED: {response.status_code=}, {response.next_request=}")
                return False
        except httpx.HTTPError:
            logger.exception(f"SKINPORT SCREENSHOT FAILED (HTTP ERROR: {item.inspect_link})")
            return False
        except json.JSONDecodeError:
            logger.exception(f"SKINPORT SCREENSHOT FAILED (JSON DECODE ERROR: {item.inspect_link})")
            return False
        except Exception:
            logger.exception(f"SKINPORT SCREENSHOT ERROR (UNKNOWN ERROR): {item.inspect_link}")
            return False

    async def screenshot_item(self: Screenshot, item: Item) -> bool:
        logger.debug(f"SCREENSHOTTING: {item.inspect_link}")

        success = await self.skinport_screenshot(item)

        if not success or not item.image_link:
            logger.warning(f"SCREENSHOT FAILED: {item.inspect_link}")
            return False

        logger.debug(f"SCREENSHOT COMPLETE: {item.image_link} {success=}")
        return True

    async def screenshot_items(self: Screenshot, items: t.Iterable[Item]) -> list[bool]:
        screenshot_tasks: list[asyncio.Task[bool]] = []

        for item in items:
            screenshot_coro = self.screenshot_item(item)
            screenshot_task = asyncio.create_task(screenshot_coro)
            screenshot_tasks.append(screenshot_task)

        screenshot_responses: list[bool] = await asyncio.gather(*screenshot_tasks)
        return screenshot_responses


if __name__ == "__main__":  # pragma: no cover
    from csinspect.item import Item

    async def main() -> None:
        screenshot = Screenshot()
        item = Item(input("Inspect Link: "))
        await screenshot.screenshot_item(item)
        logger.success("IMAGE LINK: ", item.image_link)

    asyncio.run(main())
