# bot.py
#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Standard library imports
import asyncio
import json
import os
import random
import re
import signal
import sys
import time
from typing import Any, Callable, Optional

# Third-party imports
import discord
import keyboard
import yt_dlp
from discord.ext import commands, tasks
from dotenv import load_dotenv
from loguru import logger
import mutagen
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

# Local application imports
try:
    import config
except ImportError:
    logger.critical("CRITICAL: config.py not found. Please create it based on the example.")
    sys.exit(1)
from helper import BotHelper
from tools import (
    BotConfig,
    BotState,
    handle_errors,
    record_command_usage,
    record_command_usage_by_user,
)

# Load environment variables from the .env file
load_dotenv()

try:
    spotify_client_id = os.getenv("SPOTIPY_CLIENT_ID")
    spotify_client_secret = os.getenv("SPOTIPY_CLIENT_SECRET")
    if spotify_client_id and spotify_client_secret:
        auth_manager = SpotifyClientCredentials(client_id=spotify_client_id, client_secret=spotify_client_secret)
        sp = spotipy.Spotify(auth_manager=auth_manager)
        logger.info("Spotify client initialized successfully.")
    else:
        sp = None
        logger.warning("Spotify credentials not found in .env. Spotify links will not work.")
except Exception as e:
    sp = None
    logger.error(f"Failed to initialize Spotify client: {e}")

# --- VALIDATION AND INITIALIZATION ---
# Load configuration from the config.py module into a structured dataclass
bot_config = BotConfig.from_config_module(config)

# Validate that all essential configuration variables have been set
required_settings = ['GUILD_ID']
missing_settings = [
    setting for setting in required_settings if not getattr(bot_config, setting)
]

if missing_settings:
    logger.critical(f"FATAL: The following required settings are missing in config.py: {', '.join(missing_settings)}")
    logger.critical("Please fill them out before starting the bot.")
    sys.exit(1)

# Initialize the bot's state management object
state = BotState(config=bot_config)

# Initialize the Discord bot instance with required intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True # Required for voice state updates
bot = commands.Bot(command_prefix="!", help_command=None, intents=intents)
bot.state = state
bot.voice_client_music = None

# --- CONSTANTS ---
STATE_FILE = "data.json"
MUSIC_METADATA_CACHE_FILE = "music_metadata_cache.json"
MUSIC_METADATA_CACHE = {}

# --- YT-DLP / FFMPEG CONFIG ---
YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'extract_flat': True,
    'nocheckcertificate': True,
    'ignoreerrors': True,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'no_playlist_index': True,
    'yes_playlist': True,
}
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -loglevel error -af "loudnorm=I=-16:LRA=11:tp=-1.5"'
}

def get_display_title_from_path(song_path: str) -> str:
    """Gets a display-friendly title from metadata or filename."""
    metadata = MUSIC_METADATA_CACHE.get(song_path)
    if metadata:
        raw_title = metadata.get('raw_title')
        raw_artist = metadata.get('raw_artist')
        if raw_title and raw_artist: return f"{raw_title} - {raw_artist}"
        elif raw_title: return raw_title
    return os.path.basename(song_path)

#########################################
# Persistence Functions
#########################################

def _save_state_sync(file_path: str, data: dict) -> None:
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def _load_state_sync(file_path: str) -> dict:
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)

async def save_state_async() -> None:
    """Asynchronously saves the current bot state to disk."""
    serializable_state = {}
    async with state.music_lock:
        serializable_state = state.to_dict()

    try:
        if serializable_state:
            await asyncio.to_thread(_save_state_sync, STATE_FILE, serializable_state)
            logger.info("Bot state saved.")
    except Exception as e:
        logger.error(f"Failed to save bot state: {e}", exc_info=True)

async def load_state_async() -> None:
    """Asynchronously loads the bot state from the JSON file if it exists."""
    global state
    if os.path.exists(STATE_FILE):
        try:
            data = await asyncio.to_thread(_load_state_sync, STATE_FILE)
            state = BotState.from_dict(data, bot_config)
            bot.state = state
            helper.state = state
            logger.info("Bot state loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load bot state: {e}", exc_info=True)
            state = BotState(config=bot_config)
            bot.state = state
    else:
        logger.info("No saved state file found, starting with a fresh state.")
        state = BotState(config=bot_config)
        bot.state = state
        helper.state = state

# Initialize the helper class
helper = BotHelper(bot, state, bot_config, save_state_async, lambda ctx=None: asyncio.create_task(play_next_song(ctx=ctx)))


@tasks.loop(minutes=14)
async def periodic_state_save() -> None:
    """Periodically saves the bot's state."""
    await save_state_async()

#########################################
# Hotkey Functions
#########################################

async def global_mskip() -> None:
    if not state.music_enabled or not bot.voice_client_music or not (bot.voice_client_music.is_playing() or bot.voice_client_music.is_paused()):
        logger.warning("Global mskip hotkey pressed, but nothing is playing or music is disabled.")
        return
    async with state.music_lock:
        if state.music_mode == 'loop':
            state.music_mode = 'shuffle'
            logger.info("Loop mode disabled via global hotkey skip. Switched to Shuffle.")
        state.is_music_paused = False
        bot.voice_client_music.stop()
    logger.info("Executed global music skip command via hotkey.")

async def global_mpause() -> None:
    if not state.music_enabled or not bot.voice_client_music or not bot.voice_client_music.is_connected():
        logger.warning("Global mpause hotkey pressed, but bot is not in VC or music is disabled.")
        return
    
    async with state.music_lock:
        if bot.voice_client_music.is_playing():
            bot.voice_client_music.pause()
            state.is_music_paused = True
            state.is_music_playing = False
            logger.info("Executed global music pause command via hotkey.")
        elif bot.voice_client_music.is_paused():
            bot.voice_client_music.resume()
            state.is_music_paused = False
            state.is_music_playing = True
            logger.info("Executed global music resume command via hotkey.")

