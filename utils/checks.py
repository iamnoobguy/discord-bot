from discord import Interaction, app_commands

from config import SUPER_ADMINS


def is_super_admin():
    """Check if the user is in super admins list"""
    async def predicate(interaction: Interaction):
        if interaction.user.id in SUPER_ADMINS:
            return True
        else:
            return False

    return app_commands.check(predicate)
