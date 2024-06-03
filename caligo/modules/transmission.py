import asyncio
from datetime import datetime, timedelta
from typing import Any, ClassVar, Literal, Optional, Set, Tuple

from aiopath import AsyncPath
from pyrogram import Client, types

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
    elapsed_time = util.time.sec() - start_time
    now = datetime.now()

    try:
        speed = round(current / elapsed_time, 2)
        eta = timedelta(seconds=int(round((total - current) / speed)))
    except ZeroDivisionError:
        speed = 0
        eta = timedelta(seconds=0)

    # Generate progress bars
    progress_bars = "●" * int(round(percent * 10)) + "○" * (
        10 - int(round(percent * 10))
    )

    # Ensure the progress bar doesn't exceed 10 characters
    if len(progress_bars) > 10:
        progress_bars = progress_bars[:10]

    status = "Uploading" if mode == "upload" else "Downloading"
    progress_message = (
        f"`{file_name}`\n"
        f"Status: **{status}**\n"
        f"Progress: [{progress_bars.ljust(10)}] {round(percent * 100)}%\n"
        f"__{util.misc.human_readable_bytes(current)} of "
        f"{util.misc.human_readable_bytes(total)} @ "
        f"{util.misc.human_readable_bytes(speed, postfix='/s')}\n"
        f"ETA - {util.time.format_duration_td(eta)}__\n\n"
    )

    # Update message every 5 seconds to avoid rate limits
    if (
        ctx.last_update_time is None
        or (now - ctx.last_update_time).total_seconds() >= 5
    ):
        await ctx.respond(progress_message)
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

        # Determine whether to download a media group or a single message
        if not all_media:
            if not message.media:
                return "__Failed to download media: No media found.__"
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
            media = getattr(msg, msg.media.value, None)
            if not media:
                continue

            name = getattr(
                media,
                "file_name",
                f"{msg.media.value}_{getattr(media, 'date', datetime.now()).strftime('%Y-%m-%d_%H-%M-%S')}",
            )

            # Create a task to download each media message
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

        paths = "\n".join(
            f"× `{self.bot.client.workdir}/downloads/{result.split('/')[-1] if isinstance(result, str) else result.name}`"
            for msg_id, result in results
            if result
        )

        return paths if paths else "__Failed to download media.__"

    async def upload_file(
        self,
        ctx: command.Context,
        path: AsyncPath,
        del_path: bool,
        caption: str = None,
        thumb: Optional[str] = None,
        extra: dict = None,
    ):
        """
        Upload a file to a Telegram chat.

        Parameters:
        - ctx: The command context.
        - path: The path of the file as an AsyncPath object.
        - del_path: Boolean indicating whether to delete the file after upload.
        - caption: The caption to include with the upload.
        - thumb: The path to the thumbnail image (if applicable).
        - extra: Additional data to pass to the upload function.
        """
        extra = extra or {}
        file_name = path.name.lower()

        if file_name.endswith((".mkv", ".mp4", ".webm", ".m4v")):
            await self.bot.client.send_video(
                ctx.msg.chat.id, video=str(path), thumb=thumb, caption=caption, **extra
            )
        elif file_name.endswith((".mp3", ".flac", ".wav", ".m4a")):
            await self.bot.client.send_audio(
                ctx.msg.chat.id, audio=str(path), caption=caption, **extra
            )
        elif file_name.endswith((".jpg", ".jpeg", ".png", ".bmp")):
            await self.bot.client.send_photo(
                ctx.msg.chat.id, photo=str(path), caption=caption, **extra
            )
        else:
            await self.bot.client.send_document(
                ctx.msg.chat.id,
                document=str(path),
                thumb=thumb,
                caption=caption,
                **extra,
            )

        if del_path:
            await path.unlink()

    @command.desc("Abort transmission of upload or download")
    @command.usage("[message progress to abort]", reply=True)
    async def cmd_abort(self, ctx: command.Context) -> Optional[str]:
        """
        Abort transmission task.
        """
        if not ctx.input and not ctx.msg.reply_to_message:
            return "__Pass GID or reply to the message of the task to abort transmission.__"

        if ctx.msg.reply_to_message and ctx.input:
            return "__Can't pass GID/Message ID while replying to a message.__"

        reply_msg = ctx.msg.reply_to_message

        for msg_id, task in list(self.tasks):
            if (reply_msg and reply_msg.id == msg_id) or (
                ctx.input and int(ctx.input) == msg_id
            ):
                task.cancel()
                self.tasks.remove((msg_id, task))
                break
        else:
            return "__The message you chose is not in task.__"

        await ctx.msg.delete()

    @command.desc("Download file from Telegram server.")
    @command.alias("dl")
    @command.usage(
        "download reply or send link with [message media to download]\n-b: Bulk media download."
    )
    async def cmd_download(self, ctx: command.Context) -> str:
        """
        Download file from a Telegram message.
        """

        reply_msg = ctx.msg.reply_to_message

        if not ctx.input and not reply_msg:
            return "`Reply to any media or provide a Telegram link!`"
        if reply_msg and not reply_msg.media:
            return "__The message you replied to doesn't contain any media.__"
        await ctx.respond("Preparing to download...")

        if ctx.input:
            chat_id, msg_id = await util.tg.parse_telegram_link(ctx.input)
        else:
            chat_id = ctx.chat.id
            msg_id = reply_msg.id

        bulk = "b" in ctx.flags
        message = (
            reply_msg
            if reply_msg
            else await self.bot.client.get_messages(chat_id, msg_id)
        )

        return await self.download_media(ctx, message, "Download", bulk)

    @command.desc("Upload file to Telegram server")
    @command.alias("ul")
    @command.usage("[file path] [-d] [-c caption]")
    async def cmd_upload(self, ctx: command.Context) -> Optional[str]:
        """
        Upload file to a Telegram server.
        """
        if not ctx.segments and not ctx.flags.get("f"):
            return "__Pass the file path.__"

        start_time = util.time.sec()
        file_path = None
        del_path = False
        caption = ""

        if ctx.args:
            file_path = AsyncPath(ctx.args[0])
            print(file_path)
        elif "f" in ctx.flags:
            file_path = AsyncPath(ctx.flags["f"])

        if file_path and not await file_path.is_file():
            return "__The file you input doesn't exist.__"

        await ctx.respond("Preparing to upload...")

        if "d" in ctx.flags:
            del_path = True

        caption = ctx.flags.get("c", "")

        task = self.bot.loop.create_task(
            self.upload_file(
                ctx,
                file_path,
                del_path=del_path,
                caption=caption,
                thumb=None,  # Set thumb as per your requirements
                extra={
                    "progress": prog_func,
                    "progress_args": (start_time, "upload", ctx, file_path.name),
                },
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