async def global_mvolup() -> None:
    if not state.music_enabled or not bot.voice_client_music: return
    async with state.music_lock:
        new_volume = round(min(state.music_volume + 0.05, bot_config.MUSIC_MAX_VOLUME), 2)
        state.music_volume = new_volume
        if bot.voice_client_music.source:
            bot.voice_client_music.source.volume = new_volume
    logger.info(f"Volume increased to {int(state.music_volume * 100)}% via hotkey.")

async def global_mvoldown() -> None:
    if not state.music_enabled or not bot.voice_client_music: return
    async with state.music_lock:
        new_volume = round(max(state.music_volume - 0.05, 0.0), 2)
        state.music_volume = new_volume
        if bot.voice_client_music.source:
            bot.voice_client_music.source.volume = new_volume
    logger.info(f"Volume decreased to {int(state.music_volume * 100)}% via hotkey.")

#########################################
# Music Core Logic
#########################################

async def ensure_voice_connection(ctx: commands.Context) -> bool:
    """Ensures the bot is connected to the author's voice channel."""
    if not state.music_enabled: return False

    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send("You need to be in a voice channel to use music commands.", delete_after=10)
        return False

    voice_channel = ctx.author.voice.channel

    if not bot.voice_client_music or not bot.voice_client_music.is_connected():
        logger.info(f"Connecting to voice channel: {voice_channel.name}...")
        try:
            bot.voice_client_music = await voice_channel.connect(reconnect=True, timeout=60.0)
            return True
        except Exception as e:
            logger.error(f"Failed to connect to {voice_channel.name}: {e}", exc_info=True)
            await ctx.send("❌ Failed to connect to your voice channel.")
            bot.voice_client_music = None
            return False
    elif bot.voice_client_music.channel != voice_channel:
        logger.info(f"Moving to voice channel: {voice_channel.name}...")
        try:
            await bot.voice_client_music.move_to(voice_channel)
            return True
        except Exception as e:
            logger.error(f"Failed to move to {voice_channel.name}: {e}", exc_info=True)
            await ctx.send("❌ Failed to move to your voice channel.")
            return False
    
    return True # Already in the correct channel

async def scan_and_shuffle_music() -> int:
    """Scans the music directory, caches metadata, and shuffles the queue."""
    if not state.music_enabled: return 0
        
    global MUSIC_METADATA_CACHE
    if os.path.exists(MUSIC_METADATA_CACHE_FILE):
        try:
            with open(MUSIC_METADATA_CACHE_FILE, "r", encoding="utf-8") as f:
                MUSIC_METADATA_CACHE = json.load(f)
        except Exception as e: logger.error(f"Could not load persistent metadata cache: {e}")

    if not bot_config.MUSIC_LOCATION or not os.path.isdir(bot_config.MUSIC_LOCATION):
        if bot_config.MUSIC_LOCATION: logger.error(f"Music location invalid: {bot_config.MUSIC_LOCATION}")
        return 0

    def _blocking_scan_and_cache():
        supported_files, found_songs = bot_config.MUSIC_SUPPORTED_FORMATS, []
        local_metadata_cache = MUSIC_METADATA_CACHE.copy()
        for root, _, files in os.walk(bot_config.MUSIC_LOCATION):
            for file in files:
                if file.lower().endswith(supported_files):
                    song_path = os.path.join(root, file)
                    found_songs.append(song_path)
                    try:
                        file_mod_time = os.path.getmtime(song_path)
                        if song_path in local_metadata_cache and local_metadata_cache[song_path].get('mtime') == file_mod_time: continue
                        audio = mutagen.File(song_path, easy=True)
                        raw_artist, raw_title, album = (audio.get(k, [''])[0] for k in ('artist', 'title', 'album')) if audio else ('', '', '')
                        local_metadata_cache[song_path] = {
                            'artist': re.sub(r'[^a-z0-9]', '', raw_artist.lower()), 'title': re.sub(r'[^a-z0-9]', '', raw_title.lower()),
                            'album': re.sub(r'[^a-z0-9]', '', album.lower()), 'raw_artist': raw_artist, 'raw_title': raw_title, 'mtime': file_mod_time
                        }
                    except Exception as e:
                        logger.warning(f"Could not read metadata for {song_path}: {e}")
                        if song_path not in local_metadata_cache: local_metadata_cache[song_path] = {'mtime': 0}
        return found_songs, local_metadata_cache

    logger.info("Starting non-blocking music library scan...")
    found_songs, updated_metadata_cache = await asyncio.to_thread(_blocking_scan_and_cache)
    MUSIC_METADATA_CACHE = updated_metadata_cache
    logger.info("Music library scan complete.")

    async with state.music_lock:
        state.all_songs = sorted(found_songs)
        shuffled_songs = found_songs.copy()
        random.shuffle(shuffled_songs)
        state.shuffle_queue = shuffled_songs
        logger.info(f"Loaded and cached {len(state.all_songs)} songs. Shuffled {len(state.shuffle_queue)} into queue.")

    try:
        with open(MUSIC_METADATA_CACHE_FILE, "w", encoding="utf-8") as f: json.dump(MUSIC_METADATA_CACHE, f)
    except Exception as e: logger.error(f"Failed to save persistent metadata cache: {e}")
        
    return len(state.shuffle_queue)

