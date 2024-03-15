import asyncio
from datetime import datetime, timedelta
from typing import Any, ClassVar, Literal, Optional, Set, Tuple

from aiopath import AsyncPath
from pyrogram import types

from caligo import command, module, util


async def prog_func(
    current: int,
    total: int,
    start_time: int,
    mode: Literal["upload", "download"],
    ctx: command.Context,
    file_name: str,
) -> None:
    """
    Progress function to display upload/download progress.
    """
    percent = current / total
    end_time = util.time.sec() - start_time
    now = datetime.now()

    try:
        speed = round(current / end_time, 2)
        eta = timedelta(seconds=int(round((total - current) / speed)))
    except ZeroDivisionError:
        speed = 0
        eta = timedelta(seconds=0)

    bullets = "●" * int(round(percent * 10)) + "○"
    if len(bullets) > 10:
        bullets = bullets.replace("○", "")

    status = "Uploading" if mode == "upload" else "Downloading"
    space = "    " * (10 - len(bullets))
    progress = (
        f"`{file_name}`\n"
        f"Status: **{status}**\n"
        f"Progress: [{bullets + space}] {round(percent * 100)}%\n"
        f"__{util.misc.human_readable_bytes(current)} of "
        f"{util.misc.human_readable_bytes(total)} @ "
        f"{util.misc.human_readable_bytes(speed, postfix='/s')}\n"
        f"eta - {util.time.format_duration_td(eta)}__\n\n"
    )

    # Only edit message once every 5 seconds to avoid ratelimits
    if (
        ctx.last_update_time is None
        or (now - ctx.last_update_time).total_seconds() >= 5
    ):
        await ctx.respond(progress)
        ctx.last_update_time = now


class Transmission(module.Module):
    name: ClassVar[str] = "Transmission"

    tasks: Set[Tuple[int, asyncio.Task[Any]]]

    async def on_load(self) -> None:
        self.tasks = set()

    async def download_media(
        self,
        ctx: command.Context,
        message: types.Message,
        task_name: str,
        all_media: bool = False,
    ) -> Optional[str]:
        """
        Download media from a Telegram message.
        """
        start_time = util.time.sec()

        if not all_media:
            if not message.media:
                return "__Failed to download media: No media found.__"
            media = message.media
            msg_list = [message]
        else:
            try:
                msg_list = await self.bot.client.get_media_group(
                    message.chat.id, message.id
                )
            except ValueError:
                msg_list = [message]

        results = set()

        for msg in msg_list:
            media = getattr(msg, msg.media.value)
            if not media:
                continue

            try:
                name = media.file_name
            except AttributeError:
                name = (
                    f"{msg.media.value}_{media.date.strftime('%Y-%m-%d_%H-%M-%S')}"
                    if hasattr(media, "date")
                    else f"{msg.media.value}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
                )

            task = self.bot.loop.create_task(
                self.bot.client.download_media(
                    msg,
                    progress=prog_func,
                    progress_args=(start_time, "download", ctx, name),
                )
            )
            self.tasks.add((ctx.msg.id, task))
            try:
                await task
            except asyncio.CancelledError:
                return "__Transmission aborted.__"
            else:
                self.tasks.remove((ctx.msg.id, task))
                results.add((msg.id, task.result()))

        path = ""
        for msg_id, result in results:
            if not result:
                path += f"__Failed to download media({msg_id}).__"
                continue

            if isinstance(result, str):
                path += (
                    f"\n× `{ctx.bot.client.workdir}/downloads/{result.split('/')[-1]}`"
                )
            else:
                path += f"\n× `{ctx.bot.client.workdir}/downloads/{result.name}`"

        if not path:
            return "__Failed to download media.__"

        return f"Downloaded to:\n{path}"

    @command.desc("Abort transmission of upload or download")
    @command.usage("[message progress to abort]", reply=True)
    async def cmd_abort(self, ctx: command.Context) -> Optional[str]:
        """
        Abort transmission task.
        """
        if not ctx.input and not ctx.msg.reply_to_message:
            return "__Pass GID or reply to message of task to abort transmission.__"

        if ctx.msg.reply_to_message and ctx.input:
            return "__Can't pass GID/Message Id while replying to message.__"

        reply_msg = ctx.msg.reply_to_message

        for msg_id, task in list(self.tasks.copy()):
            if reply_msg and reply_msg.id == msg_id or ctx.input == int(msg_id):
                task.cancel()
                self.tasks.remove((msg_id, task))
                break
            else:
                return "__The message you choose is not in task.__"

        await ctx.msg.delete()

    @command.desc("Download file from telegram server.")
    @command.alias("dl")
    @command.usage(
        "download reply or send link with [message media to download]\n-b: Bulk media download."
    )
    async def cmd_download(self, ctx: command.Context) -> str:
        """
        Download file from a Telegram message.
        """
        reply_msg = ctx.msg.reply_to_message
        if reply_msg and not reply_msg.media:
            return "__The message you replied to doesn't contain any media.__"

        await ctx.respond("Preparing to download...")

        if ctx.input:
            chat_id, msg_id = await util.tg.parse_telegram_link(ctx.input)
        else:
            chat_id = ctx.chat.id
            msg_id = reply_msg.id

        message = (
            reply_msg
            if reply_msg
            else await self.bot.client.get_messages(chat_id, msg_id)
        )
        bulk = True if "b" in ctx.flags else False

        return await self.download_media(ctx, message, "Download", bulk)

    @command.desc("Upload file into telegram server")
    @command.alias("ul")
    @command.usage("[file path]")
    async def cmd_upload(self, ctx: command.Context) -> Optional[str]:
        """
        Upload file to a Telegram server.
        """
        if not ctx.input:
            return "__Pass the file path.__"

        start_time = util.time.sec()
        file_path = AsyncPath(ctx.input)

        if await file_path.is_dir():
            return "__The path you input is a directory.__"

        if not await file_path.is_file():
            return "__The file you input doesn't exist.__"

        await ctx.respond("Preparing to upload...")
        task = self.bot.loop.create_task(
            self.bot.client.send_document(
                ctx.msg.chat.id,
                str(file_path),
                message_thread_id=ctx.msg.message_thread_id,
                force_document=True,
                progress=prog_func,
                progress_args=(start_time, "upload", ctx, file_path.name),
            )
        )
        self.tasks.add((ctx.msg.id, task))
        try:
            await task
        except asyncio.CancelledError:
            return "__Transmission aborted.__"
        else:
            self.tasks.remove((ctx.msg.id, task))

        await ctx.msg.delete()
