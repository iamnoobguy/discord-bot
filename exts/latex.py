import discord
from discord.ext import commands

from bot import BaseBot
from utils.latex import render_latex_jpg

class LaTeX(commands.Cog):
    def __init__(self, bot: BaseBot):
        self.bot = bot

    @commands.command(name="latex", aliases=["tex"])
    async def latex(self, ctx: commands.Context, *, latex_code: str):
        """Render LaTeX code as an image."""

        loop = self.bot.loop
        buf = await loop.run_in_executor(None, render_latex_jpg, latex_code, f"latex_{ctx.message.id}")
        
        if buf is None:
            await ctx.send("Failed to render LaTeX. Please check your code.")
            return

        file = discord.File(fp=buf, filename=f"latex_{ctx.message.id}.jpg")
        await ctx.send(file=file)


async def setup(bot: BaseBot):
    await bot.add_cog(LaTeX(bot))