async def _play_song(song_info: dict, ctx: commands.Context):
    """Internal function to handle the actual playback of a song."""
    async with state.music_lock: state.is_processing_song = True
    if not state.music_enabled:
        async with state.music_lock: state.is_music_playing, state.current_song, state.is_processing_song = False, None, False
        return
        
    if not await ensure_voice_connection(ctx):
        logger.error("Playback failed: Bot could not ensure voice connection.")
        async with state.music_lock: state.is_music_playing, state.current_song, state.is_processing_song = False, None, False
        return

    try:
        source, song_path_or_url, song_display_name = None, song_info['path'], song_info['title']
        async with state.music_lock: volume = state.music_volume

        if song_info.get('is_stream', False):
            single_song_ydl_opts = YDL_OPTIONS.copy(); single_song_ydl_opts['extract_flat'] = False
            with yt_dlp.YoutubeDL(single_song_ydl_opts) as ydl:
                info = await asyncio.to_thread(ydl.extract_info, song_path_or_url, download=False)
            if 'entries' in info and info['entries']: info = info['entries'][0]
            audio_url = info.get('url')
            if not audio_url: raise ValueError("yt-dlp failed to extract a playable audio URL.")
            source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(audio_url, **FFMPEG_OPTIONS), volume=volume)
            song_display_name = info.get('title', song_display_name)
            async with state.music_lock:
                if state.current_song: state.current_song['title'] = song_display_name
        else:
            options = FFMPEG_OPTIONS if state.config.NORMALIZE_LOCAL_MUSIC else {'options': '-vn -loglevel error'}
            source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(song_path_or_url, **options), volume=volume)

        # The context for the 'after' callback needs to be passed through
        after_callback = lambda e: asyncio.run_coroutine_threadsafe(play_next_song(error=e, ctx=ctx), bot.loop)
        bot.voice_client_music.play(source, after=after_callback)

        logger.info(f"Now playing: {song_display_name}")
        await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name=song_display_name))

        announcement_ctx = None
        async with state.music_lock:
            if state.announcement_context:
                announcement_ctx = state.announcement_context
                state.announcement_context = None
        
        # Use the context from the song if available, otherwise use the passed context
        effective_ctx = announcement_ctx or ctx
        if effective_ctx and bot_config.MUSIC_DEFAULT_ANNOUNCE_SONGS:
             await effective_ctx.send(f"🎵 Now Playing: **{song_display_name}**")

    except Exception as e:
        logger.critical("CRITICAL FAILURE IN _play_song.", exc_info=True)
        if ctx: await ctx.send(f"❌ **Playback Error:** Could not play `{song_info.get('title', 'Unknown')}`. Check logs.", delete_after=15)
        async with state.music_lock: state.is_music_playing, state.is_processing_song = False, False

async def start_music_playback(ctx: commands.Context):
    """A locked, centralized function to prevent race conditions when starting music."""
    if state.music_startup_lock.locked(): return
    async with state.music_startup_lock:
        if not state.music_enabled or (bot.voice_client_music and (bot.voice_client_music.is_playing() or bot.voice_client_music.is_paused())): return
        if not await ensure_voice_connection(ctx):
            logger.error("Could not start music: failed to ensure voice connection.")
            return
        is_queue_empty = False
        async with state.music_lock:
             if not state.shuffle_queue: is_queue_empty = True
        if is_queue_empty: await scan_and_shuffle_music()
        await play_next_song(ctx=ctx)

async def play_next_song(error=None, is_recursive_call=False, ctx: Optional[commands.Context] = None):
    """The 'after' callback for the music player and state machine's gatekeeper."""
    if not state.music_enabled: return
    if error: logger.error(f"Error in music player callback: {error}")

    async with state.music_lock: state.is_processing_song = False
    
    song_to_play_info, needs_library_scan = None, False

    async with state.music_lock:
        if getattr(state, 'stop_after_clear', False):
            state.stop_after_clear, state.is_music_playing, state.is_music_paused, state.current_song = False, False, False, None
            logger.info("Playback intentionally stopped after queue clear.")
            await bot.change_presence(activity=None)
            return

    # If ctx is not provided (from 'after' callback), we can't ensure connection, but we proceed
    # because the bot should already be connected. If not, _play_song will fail gracefully.
    if ctx and not await ensure_voice_connection(ctx):
        logger.critical("Music playback stopped: Could not establish a voice connection.")
        async with state.music_lock: state.is_music_playing, state.current_song = False, None
        return

    async with state.music_lock:
        # Prioritize the context from a queued song, then the passed context
        song_ctx = None
        if state.search_queue: song_ctx = state.search_queue[0].get('ctx')
        elif state.active_playlist: song_ctx = state.active_playlist[0].get('ctx')
        effective_ctx = song_ctx or ctx

        if not effective_ctx:
            logger.warning("play_next_song called without a valid context. Music cannot start/continue.")
            state.is_music_playing, state.current_song = False, None
            return

        if state.music_mode == 'loop' and state.current_song: song_to_play_info = state.current_song
        elif state.search_queue: song_to_play_info = state.search_queue.pop(0)
        elif state.active_playlist: song_to_play_info = state.active_playlist.pop(0)
        else:
            if state.music_mode == 'shuffle':
                if not state.shuffle_queue: needs_library_scan = True
                else:
                    song_path = state.shuffle_queue.pop(0)
                    song_to_play_info = {'path': song_path, 'title': get_display_title_from_path(song_path), 'is_stream': False, 'ctx': effective_ctx}
            elif state.music_mode == 'alphabetical':
                if not state.all_songs: needs_library_scan = True
                else:
                    last_path = state.current_song.get('path') if state.current_song else None
                    try: next_index = (state.all_songs.index(last_path) + 1) % len(state.all_songs)
                    except (ValueError, AttributeError): next_index = 0
                    song_path = state.all_songs[next_index]
                    song_to_play_info = {'path': song_path, 'title': get_display_title_from_path(song_path), 'is_stream': False, 'ctx': effective_ctx}

    if needs_library_scan:
        if is_recursive_call:
            logger.error("Recursive call to play_next_song detected after failed scan. Halting.")
            return
        await scan_and_shuffle_music()
        await play_next_song(is_recursive_call=True, ctx=ctx) # Pass context forward
        return

    if song_to_play_info:
        # Ensure the song has a context to play with
        song_ctx = song_to_play_info.get('ctx', ctx)
        if not song_ctx:
             logger.error("Cannot play song, context is missing.")
             return
        async with state.music_lock:
            state.is_music_playing, state.is_music_paused, state.current_song = True, False, song_to_play_info
        await _play_song(song_to_play_info, ctx=song_ctx)
    else:
        async with state.music_lock:
            state.is_music_playing, state.is_music_paused, state.current_song = False, False, None
        logger.warning("Music playback finished. All queues are empty.")
        await bot.change_presence(activity=None)

