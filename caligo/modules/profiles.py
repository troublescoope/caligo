from typing import ClassVar, Optional

from caligo import command, module


class Profiles(module.Module):
    name: ClassVar[str] = "Profiles"

    @command.desc("Update profile information (first name, last name, and bio)")
    @command.usage(
        "setprofile new name or bio [Add -l flags for update lastname] [Add -b flags for update bio]"
    )
    @command.alias("sp")
    async def cmd_setprofile(self, ctx: command.Context) -> Optional[str]:
        # Check if ctx.input is None or empty
        if ctx.input is None or not ctx.input.strip():
            return "**Input is empty!**\n__Send a command with a new name and add '-l' flag for changing the last name and '-b' for changing the bio.__"

        # Initialize first_name, last_name, and bio with current profile values
        user_profile = await self.bot.client.get_chat("me")
        first_name = user_profile.first_name
        last_name = user_profile.last_name
        bio = user_profile.bio

        # Split the input into segments using "-" as the separator
        segments = ctx.input.split("-")

        # Update the profile variables based on input and flags
        if segments[0].strip():
            first_name = segments[0].strip()

        elif "l" in ctx.flags:
            last_name = ctx.flags["l"]

        elif "b" in ctx.flags:
            bio = ctx.flags["b"]

        await self.bot.client.update_profile(
            first_name=first_name, last_name=last_name, bio=bio
        )
        return "__Profile updated successfully.__"
