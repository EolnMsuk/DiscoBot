# helper.py
import asyncio
import discord
import time
from typing import Any, Callable, Optional, List

from discord.ext import commands
from discord.ui import View, Button
from loguru import logger

from tools import (
    BotState,
    BotConfig,
    handle_errors,
    record_command_usage,
    record_command_usage_by_user,
)

async def _button_callback_handler(interaction: discord.Interaction, command: str, bot_config: BotConfig, state: BotState) -> None:
    """A generic handler for button presses, including permissions and cooldowns."""
    try:
        user_id = interaction.user.id
        # Check if the command is being used in the correct channel
        if interaction.channel.id != bot_config.MUSIC_CONTROL_CHANNEL_ID:
            await interaction.response.send_message(f"Music commands must be used in <#{bot_config.MUSIC_CONTROL_CHANNEL_ID}>", ephemeral=True)
            return

        # Cooldown check
        current_time = time.time()
        async with state.cooldown_lock:
            if user_id in state.button_cooldowns:
                last_used, warned = state.button_cooldowns[user_id]
                time_left = bot_config.COMMAND_COOLDOWN - (current_time - last_used)
                if time_left > 0:
                    if not warned:
                        await interaction.response.send_message(f"Please wait {int(time_left)}s before using another button.", ephemeral=True)
                        state.button_cooldowns[user_id] = (last_used, True)
                    else:
                        await interaction.response.defer(ephemeral=True)
                    return
            state.button_cooldowns[user_id] = (current_time, False)

        await interaction.response.defer()
        cmd_name = command.lstrip("!")
        command_obj = interaction.client.get_command(cmd_name)
        if command_obj:
            # Create a fake message to properly invoke the command context
            fake_message = await interaction.channel.send(f"{interaction.user.mention} used {command}")
            fake_message.content = command
            fake_message.author = interaction.user
            ctx = await interaction.client.get_context(fake_message)
            await interaction.client.invoke(ctx)
            await fake_message.delete()
        else:
            logger.warning(f"Button tried to invoke non-existent command: {cmd_name}")
            await interaction.followup.send("Could not process that command.", ephemeral=True)
    except Exception as e:
        logger.error(f"Error in button callback: {e}", exc_info=True)

class MusicButton(Button):
    def __init__(self, label: str, emoji: str, command: str, style: discord.ButtonStyle, bot_config: BotConfig, state: BotState):
        super().__init__(label=label, emoji=emoji, style=style)
        self.command, self.bot_config, self.state = command, bot_config, state
    async def callback(self, interaction: discord.Interaction): await _button_callback_handler(interaction, self.command, self.bot_config, self.state)

class MusicView(discord.ui.View):
    def __init__(self, bot_config: BotConfig, state: BotState):
        super().__init__(timeout=None)
        btns = [
            ("⏯️", "Toggle", "!mpauseplay", discord.ButtonStyle.danger), 
            ("⏭️", "Skip", "!mskip", discord.ButtonStyle.success), 
            ("🔀", "Mode", "!mshuffle", discord.ButtonStyle.primary),              
            ("❌", "Clear", "!mclear", discord.ButtonStyle.secondary)            
        ]
        for e, l, c, s in btns: 
            self.add_item(MusicButton(label=l, emoji=e, command=c, style=s, bot_config=bot_config, state=state))