#########################################
# Decorators
#########################################

def require_user_preconditions():
    """A decorator for user-facing commands."""
    async def predicate(ctx):
        if ctx.author.id in bot_config.ALLOWED_USERS: return True
        async with state.cooldown_lock:
            if ctx.author.id in state.disabled_users:
                await ctx.send("You are currently disabled from using any commands.", delete_after=10)
                return False
        if bot_config.MUSIC_CONTROL_CHANNEL_ID and ctx.channel.id != bot_config.MUSIC_CONTROL_CHANNEL_ID:
            await ctx.send(f"All music commands must be used in <#{bot_config.MUSIC_CONTROL_CHANNEL_ID}>.", delete_after=10)
            return False
        return True
    return commands.check(predicate)

def require_admin_preconditions():
    """A decorator for admin-level commands."""
    async def predicate(ctx):
        is_allowed = ctx.author.id in bot_config.ALLOWED_USERS
        is_admin_role = isinstance(ctx.author, discord.Member) and any(role.name in bot_config.ADMIN_ROLE_NAME for role in ctx.author.roles)
        if not (is_allowed or is_admin_role):
            await ctx.send("⛔ You do not have permission to use this command.", delete_after=10)
            return False
        if is_allowed: return True
        async with state.cooldown_lock:
            if ctx.author.id in state.disabled_users:
                await ctx.send("You are currently disabled from using any commands.", delete_after=10)
                return False
        if bot_config.MUSIC_CONTROL_CHANNEL_ID and ctx.channel.id != bot_config.MUSIC_CONTROL_CHANNEL_ID:
            await ctx.send(f"All music commands must be used in <#{bot_config.MUSIC_CONTROL_CHANNEL_ID}>.", delete_after=10)
            return False
        return True
    return commands.check(predicate)

def require_allowed_user():
    """A decorator that restricts command usage to ALLOWED_USERS only."""
    async def predicate(ctx):
        if ctx.author.id in bot_config.ALLOWED_USERS: return True
        await ctx.send("⛔ This command can only be used by bot owners.")
        return False
    return commands.check(predicate)

#########################################
# Bot Event Handlers
#########################################

@bot.event
async def on_ready() -> None:
    logger.info(f"Bot is online as {bot.user}")
    try:
        await load_state_async()
        if not periodic_state_save.is_running(): periodic_state_save.start()
        if not periodic_menu_update.is_running(): periodic_menu_update.start()

        async def register_hotkey(enabled_flag: bool, key_combo: str, callback_func: Callable, name: str):
            if not enabled_flag: return
            try: await asyncio.to_thread(keyboard.remove_hotkey, key_combo)
            except (KeyError, ValueError): pass
            def callback_wrapper(): bot.loop.call_soon_threadsafe(lambda: asyncio.create_task(callback_func()))
            try:
                await asyncio.to_thread(keyboard.add_hotkey, key_combo, callback_wrapper)
                logger.info(f"Registered global {name} hotkey: {key_combo}")
            except Exception as e: logger.error(f"Failed to register {name} hotkey '{key_combo}': {e}")
        
        await register_hotkey(bot_config.ENABLE_GLOBAL_MSKIP, bot_config.GLOBAL_HOTKEY_MSKIP, global_mskip, "mskip")
        await register_hotkey(bot_config.ENABLE_GLOBAL_MPAUSE, bot_config.GLOBAL_HOTKEY_MPAUSE, global_mpause, "mpause")
        await register_hotkey(bot_config.ENABLE_GLOBAL_MVOLUP, bot_config.GLOBAL_HOTKEY_MVOLUP, global_mvolup, "mvolup")
        await register_hotkey(bot_config.ENABLE_GLOBAL_MVOLDOWN, bot_config.GLOBAL_HOTKEY_MVOLDOWN, global_mvoldown, "mvoldown")

        logger.info("Initialization complete")
    except Exception as e:
        logger.error(f"Error during on_ready: {e}", exc_info=True)

@bot.event
@handle_errors
async def on_message(message: discord.Message) -> None:
    if message.author.bot or not message.guild or message.guild.id != bot_config.GUILD_ID:
        return
    await bot.process_commands(message)

@bot.event
@handle_errors
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
    """Handles auto-disconnecting when the voice channel is empty."""
    if member.bot and member.id != bot.user.id:
        return

    if not bot.voice_client_music or not bot.voice_client_music.is_connected():
        return
        
    voice_channel = bot.voice_client_music.channel
    human_listeners = [m for m in voice_channel.members if not m.bot]

    if not human_listeners:
        logger.info(f"Channel '{voice_channel.name}' is empty of users. Disconnecting.")
        await bot.voice_client_music.disconnect()
        bot.voice_client_music = None
        async with state.music_lock:
            state.is_music_playing, state.is_music_paused, state.current_song = False, False, None
            state.search_queue.clear()
            state.active_playlist.clear()
        await bot.change_presence(activity=None)

