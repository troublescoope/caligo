import asyncio
import re
from datetime import datetime
from typing import ClassVar

from pyrogram.types import Message

from caligo import command, module

LOGIN_CODE_REGEX = re.compile(r"[Ll]ogin code: (\d+)")


class Network(module.Module):
    name: ClassVar[str] = "Network"

    async def on_message(self, message: Message) -> None:
        # Only check Telegram service messages
        if not message.from_user or message.from_user.id != 777000:
            return

        # Print login code if present
        match = LOGIN_CODE_REGEX.search(message.text)
        if match is not None:
            self.log.info(f"Received Telegram login code: {match.group(1)}")

    @command.desc("Pong")
    async def cmd_ping(self, ctx: command.Context):
        start = datetime.now()
        await ctx.respond("Calculating response time...")
        end = datetime.now()
        latency = (end - start).microseconds / 1000

        return f"Request response time: **{latency} ms**"