class QueueDropdown(discord.ui.Select):
    def __init__(self, bot, state, page_items, author):
        self.bot, self.state, self.author = bot, state, author
        options = [discord.SelectOption(label=f"{i + 1}. {info.get('title', 'Unknown')}"[:100], value=str(i)) for i, info in page_items]
        super().__init__(placeholder="Select a song to jump to...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user != self.author: return await interaction.response.send_message("You can't control this.", ephemeral=True)
        selected_index = int(self.values[0])
        async with self.state.music_lock:
            full_queue = self.state.active_playlist + self.state.search_queue
            if selected_index >= len(full_queue):
                await interaction.response.send_message("That song is no longer in the queue.", ephemeral=True, delete_after=10)
                return await interaction.message.delete()
            selected_song = full_queue.pop(selected_index)
            len_active = len(self.state.active_playlist)
            if selected_index < len_active: self.state.active_playlist.pop(selected_index)
            else: self.state.search_queue.pop(selected_index - len_active)
            self.state.search_queue.insert(0, selected_song)
            self.state.play_next_override = True
        if self.bot.voice_client_music and self.bot.voice_client_music.is_connected():
            self.bot.voice_client_music.stop()
            await interaction.response.send_message(f"✅ Jumping to **{selected_song.get('title')}**.", delete_after=10)
        else:
            await interaction.response.send_message(f"✅ Queued **{selected_song.get('title')}** to play next.", delete_after=10)
        await interaction.message.delete()

class QueueView(discord.ui.View):
    def __init__(self, bot, state, author):
        super().__init__(timeout=300.0)
        self.bot, self.state, self.author, self.current_page, self.page_size = bot, state, author, 0, 25
        self.full_queue, self.message = [], None

    async def start(self):
        await self.update_queue()
        self.update_components()

    async def update_queue(self):
        async with self.state.music_lock: self.full_queue = list(enumerate(self.state.active_playlist + self.state.search_queue))
        self.total_pages = max(1, (len(self.full_queue) + self.page_size - 1) // self.page_size)

    def update_components(self):
        self.clear_items()
        start, end = self.current_page * self.page_size, (self.current_page + 1) * self.page_size
        if page_items := self.full_queue[start:end]: self.add_item(QueueDropdown(self.bot, self.state, page_items, self.author))
        if self.total_pages > 1:
            self.add_item(self.create_nav_button("⬅️ Prev", "prev_page", self.current_page == 0))
            self.add_item(self.create_nav_button("Next ➡️", "next_page", self.current_page >= self.total_pages - 1))

    def create_nav_button(self, label: str, custom_id: str, disabled: bool) -> discord.ui.Button:
        button = discord.ui.Button(label=label, style=discord.ButtonStyle.secondary, custom_id=custom_id, disabled=disabled)
        async def nav_callback(interaction: discord.Interaction):
            if interaction.user != self.author: return await interaction.response.send_message("You can't control this.", ephemeral=True)
            if interaction.data['custom_id'] == 'prev_page': self.current_page -= 1
            else: self.current_page += 1
            self.update_components()
            await interaction.response.edit_message(view=self)
        button.callback = nav_callback
        return button

    async def on_timeout(self):
        if self.message:
            for item in self.children: item.disabled = True
            try: await self.message.edit(view=self)
            except discord.NotFound: pass

class BotHelper:
    def __init__(self, bot: commands.Bot, state: BotState, bot_config: BotConfig, save_func: Optional[Callable] = None, play_next_song_func: Optional[Callable] = None):
        self.bot, self.state, self.bot_config, self.save_state, self.play_next_song = bot, state, bot_config, save_func, play_next_song_func

    async def send_music_menu(self, target: Any) -> None:
        """Sends the interactive music control menu."""
        try:
            status_lines = []
            async with self.state.music_lock:
                status_lines.append(f"**Now Playing:** `{self.state.current_song['title']}`" if self.state.current_song else "**Now Playing:** Nothing")
                status_lines.append(f"**Mode:** {self.state.music_mode.capitalize()}")
                display_volume = int((self.state.music_volume / self.bot_config.MUSIC_MAX_VOLUME) * 100) if self.bot_config.MUSIC_MAX_VOLUME > 0 else 0
                status_lines.append(f"**Volume:** {display_volume}%")
                queue_len = len(self.state.active_playlist + self.state.search_queue)
                if queue_len: status_lines.append(f"**Queue:** {queue_len} song(s)")
            
            description = f"""
*Use commands or buttons to control the music.*
**!m <song or URL>** ----- Find/queue a song
**!q** ---------------------- View the queue
**!np** --------------------- Show current song

*{" | ".join(status_lines)}*
"""
            embed = discord.Embed(title="🎵  Music Controls 🎵", description=description, color=discord.Color.purple())
            destination = target.channel if hasattr(target, 'channel') else target
            if destination and hasattr(destination, 'send'):
                await destination.send(embed=embed, view=MusicView(self.bot_config, self.state))
        except Exception as e:
            logger.error(f"Error in send_music_menu: {e}", exc_info=True)
            
    @handle_errors
    async def confirm_and_clear_music_queue(self, ctx) -> None:
        """Confirms and clears all music queues, stopping playback."""
        record_command_usage(self.state.analytics, "!mclear"); record_command_usage_by_user(self.state.analytics, ctx.author.id, "!mclear")
        async with self.state.music_lock:
            queue_len = len(self.state.active_playlist + self.state.search_queue)
            is_playing = self.bot.voice_client_music and (self.bot.voice_client_music.is_playing() or self.bot.voice_client_music.is_paused())
            if not queue_len and not is_playing: return await ctx.send("Queue is already empty.", delete_after=10)

        confirm_msg = await ctx.send(f"Clear all **{queue_len}** songs and stop playback?\nReact ✅ to confirm.")
        await confirm_msg.add_reaction("✅"); await confirm_msg.add_reaction("❌")

        def check(r, u): return u == ctx.author and str(r.emoji) in ["✅", "❌"] and r.message.id == confirm_msg.id
        try:
            reaction, _ = await self.bot.wait_for("reaction_add", timeout=30.0, check=check)
            if str(reaction.emoji) == "✅":
                was_playing = False
                async with self.state.music_lock:
                    self.state.search_queue.clear(); self.state.active_playlist.clear()
                    if self.bot.voice_client_music and (self.bot.voice_client_music.is_playing() or self.bot.voice_client_music.is_paused()):
                        was_playing = True
                        self.state.stop_after_clear = True 
                        self.bot.voice_client_music.stop()
                msg = f"✅ Cleared **{queue_len}** songs." + (" and stopped playback." if was_playing else "")
                await confirm_msg.edit(content=msg, view=None)
            else: await confirm_msg.edit(content="❌ Cancelled.", view=None)
        except asyncio.TimeoutError: await confirm_msg.edit(content="⌛ Timed out.", view=None)
        finally:
            try: await confirm_msg.clear_reactions()
            except discord.HTTPException: pass

    @handle_errors
    async def show_now_playing(self, ctx) -> None:
        """Shows details about the currently playing song."""
        async with self.state.music_lock:
            if not self.state.current_song or not self.bot.voice_client_music or not (self.bot.voice_client_music.is_playing() or self.bot.voice_client_music.is_paused()):
                return await ctx.send("Nothing is playing.", delete_after=10)
            
            song_info = self.state.current_song
            embed = discord.Embed(title="🎵", description=f"**{song_info.get('title', 'Unknown')}**", color=discord.Color.purple())
            embed.add_field(name="Source", value="Stream" if song_info.get('is_stream', False) else "Local", inline=True)
            display_vol = int((self.state.music_volume / self.bot_config.MUSIC_MAX_VOLUME) * 100) if self.bot_config.MUSIC_MAX_VOLUME > 0 else 0
            embed.add_field(name="Volume", value=f"{display_vol}%", inline=True)
            embed.add_field(name="Mode", value=self.state.music_mode.capitalize(), inline=True)
            await ctx.send(embed=embed)

    @handle_errors
    async def show_queue(self, ctx) -> None:
        """Displays an interactive list of songs in the queue."""
        async with self.state.music_lock:
            if not self.state.active_playlist and not self.state.search_queue:
                return await ctx.send("The music queue is empty.", delete_after=10)
        
        view = QueueView(self.bot, self.state, ctx.author)
        await view.start()
        view.message = await ctx.send(content="**Current Queue:** (Select a song to jump to it)", view=view)

    @handle_errors
    async def show_commands_list(self, ctx) -> None:
        """Displays a formatted list of all available bot commands."""
        user_commands = (
            "`!m <query>` - Searches for songs/URLs to queue.\n"
            "`!q` / `!queue` - Displays the interactive song queue.\n"
            "`!np` / `!nowplaying` - Shows the currently playing song.\n"
            "`!mskip` - Skips the current song.\n"
            "`!mpp` / `!mpauseplay` - Toggles music play/pause.\n"
            "`!vol <0-100>` - Sets the music volume.\n"
            "`!mclear` - Clears all songs from the queue.\n"
            "`!mshuffle` - Cycles music mode (Shuffle -> Alpha -> Loop).\n"
            "`!playlist <subcommand>` - Manages playlists."
        )
        admin_commands = (
            "`!music` - Posts the interactive music control menu.\n"
            "`!mon` - Enables all music features and connects the bot.\n"
            "`!moff` - Disables all music features and disconnects the bot."
        )
        owner_commands = (
            "`!enable <user>` - Allows a user to use commands.\n"
            "`!disable <user>` - Prevents a user from using commands.\n"
            "`!shutdown` - Safely shuts down the bot."
        )
        
        embed = discord.Embed(title="🎵 Music Bot Commands", color=discord.Color.blue())
        embed.add_field(name="👤 User Commands", value=user_commands, inline=False)
        embed.add_field(name="🛡️ Admin Commands", value=admin_commands, inline=False)
        embed.add_field(name="👑 Owner Commands", value=owner_commands, inline=False)
        await ctx.send(embed=embed)