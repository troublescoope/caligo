from caligo import command, module

class Afk(module.Module):
    name: ClassVar[str] = "Afk"
    
    
    @command.desc("Handle message or tag when you're leaving")
    @command.usage("afk [reason?]")
    async def cmd_afk(self, ctx: command.Context):
        await ctx.respond("__Will be back later...__")
        
        
    @command.desc("Remove afk handler")
    @command.usage("unafk")
    async def cmd_unafk(self, ctx: command.Context):
        await ctx.respond("You're back\n\n You can view logging in bot")
        
        