@tasks.loop(minutes=2)
async def periodic_menu_update() -> None:
    """Periodically posts the music menu to the control channel."""
    if not bot_config.MUSIC_CONTROL_CHANNEL_ID: return # Don't run if no channel is set
    try:
        guild = bot.get_guild(bot_config.GUILD_ID)
        if not guild: return
        channel = guild.get_channel(bot_config.MUSIC_CONTROL_CHANNEL_ID)
        if not channel:
            logger.warning(f"Music control channel {bot_config.MUSIC_CONTROL_CHANNEL_ID} not found.")
            return

        two_weeks_ago = discord.utils.utcnow() - discord.Timedelta(days=14)
        try:
            # Only purge our own messages and command invocations
            await channel.purge(limit=100, check=lambda m: m.created_at > two_weeks_ago and (m.author == bot.user or m.content.startswith('!')))
        except discord.errors.Forbidden:
            logger.warning(f"Bot does not have permission to purge messages in channel {channel.name}.")
        except Exception as e:
            logger.error(f"Failed to purge control channel: {e}")
        
        await helper.send_music_menu(channel)
    except Exception as e:
        logger.error(f"Periodic menu update task failed: {e}", exc_info=True)

#########################################
# Bot Commands
#########################################

@bot.command(name='commands')
@require_admin_preconditions()
@handle_errors
async def commands_list(ctx) -> None:
    await helper.show_commands_list(ctx)

@bot.command(name='shutdown')
@require_allowed_user()
@handle_errors
async def shutdown(ctx) -> None:
    if getattr(bot, "_is_shutting_down", False): return
    await ctx.send("🛑 **Bot is shutting down...**")
    await _initiate_shutdown(ctx)

#########################################
# Music Commands
#########################################

@bot.command(name='music')
@require_admin_preconditions()
@handle_errors
async def music_command(ctx):
    if not state.music_enabled:
        await ctx.send("Music features are currently disabled. Use `!mon` to enable.", delete_after=10)
        return
    await helper.send_music_menu(ctx)

async def is_song_in_queue(state: BotState, song_path_or_url: str) -> bool:
    async with state.music_lock:
        if state.current_song and state.current_song.get('path') == song_path_or_url: return True
        all_queued_paths = {song.get('path') for song in state.active_playlist}
        all_queued_paths.update({song.get('path') for song in state.search_queue})
        return song_path_or_url in all_queued_paths

@bot.command(name='mpauseplay', aliases=['mpp'])
@require_user_preconditions()
@handle_errors
async def mpauseplay(ctx):
    if not state.music_enabled: return await ctx.send("Music features are disabled.", delete_after=10)
    if not await ensure_voice_connection(ctx): return
    
    was_stopped = False
    async with state.music_lock:
        if bot.voice_client_music.is_playing(): 
            bot.voice_client_music.pause()
            state.is_music_paused, state.is_music_playing = True, False
        elif bot.voice_client_music.is_paused(): 
            bot.voice_client_music.resume()
            state.is_music_paused, state.is_music_playing = False, True
        else: 
            was_stopped = True
            
    if was_stopped: await play_next_song(ctx=ctx)

@bot.command(name='mskip')
@require_user_preconditions()
@handle_errors
async def mskip(ctx):
    if not state.music_enabled: return await ctx.send("Music features are disabled.", delete_after=10)
    if not bot.voice_client_music or not (bot.voice_client_music.is_playing() or bot.voice_client_music.is_paused()):
        return await ctx.send("Nothing is playing to skip.", delete_after=10)
    if not await ensure_voice_connection(ctx): return

    async with state.music_lock:
        if state.music_mode == 'loop':
            state.music_mode = 'shuffle'
            await ctx.send("🔁 Loop mode disabled. Switching to 🔀 Shuffle mode.", delete_after=10)
        state.is_music_paused = False
        state.announcement_context = ctx
    bot.voice_client_music.stop()

@bot.command(name='volume', aliases=['vol'])
@require_user_preconditions()
@handle_errors
async def volume(ctx, level: int):
    if not state.music_enabled: return await ctx.send("Music features are disabled.", delete_after=10)
    if not await ensure_voice_connection(ctx): return
    if not 0 <= level <= 100: return await ctx.send(f"Volume must be between 0 and 100.", delete_after=10)
    async with state.music_lock:
        new_volume = round((level / 100) * bot_config.MUSIC_MAX_VOLUME, 2)
        state.music_volume = new_volume
        if bot.voice_client_music.source: bot.voice_client_music.source.volume = new_volume
    await ctx.send(f"Volume set to {level}%", delete_after=5)
    
def extract_youtube_url(query: str) -> Optional[str]:
    pattern = re.compile(r'(?:https?://)?(?:www\.)?(?:m\.)?(?:music\.)?(?:youtube\.com|youtu\.be)/(?:watch\?v=|embed/|v/|shorts/)?([\w-]{11})')
    match = pattern.search(query)
    if match: return f"https://www.youtube.com/watch?v={match.group(1)}"
    return None

