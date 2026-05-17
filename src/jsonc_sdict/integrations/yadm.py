"""support config file backup, because we are afraid of breaking our config file.

## Methods
For linux, we use [yadm](https://github.com/yadm-dev/yadm "yet another dotfile manager") because it has a lot stars. We will auto commit each change in local yadm git repo(but no push).

For windows, we currently don't support in v0.2. Maybe in v0.3 we use fallback method: rename old config file like `config.2026-month-day_HH:MM:SS.jsonc.bak`, then create new config. Issues for suggestions are welcomed!

## Notify
We use `desktop_notifier` to notify user that config files are changed by default.
"""

from __future__ import annotations

import asyncio
from desktop_notifier import DesktopNotifier

notifier = DesktopNotifier()


async def main():
    await notifier.send(title="Hello world!", message="Sent from Python")


if __name__ == "__main__":
    asyncio.run(main())
