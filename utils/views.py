"""Boilerplate discord.ui.Views."""

from typing import TypeVar, Optional, Union
import re

import discord
from discord.ext import commands

from utils.constants import EMOJIS, HTTP_URL_REGEX

BotT = TypeVar("BotT", bound="commands.Bot")


def re_url_match(url: str):
    """

    :param url: str:
    :param url: str: 

    """
    return re.fullmatch(HTTP_URL_REGEX, url)


def url_jump_button(url: str, to_where: str = "to Message"):
    """

    :param url: str:
    :param to_where: str:  (Default value = "to Message")
    :param url: str: 
    :param to_where: str:  (Default value = "to Message")

    """
    if not re_url_match(url):
        raise ValueError("Invalid URL.")

    return discord.ui.Button(
        label=f"Jump {to_where}", style=discord.ButtonStyle.link, url=url
    )


def url_jump_view(url: str, to_where: str = "to Message"):
    """

    :param url: str:
    :param to_where: str:  (Default value = "to Message")
    :param url: str: 
    :param to_where: str:  (Default value = "to Message")

    """
    if not re_url_match(url):
        raise ValueError("Invalid URL.")

    return discord.ui.View().add_item(url_jump_button(url, to_where=to_where))


class BaseView(discord.ui.View):
    """Base View for other views."""

    def __init__(
        self,
        *,
        timeout=180,
        target,
    ):
        self.target = target

        self.author: Optional[Union[discord.User, discord.Member]] = target and (
            target.user if isinstance(target, discord.Interaction) else target.author  # type: ignore
        )

        self.ctx_msg = None

        super().__init__(timeout=timeout)

    async def stop(self, interaction: discord.Interaction):
        for child in self.children:
            setattr(child, "disabled", True)

        await interaction.edit_original_response(view=self)

        super().stop()

    async def interaction_check(
        self, interaction: discord.Interaction[discord.Client]
    ) -> bool:
        if self.target is None:
            return True

        assert self.author

        if self.author.id != interaction.user.id:
            await interaction.response.send_message(
                f"{EMOJIS['no']} - Only the author can respond to this",
                ephemeral=True,
            )

        # chnl
        self.target: discord.Interaction
        if (
            self.target.channel
            and interaction.channel
            and self.target.channel.id != interaction.channel.id
        ):
            await interaction.response.send_message(
                f"{EMOJIS['no']} - This isn't in the right channel",
                ephemeral=True,
            )

        return True

    async def on_timeout(self) -> None:
        for child in self.children:
            setattr(child, "disabled", True)

        if not self.target:
            return

        if isinstance(self.target, discord.Interaction):
            await self.target.edit_original_response(view=self)
        else:
            await self.ctx_msg.edit(view=self)  # type: ignore


class ConfirmView(BaseView):
    """View for confirming or denying a request."""

    def __init__(
        self,
        target: discord.Interaction | commands.Context,
        timeout=180,
        confirm_msg: str | None = None,
        deny_msg: str | None = None,
    ):
        super().__init__(timeout=timeout, target=target)

        self.value = None

        self.confirm_msg = confirm_msg
        self.deny_msg = deny_msg

    @discord.ui.button(emoji=EMOJIS["white_tick"], style=discord.ButtonStyle.green)
    async def confirm_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if self.confirm_msg:
            await interaction.response.edit_message(content=self.confirm_msg, view=self)
        else:
            await interaction.response.defer()

        self.value = True
        await self.stop(interaction)

    @discord.ui.button(emoji=EMOJIS["white_x"], style=discord.ButtonStyle.red)
    async def deny_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if self.deny_msg:
            await interaction.response.edit_message(content=self.deny_msg, view=self)
        else:
            await interaction.response.defer()

        self.value = False
        await self.stop(interaction)
