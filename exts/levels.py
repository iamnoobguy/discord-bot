import discord
from discord import app_commands
from discord.ext import commands

import config


class XPCog(commands.GroupCog, group_name="levels"):
    """ """

    def __init__(self, bot: commands.Bot, xp_service):
        self.bot = bot
        self.xp_service = xp_service

    # /levels xp
    @app_commands.command(name="xp", description="View your XP profile")
    async def xp(self, interaction: discord.Interaction):
        user = interaction.user
        current_xp = await self.xp_service.get_xp(user.id)

        current_level = "Unranked"
        next_threshold = 100
        next_level = "Quantum Newbie"

        if config.XP_THRESHOLDS:
            for threshold, (level_name, _) in sorted(
                config.XP_THRESHOLDS.items(), reverse=True
            ):
                if current_xp >= threshold:
                    current_level = level_name
                    higher = sorted(t for t in config.XP_THRESHOLDS if t > threshold)
                    next_threshold = higher[0] if higher else threshold + 500
                    next_level = config.XP_THRESHOLDS.get(
                        next_threshold, ("Master", None)
                    )[0]
                    break
            else:
                next_threshold = sorted(config.XP_THRESHOLDS.keys())[0]

        progress_percent = int((current_xp % next_threshold) / next_threshold * 100)

        box_count = 15
        filled_count = progress_percent // (100 // box_count)
        progress_bar = (
            "🟦 " * filled_count
            + "⬜ " * (box_count - filled_count)
            + f"{progress_percent}%"
        )

        embed = discord.Embed(
            title=f"{user.display_name}'s Physics XP Profile",
            description=f"**Rank:** {current_level} **XP:** {current_xp}",
            color=0x3498DB,
            timestamp=discord.utils.utcnow(),
        )

        embed.set_thumbnail(url=user.display_avatar.url)

        remaining = next_threshold - (current_xp % next_threshold)

        embed.add_field(
            name="Progress to Next Rank",
            value=f"{current_xp % next_threshold} / {next_threshold} XP ({remaining} remaining)",
            inline=False,
        )

        embed.add_field(name="Level Progress", value=progress_bar, inline=False)

        embed.add_field(
            name="Next Milestone",
            value=f"**{next_level}** at {current_xp + remaining} XP",
            inline=False,
        )

        await interaction.response.send_message(embed=embed)

    # /levels add-xp
    @app_commands.command(name="add-xp", description="Add XP to a member")
    @app_commands.checks.has_role("Curator")
    async def add_xp(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        amount: int,
    ):
        if amount <= 0:
            await interaction.response.send_message(
                "❌ Amount must be positive.", ephemeral=True
            )
            return

        await self.xp_service.update_xp(member.id, amount)
        new_xp = await self.xp_service.get_xp(member.id)

        # auto ole assignment
        for threshold, (_, role_name) in config.XP_THRESHOLDS.items():
            if new_xp >= threshold:
                role = discord.utils.get(interaction.guild.roles, name=role_name)
                if role and role not in member.roles:
                    await member.add_roles(role)

        embed = discord.Embed(
            title="XP Granted",
            description=f"{interaction.user.mention} added **{amount} XP** to {member.mention}\nNew total: {new_xp}",
            color=0x00FF00,
        )

        embed.set_thumbnail(url=member.display_avatar.url)

        await interaction.response.send_message(embed=embed)

    # /levels remove-xp
    @app_commands.command(name="remove-xp", description="Remove XP from a member")
    @app_commands.checks.has_role("Curator")
    async def remove_xp(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        amount: int,
    ):
        if amount <= 0:
            await interaction.response.send_message(
                "❌ Amount must be positive.", ephemeral=True
            )
            return

        old_xp = await self.xp_service.get_xp(member.id)
        await self.xp_service.update_xp(member.id, -amount)
        new_xp = await self.xp_service.get_xp(member.id)

        removed = old_xp - new_xp

        if removed == 0:
            await interaction.response.send_message(
                f"⚠️ {member.mention} had 0 XP.", ephemeral=True
            )
            return

        # auto role removal
        for threshold, (_, role_name) in sorted(config.XP_THRESHOLDS.items()):
            role = discord.utils.get(interaction.guild.roles, name=role_name)
            if role and role in member.roles and new_xp < threshold:
                await member.remove_roles(role)

        embed = discord.Embed(
            title="XP Removed",
            description=f"{interaction.user.mention} removed **{removed} XP** from {member.mention}\nNew total: {new_xp}",
            color=0xFF0000,
            timestamp=discord.utils.utcnow(),
        )

        embed.set_thumbnail(url=member.display_avatar.url)

        await interaction.response.send_message(embed=embed)

    # /levels leaderboard
    @app_commands.command(name="leaderboard", description="View top XP holders")
    async def leaderboard(self, interaction: discord.Interaction):
        top_data = await self.xp_service.get_leaderboard(10)

        if not top_data:
            await interaction.response.send_message(
                "📉 Leaderboard is empty.", ephemeral=True
            )
            return

        lines = []

        for rank, (user_id, xp) in enumerate(top_data, 1):

            member = interaction.guild.get_member(user_id)

            if member:
                display_name = member.display_name
            else:
                try:
                    user = await self.bot.fetch_user(user_id)
                    display_name = user.name
                except discord.NotFound:
                    display_name = f"Deleted User ({user_id})"

            prefix = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, f"{rank}.")
            lines.append(f"`{prefix}` **{display_name}** — `{xp} XP`")

        embed = discord.Embed(
            title="🏆 Physics Club Hall of Fame",
            description="\n".join(lines),
            color=0xF1C40F,
            timestamp=discord.utils.utcnow(),
        )

        await interaction.response.send_message(embed=embed)

    # todo: integrate with more modularity
    # Error handler for role check
    @add_xp.error
    @remove_xp.error
    async def role_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.errors.MissingRole):
            await interaction.response.send_message(
                "❌ You need the 'Curator' role.", ephemeral=True
            )
        else:
            self.bot.logger.error(error)
            await interaction.response.send_message(
                "❌ Unexpected error.", ephemeral=True
            )


async def setup(bot):
    xp_service = bot.xp_service  # assume attached during startup
    await bot.add_cog(XPCog(bot, xp_service))
