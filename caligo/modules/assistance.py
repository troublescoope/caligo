import asyncio
from datetime import datetime
from typing import ClassVar, Optional, Tuple

from pyrogram import filters, types
from pyrogram.errors import MessageDeleteForbidden, MessageIdInvalid

from caligo import command, listener, module, util
from caligo.core import database
from caligo.util.cache_limiter import CacheLimiter


class Assistant(module.Module):
    name: ClassVar[str] = "Assistant"

    db: database.AsyncCollection
    cache: CacheLimiter

    async def on_load(self) -> None:
        self.db = self.bot.db.get_collection(self.name.lower())
        self.cache = CacheLimiter(ttl=60, max_value=3)

    async def _afk_data(self) -> Tuple[bool, Optional[datetime], Optional[int], str]:
        data = await self.db.find_one({"_id": 0})
        if data:
            return (
                data.get("afk", False),
                data.get("start_time"),
                data.get("strict"),
                data.get("reason", ""),
            )
        return False, None, None, ""

    async def _set_afk(
        self, afk: bool, reason: Optional[str] = None, strict: int = 0
    ) -> None:
        update_data = {
            "afk": afk,
            "reason": reason,
            "strict": strict,
            "start_time": datetime.now(),
        }
        await self.db.update_one({"_id": 0}, {"$set": update_data}, upsert=True)

    async def delete_message_after(self, message: types.Message, seconds: int) -> None:
        try:
            await asyncio.sleep(seconds)
            await message.delete()
        except (MessageDeleteForbidden, MessageIdInvalid) as e:
            self.log.error(f"Error deleting message: {e}")

    @command.desc("Handle messages or tags when you're away")
    @command.usage("afk [reason?]")
    async def cmd_afk(self, ctx: command.Context) -> None:
        reason = ctx.input or (
            ctx.reply_msg.text or ctx.reply_msg.caption if ctx.reply_msg else None
        )
        await self._set_afk(True, reason, strict=ctx.msg.id)
        await ctx.respond("__I'll be back later...__", delete_after=5)

    @listener.filters(
        ~filters.bot
        & ~filters.channel
        & ~filters.service
        & (filters.private | filters.mentioned)
        | filters.outgoing
    )
    async def on_message(self, msg: types.Message) -> None:
        afk, start_time, strict_msg, reason = await self._afk_data()

        if not afk or msg.id == strict_msg:
            return

        if msg.outgoing:
            await self._set_afk(False)
            await msg.reply("Welcome back!")
            return

        if not await self.cache.exceeded(msg.from_user.id):
            afk_time = util.time.format_duration_td(datetime.now() - start_time)
            reason_text = f"**Reason:** `{reason}`\n" if reason else ""
            response = (
                f"**I'm currently away**\n{reason_text}**Since:** `{afk_time}` ago..."
            )
            response_msg = await msg.reply(response, quote=True)
            asyncio.create_task(self.delete_message_after(response_msg, 10))
            await self.cache.increment(msg.from_user.id)