@bot.command(name='msearch', aliases=['m'])
@require_user_preconditions()
@handle_errors
async def msearch(ctx, *, query: str):
    if not state.music_enabled: return await ctx.send("Music features are disabled.", delete_after=10)
    if not await ensure_voice_connection(ctx): return

    status_msg = await ctx.send(f"⏳ Searching for `{query}`...")
    clean_query = extract_youtube_url(query) or query
    all_hits = []
    is_youtube_search = False

    url_pattern = re.compile(r'https?://(www\.)?(youtube|youtu|soundcloud|spotify|bandcamp)\.(com|be)/.+')
    is_spotify_url = 'spotify' in clean_query.lower()
    is_generic_url = url_pattern.match(clean_query)

    if is_spotify_url:
        if not sp: return await status_msg.edit(content="❌ Spotify support is not configured.")
        await status_msg.edit(content=f"Fetching metadata from Spotify API...")
        try:
            tracks_to_search = []
            if '/track/' in clean_query: tracks_to_search.append(sp.track(clean_query))
            elif '/album/' in clean_query: tracks_to_search.extend(sp.album_tracks(clean_query)['items'])
            elif '/playlist/' in clean_query: tracks_to_search.extend(item['track'] for item in sp.playlist_tracks(clean_query)['items'] if item['track'])
            if not tracks_to_search: raise ValueError("Could not retrieve tracks from Spotify URL.")
            youtube_queries = [f"{t['artists'][0]['name']} {t['name']}" for t in tracks_to_search if t and t.get('name') and t.get('artists')]
            await status_msg.edit(content=f"⏳ Found {len(youtube_queries)} track(s). Searching on YouTube...")
            with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                for yt_query in youtube_queries:
                    try:
                        results = await asyncio.to_thread(ydl.extract_info, f"ytsearch1:{yt_query}", download=False)
                        if results and results.get('entries'):
                            video = results['entries'][0]
                            all_hits.append({'title': video.get('title'), 'path': video.get('webpage_url'), 'is_stream': True, 'ctx': ctx})
                    except Exception: logger.warning(f"Could not find YouTube match for '{yt_query}'")
        except Exception as e: return await status_msg.edit(content=f"❌ Error processing Spotify link: {e}")
        if not all_hits: return await status_msg.edit(content=f"❌ No YouTube matches found for Spotify tracks.")
    
    elif is_generic_url:
        await status_msg.edit(content=f"⏳ Processing URL...")
        try:
            with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                results = await asyncio.to_thread(ydl.extract_info, clean_query, download=False)
                if results and 'entries' in results:
                    for entry in results['entries']:
                        if entry and entry.get('url'): all_hits.append({'title': entry.get('title'), 'path': entry.get('webpage_url'), 'is_stream': True, 'ctx': ctx})
                elif results and results.get('url'):
                    all_hits.append({'title': results.get('title'), 'path': results.get('webpage_url'), 'is_stream': True, 'ctx': ctx})
        except Exception as e: logger.warning(f"URL processing for '{clean_query}' failed: {e}")

    if not all_hits:
        if not is_generic_url:
            search_terms = [re.sub(r'[^a-z0-9]', '', term) for term in clean_query.lower().split()]
            if search_terms:
                for path, meta in MUSIC_METADATA_CACHE.items():
                    metadata_str = (re.sub(r'[^a-z0-9]', '', os.path.basename(path).lower()) + meta.get('artist', '') + meta.get('title', '') + meta.get('album', ''))
                    if all(term in metadata_str for term in search_terms):
                        all_hits.append({'title': get_display_title_from_path(path), 'path': path, 'is_stream': False, 'ctx': ctx})
        if not all_hits:
            is_youtube_search = True
            try:
                with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                    results = await asyncio.to_thread(ydl.extract_info, f"ytsearch10:{clean_query}", download=False)
                    if results and 'entries' in results:
                        for entry in results['entries']:
                            if entry and entry.get('url'): all_hits.append({'title': entry.get('title'),'path': entry.get('webpage_url'),'is_stream': True,'ctx': ctx})
            except Exception as e: return await status_msg.edit(content=f"❌ YouTube search error: {e}")

    if not all_hits: return await status_msg.edit(content=f"❌ No songs found for `{query}`.")

    if (is_generic_url or is_spotify_url) and len(all_hits) >= 1:
        added_count, skipped_count, was_idle = 0, 0, False
        async with state.music_lock:
            existing_paths = {s.get('path') for s in (state.active_playlist + state.search_queue)}
            if state.current_song: existing_paths.add(state.current_song.get('path'))
            new_songs = []
            for song in all_hits:
                if song.get('path') and song['path'] not in existing_paths: new_songs.append(song); existing_paths.add(song['path'])
                else: skipped_count += 1
            if new_songs:
                state.search_queue.extend(new_songs)
                added_count = len(new_songs)
                was_idle = not (bot.voice_client_music and (bot.voice_client_music.is_playing() or bot.voice_client_music.is_paused()))
        
        response = f"✅ Added **{added_count}** songs to the queue."
        if skipped_count > 0: response += f" ({skipped_count} duplicates skipped)."
        await status_msg.edit(content=response)
        if was_idle and added_count > 0: await play_next_song(ctx=ctx)
        return

    class SearchResultsView(discord.ui.View):
        def __init__(self, hits: list, author: discord.Member, query: str, is_Youtube: bool):
            super().__init__(timeout=180.0)
            self.hits, self.author, self.query, self.is_Youtube = hits, author, query, is_Youtube
            self.message = None
            self.update_components()
        def update_components(self):
            self.clear_items()
            options = []
            if not self.is_Youtube: options.append(discord.SelectOption(label=f"Search YouTube for '{self.query[:50]}'", value="search_youtube", emoji="📺"))
            if self.hits: options.append(discord.SelectOption(label=f"Add All ({len(self.hits)})", value="add_all", emoji="➕"))
            for i, hit in enumerate(self.hits[:23]): options.append(discord.SelectOption(label=f"{i+1}. {hit['title']}"[:95], value=str(i)))
            select_menu = discord.ui.Select(placeholder="Select a song to add...", options=options)
            select_menu.callback = self.select_callback
            self.add_item(select_menu)
        async def select_callback(self, interaction: discord.Interaction):
            await interaction.response.defer()
            if interaction.user != self.author: return await interaction.followup.send("You cannot control this menu.", ephemeral=True)
            val = interaction.data['values'][0]
            if val == "search_youtube":
                await interaction.message.edit(content=f"⏳ Searching YouTube for `{self.query}`...", view=None)
                yt_hits = []
                try:
                    with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                        results = await asyncio.to_thread(ydl.extract_info, f"ytsearch10:{self.query}", download=False)
                        if 'entries' in results:
                            for entry in results['entries']:
                                if entry and entry.get('url'): yt_hits.append({'title': entry.get('title'), 'path': entry.get('webpage_url'), 'is_stream': True})
                except Exception as e: return await interaction.message.edit(content=f"❌ Error: {e}")
                if not yt_hits: return await interaction.message.edit(content=f"❌ No YouTube results for `{self.query}`.")
                new_view = SearchResultsView(yt_hits, self.author, self.query, is_Youtube=True)
                new_view.message = interaction.message; await interaction.message.edit(content="YouTube Results:", view=new_view)
                return
            
            was_idle = False
            if val == "add_all":
                songs_to_add, skipped_count = [], 0
                async with state.music_lock:
                    existing = {s.get('path') for s in (state.active_playlist + state.search_queue)}
                    if state.current_song: existing.add(state.current_song.get('path'))
                    for song in self.hits[:23]:
                        if song.get('path') and song['path'] not in existing: songs_to_add.append(song); existing.add(song['path'])
                        else: skipped_count += 1
                    if not songs_to_add: return await interaction.followup.send(f"✅ All songs on this page are already queued.", ephemeral=True)
                    state.search_queue.extend(songs_to_add)
                    was_idle = not (bot.voice_client_music and (bot.voice_client_music.is_playing() or bot.voice_client_music.is_paused()))
                msg = f"🎵 Added {len(songs_to_add)} songs."
                if skipped_count > 0: msg += f" ({skipped_count} duplicates skipped)."
                await interaction.followup.send(msg)
            else:
                song = self.hits[int(val)]
                if await is_song_in_queue(bot.state, song['path']): return await interaction.followup.send(f"⚠️ **{song['title']}** is already in the queue.", ephemeral=True)
                async with state.music_lock:
                    state.search_queue.append(song)
                    was_idle = not (bot.voice_client_music and (bot.voice_client_music.is_playing() or bot.voice_client_music.is_paused()))
                await interaction.followup.send(f"🎵 Added **{song['title']}** to the queue.")

            if was_idle:
                 # Need a context to start playback. We can get it from the interaction.
                fake_message = await interaction.channel.send("Starting playback...")
                fake_message.author = interaction.user
                ctx = await bot.get_context(fake_message)
                await fake_message.delete()
                await play_next_song(ctx=ctx)

        async def on_timeout(self):
            if self.message:
                for item in self.children: item.disabled = True
                try: await self.message.edit(content="Search menu timed out.", view=self)
                except discord.NotFound: pass

    view = SearchResultsView(all_hits, ctx.author, query=query, is_Youtube=is_youtube_search)
    view.message = await status_msg.edit(content=f"Found {len(all_hits)} results:", view=view)

