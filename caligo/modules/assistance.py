import asyncio
from datetime import datetime
from typing import ClassVar, Tuple

from pyrogram import filters, types
from pyrogram.errors.exceptions import MessageDeleteForbidden, MessageIdInvalid

from caligo import command, listener, module, util
from caligo.core import database


class Assistant(module.Module):
    name: ClassVar[str] = "Assistant"

    db: database.AsyncCollection

    async def on_load(self) -> None:
        self.db = self.bot.db.get_collection(self.name.lower())

    async def _set_antipm(self, enable: bool = False, max_msg: int = 3) -> None:
        update_data = {
            "antipm": enable,
            "max_msg": max_msg,
        }
        await self.db.update_one({"_id": 0}, {"$set": update_data}, upsert=True)

    async def _get_antipm(self) -> Tuple[bool, int]:
        data = await self.db.find_one({"_id": 0})
        if data:
            return data.get("antipm", False), data.get("max_msg", 3)
        return False, 3

    async def _is_afk(self) -> Tuple[bool, datetime, int, str]:
        data = await self.db.find_one({"_id": 0})
        afk = data.get("afk", False)
        start_time = data.get("start_time")
        strict_msg = data.get("strict")
        reason = data.get("reason", "")  # Get reason as well
        return afk, start_time, strict_msg, reason

    async def _set_afk(self, afk: bool, reason: str = None, strict: int = 0) -> None:
        update_data = {
            "afk": afk,
            "reason": reason,
            "strict": strict,
            "start_time": datetime.now(),
        }
        await self.db.update_one({"_id": 0}, {"$set": update_data}, upsert=True)

    async def delete_message_after(self, message, seconds):
        try:
            await asyncio.sleep(seconds)
            await message.delete()
        except (MessageDeleteForbidden, MessageIdInvalid) as e:
            # Handle specific exceptions that may occur during message deletion
            self.log.error(f"Error deleting message: {e}")

    @command.desc("Handle messages or tags when you're away")
    @command.usage("afk [reason?]")
    async def cmd_afk(self, ctx: command.Context):
        reason = ctx.input or (
            ctx.reply_msg.text or ctx.reply_msg.caption if ctx.reply_msg else None
        )

        await self._set_afk(True, reason, strict=ctx.msg.id)

        await ctx.respond("__I'll be back later...__", delete_after=5)

    @listener.filters(
        ~filters.bot
        & ~filters.channel
        & ~filters.service
        & (filters.private | filters.mentioned | filters.incoming)
        | filters.outgoing
    )
    async def on_message(self, msg: types.Message):
        afk, start_time, strict_msg, reason = await self._is_afk()
        antipm, max_msg = await self._get_antipm()

        if not afk and not antipm or msg.id == strict_msg:  # Return early if not AFK
            return

        # Exit AFK mode when sending an outgoing message
        if msg.outgoing:
            await self._set_afk(False)
            response_msg = await msg.reply("Welcome back!")

        elif await self.cache.exceeded(msg.from_user.id):
            # User has exceeded rate limit, do not send AFK message
            return

        else:
            afk_time = util.time.format_duration_td(datetime.now() - start_time)

            response = f"**I'm currently away**\n"
            if reason:
                response += f"**Reason:** `{reason}`\n"
            response += f"**Since:** `{afk_time}` ago..."

            # Send the response message and delete it after 10 seconds using asyncio.create_task
            response_msg = await msg.reply(response)

        asyncio.create_task(self.delete_message_after(response_msg, 10))
        # Increment user count to cache
        await self.cache.increment(msg.from_user.id)