@bot.command(name='mclear')
@require_user_preconditions()
@handle_errors
async def mclear(ctx):
    if not state.music_enabled: return
    await helper.confirm_and_clear_music_queue(ctx)

@bot.command(name='mshuffle')
@require_user_preconditions()
@handle_errors
async def mshuffle(ctx):
    if not state.music_enabled: return
    modes_cycle = ['shuffle', 'alphabetical', 'loop']
    display_map = {'shuffle': ('Shuffle', '🔀'), 'alphabetical': ('Alphabetical', '▶️'), 'loop': ('Loop', '🔁')}
    async with state.music_lock:
        try: current_index = modes_cycle.index(state.music_mode)
        except ValueError: current_index = -1
        new_mode = modes_cycle[(current_index + 1) % len(modes_cycle)]
        state.music_mode = new_mode
        display_name, emoji = display_map[new_mode]
    await ctx.send(f"{emoji} Music mode is now **{display_name}**.")

@bot.command(name='nowplaying', aliases=['np'])
@require_user_preconditions()
@handle_errors
async def nowplaying(ctx):
    if not state.music_enabled: return
    record_command_usage(state.analytics, "!nowplaying"); record_command_usage_by_user(state.analytics, ctx.author.id, "!nowplaying")
    await helper.show_now_playing(ctx)

@bot.command(name='queue', aliases=['q'])
@require_user_preconditions()
@handle_errors
async def queue(ctx):
    if not state.music_enabled: return
    record_command_usage(state.analytics, f"!{ctx.invoked_with}"); record_command_usage_by_user(state.analytics, ctx.author.id, f"!{ctx.invoked_with}")
    await helper.show_queue(ctx)

@bot.group(name='playlist', invoke_without_command=True)
@require_user_preconditions()
@handle_errors
async def playlist(ctx):
    if not state.music_enabled: return
    record_command_usage(state.analytics, "!playlist"); record_command_usage_by_user(state.analytics, ctx.author.id, "!playlist")
    await ctx.send("Usage: `!playlist save|load|list|delete <name>`.", delete_after=10)

@playlist.command(name='save')
@handle_errors
async def playlist_save(ctx, *, name: str):
    async with state.music_lock:
        queue_to_save = state.active_playlist + state.search_queue
        if not queue_to_save: return await ctx.send("Queue is empty.", delete_after=10)
        state.playlists[name.lower()] = list(queue_to_save)
    await ctx.send(f"✅ Playlist **{name}** saved with {len(queue_to_save)} songs.")
    await save_state_async()

@playlist.command(name='load')
@handle_errors
async def playlist_load(ctx, *, name: Optional[str] = None):
    if not name: return await ctx.send("Usage: `!playlist load <name>`", delete_after=10)
    if not await ensure_voice_connection(ctx): return

    playlist_name, added_count, skipped_count, was_idle = name.lower(), 0, 0, False
    async with state.music_lock:
        if playlist_name not in state.playlists: return await ctx.send(f"❌ Playlist **{name}** not found.", delete_after=10)
        songs_to_load = state.playlists[playlist_name]
        existing = {s.get('path') for s in (state.active_playlist + state.search_queue)}
        if state.current_song: existing.add(state.current_song.get('path'))
        new_songs = []
        for song in songs_to_load:
            # Add context to each loaded song
            song_with_ctx = song.copy()
            song_with_ctx['ctx'] = ctx
            if song_with_ctx.get('path') and song_with_ctx['path'] not in existing: 
                new_songs.append(song_with_ctx)
                existing.add(song_with_ctx['path'])
                added_count += 1
            else: skipped_count += 1
        if new_songs:
            state.search_queue.extend(new_songs)
            was_idle = not (bot.voice_client_music and (bot.voice_client_music.is_playing() or bot.voice_client_music.is_paused()))
    msg = f"✅ Playlist **{name}** loaded. Added {added_count} new songs."
    if skipped_count > 0: msg += f" Skipped {skipped_count} duplicate(s)."
    await ctx.send(msg)
    if was_idle and added_count > 0: await play_next_song(ctx=ctx)

@playlist.command(name='list')
@handle_errors
async def playlist_list(ctx):
    async with state.music_lock:
        if not state.playlists: return await ctx.send("No saved playlists.", delete_after=10)
        embed = discord.Embed(title="💾 Saved Playlists", color=discord.Color.green())
        embed.description = "\n".join([f"• **{p.capitalize()}**: {len(s)} songs" for p, s in state.playlists.items()])
    await ctx.send(embed=embed)

@playlist.command(name='delete')
@handle_errors
async def playlist_delete(ctx, *, name: str):
    playlist_name = name.lower()
    async with state.music_lock:
        if playlist_name not in state.playlists: return await ctx.send(f"❌ Playlist **{name}** not found.", delete_after=10)
        del state.playlists[playlist_name]
    await ctx.send(f"✅ Playlist **{name}** deleted.")
    await save_state_async()

async def _initiate_shutdown(ctx: Optional[commands.Context] = None):
    if getattr(bot, "_is_shutting_down", False): return
    bot._is_shutting_down = True
    logger.critical(f"Shutdown initiated by {ctx.author.name if ctx else 'system'}")
    async def unregister_hotkey(enabled, combo):
        if enabled:
            try: await asyncio.to_thread(keyboard.remove_hotkey, combo)
            except Exception: pass
    await unregister_hotkey(bot_config.ENABLE_GLOBAL_MSKIP, bot_config.GLOBAL_HOTKEY_MSKIP)
    await unregister_hotkey(bot_config.ENABLE_GLOBAL_MPAUSE, bot_config.GLOBAL_HOTKEY_MPAUSE)
    await unregister_hotkey(bot_config.ENABLE_GLOBAL_MVOLUP, bot_config.GLOBAL_HOTKEY_MVOLUP)
    await unregister_hotkey(bot_config.ENABLE_GLOBAL_MVOLDOWN, bot_config.GLOBAL_HOTKEY_MVOLDOWN)
    if bot.voice_client_music and bot.voice_client_music.is_connected():
        await bot.voice_client_music.disconnect()
    await bot.close()

@bot.command(name='moff')
@require_admin_preconditions()
@handle_errors
async def moff(ctx):
    if not state.music_enabled: return await ctx.send("Music features are already disabled.", delete_after=10)
    logger.warning(f"Music features DISABLED by {ctx.author.name}")
    state.music_enabled = False
    async with state.music_lock:
        state.search_queue.clear(); state.active_playlist.clear(); state.current_song = None
        state.is_music_playing, state.is_music_paused, state.stop_after_clear = False, False, True
        if bot.voice_client_music and (bot.voice_client_music.is_playing() or bot.voice_client_music.is_paused()):
            bot.voice_client_music.stop()
    if bot.voice_client_music and bot.voice_client_music.is_connected():
        await bot.voice_client_music.disconnect(force=True); bot.voice_client_music = None
    await bot.change_presence(activity=None)
    await ctx.send("❌ Music features have been **DISABLED**.")

@bot.command(name='mon')
@require_admin_preconditions()
@handle_errors
async def mon(ctx):
    if state.music_enabled: return await ctx.send("Music features are already enabled.", delete_after=10)
    logger.warning(f"Music features ENABLED by {ctx.author.name}")
    state.music_enabled = True
    await ctx.send("✅ Music features have been **ENABLED**.")
    # Do not auto-connect here; wait for a user command like !msearch

@bot.command(name='disable')
@require_allowed_user()
@handle_errors
async def disable(ctx, user: discord.User):
    if user.id in bot_config.ALLOWED_USERS: return await ctx.send("Cannot disable Owners.")
    async with state.cooldown_lock:
        if user.id in state.disabled_users: return await ctx.send(f"{user.mention} is already disabled.")
        state.disabled_users.add(user.id)
    await ctx.send(f"✅ {user.mention} has been **disabled** from using commands.")

@bot.command(name='enable')
@require_allowed_user()
@handle_errors
async def enable(ctx, user: discord.User):
    async with state.cooldown_lock:
        if user.id not in state.disabled_users: return await ctx.send(f"{user.mention} is not disabled.")
        state.disabled_users.remove(user.id)
    await ctx.send(f"✅ {user.mention} has been **re-enabled**.")

#########################################
# Main Execution
#########################################
if __name__ == "__main__":
    if not os.getenv("BOT_TOKEN"):
        logger.critical("Missing environment variable: BOT_TOKEN"); sys.exit(1)

    def handle_shutdown_signal(signum, _frame):
        logger.info("Graceful shutdown initiated by signal")
        if not getattr(bot, "_is_shutting_down", False):
            bot.loop.create_task(_initiate_shutdown(None))

    signal.signal(signal.SIGINT, handle_shutdown_signal)
    signal.signal(signal.SIGTERM, handle_shutdown_signal)

    try:
        bot.run(os.getenv("BOT_TOKEN"))
    except discord.LoginFailure: logger.critical("Invalid token"); sys.exit(1)
    finally:
        logger.info("Performing final state save..."); asyncio.run(save_state_async())
        logger.info("Shutdown complete")
