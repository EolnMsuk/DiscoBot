# tools.py
import asyncio
import sys
import time
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import discord
from discord.ext import commands
from loguru import logger

# --- LOGGER CONFIGURATION ---
logger.remove()
logger.add(sys.stdout, colorize=True, format="<green>{time:MM-DD-YYYY HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>", enqueue=True)
logger.add("bot.log", rotation="10 MB", compression="zip", enqueue=True, level="INFO")

def handle_errors(func: Any) -> Any:
    """A decorator for centralized error handling and logging."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        ctx = None
        # Find the context object in the arguments, which could be the first or second argument
        if args:
            if isinstance(args[0], (commands.Context, discord.Interaction)):
                ctx = args[0]
            elif len(args) > 1 and isinstance(args[1], (commands.Context, discord.Interaction)):
                ctx = args[1]
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {e}", exc_info=True)
            if ctx and hasattr(ctx, "send"):
                try: await ctx.send("An unexpected error occurred. Please check the logs.", delete_after=15)
                except Exception as send_e: logger.error(f"Failed to send error message: {send_e}")
    return wrapper

ALLOWED_STATS_COMMANDS = {
    "!msearch", "!m", "!mclear", "!mshuffle", "!mpauseplay", "!mpp", "!mskip", 
    "!nowplaying", "!np", "!queue", "!q", "!playlist", "!volume", "!vol"
}

def record_command_usage(analytics: Dict[str, Any], command_name: str) -> None:
    if command_name not in ALLOWED_STATS_COMMANDS: return
    analytics["command_usage"][command_name] = analytics["command_usage"].get(command_name, 0) + 1

def record_command_usage_by_user(analytics: Dict[str, Any], user_id: int, command_name: str) -> None:
    if command_name not in ALLOWED_STATS_COMMANDS: return
    user_id_str = str(user_id) # JSON keys must be strings
    if user_id_str not in analytics["command_usage_by_user"]: analytics["command_usage_by_user"][user_id_str] = {}
    analytics["command_usage_by_user"][user_id_str][command_name] = analytics["command_usage_by_user"][user_id_str].get(command_name, 0) + 1

@dataclass
class BotConfig:
    """Holds all configuration variables for the music bot."""
    # Required Settings
    GUILD_ID: int

    # Optional Settings
    MUSIC_CONTROL_CHANNEL_ID: Optional[int]
    ALLOWED_USERS: Set[int]
    ADMIN_ROLE_NAME: List[str]
    COMMAND_COOLDOWN: int
    STATS_EXCLUDED_USERS: Set[int]
    
    # Music Settings
    MUSIC_ENABLED: bool
    MUSIC_LOCATION: Optional[str]
    MUSIC_BOT_VOLUME: float
    MUSIC_MAX_VOLUME: float
    MUSIC_SUPPORTED_FORMATS: Tuple[str, ...]
    MUSIC_DEFAULT_ANNOUNCE_SONGS: bool
    NORMALIZE_LOCAL_MUSIC: bool
    ENABLE_GLOBAL_MSKIP: bool
    GLOBAL_HOTKEY_MSKIP: str
    ENABLE_GLOBAL_MPAUSE: bool
    GLOBAL_HOTKEY_MPAUSE: str
    ENABLE_GLOBAL_MVOLUP: bool
    GLOBAL_HOTKEY_MVOLUP: str
    ENABLE_GLOBAL_MVOLDOWN: bool
    GLOBAL_HOTKEY_MVOLDOWN: str

    @staticmethod
    def from_config_module(config_module: Any) -> 'BotConfig':
        """Creates a BotConfig instance from the config.py module."""
        return BotConfig(
            # Required
            GUILD_ID=getattr(config_module, 'GUILD_ID', None),
            
            # Optional
            MUSIC_CONTROL_CHANNEL_ID=getattr(config_module, 'MUSIC_CONTROL_CHANNEL_ID', None),
            ALLOWED_USERS=set(getattr(config_module, 'ALLOWED_USERS', [])),
            ADMIN_ROLE_NAME=getattr(config_module, 'ADMIN_ROLE_NAME', []),
            COMMAND_COOLDOWN=getattr(config_module, 'COMMAND_COOLDOWN', 5),
            STATS_EXCLUDED_USERS=set(getattr(config_module, 'STATS_EXCLUDED_USERS', [])),
            
            # Music
            MUSIC_ENABLED=getattr(config_module, 'MUSIC_ENABLED', True),
            MUSIC_LOCATION=getattr(config_module, 'MUSIC_LOCATION', None),
            MUSIC_BOT_VOLUME=getattr(config_module, 'MUSIC_BOT_VOLUME', 0.2),
            MUSIC_MAX_VOLUME=getattr(config_module, 'MUSIC_MAX_VOLUME', 1.0),
            MUSIC_SUPPORTED_FORMATS=getattr(config_module, 'MUSIC_SUPPORTED_FORMATS', ('.mp3', '.flac', '.wav', '.ogg', '.m4a')),
            MUSIC_DEFAULT_ANNOUNCE_SONGS=getattr(config_module, 'MUSIC_DEFAULT_ANNOUNCE_SONGS', True),
            NORMALIZE_LOCAL_MUSIC=getattr(config_module, 'NORMALIZE_LOCAL_MUSIC', True),
            ENABLE_GLOBAL_MSKIP=getattr(config_module, 'ENABLE_GLOBAL_MSKIP', False),
            GLOBAL_HOTKEY_MSKIP=getattr(config_module, 'GLOBAL_HOTKEY_MSKIP', '`'),
            ENABLE_GLOBAL_MPAUSE=getattr(config_module, 'ENABLE_GLOBAL_MPAUSE', False),
            GLOBAL_HOTKEY_MPAUSE=getattr(config_module, 'GLOBAL_HOTKEY_MPAUSE', 'pause'),
            ENABLE_GLOBAL_MVOLUP=getattr(config_module, 'ENABLE_GLOBAL_MVOLUP', False),
            GLOBAL_HOTKEY_MVOLUP=getattr(config_module, 'GLOBAL_HOTKEY_MVOLUP', ']'),
            ENABLE_GLOBAL_MVOLDOWN=getattr(config_module, 'ENABLE_GLOBAL_MVOLDOWN', False),
            GLOBAL_HOTKEY_MVOLDOWN=getattr(config_module, 'GLOBAL_HOTKEY_MVOLDOWN', '[')
        )

# Type Aliases for BotState clarity
Cooldowns = Dict[int, Tuple[float, bool]]
AnalyticsData = Dict[str, Union[Dict[str, int], Dict[str, Dict[str, int]]]]
Playlists = Dict[str, List[Dict[str, Any]]]

@dataclass
class BotState:
    """Manages the bot's entire persistent and transient state."""
    config: BotConfig

    # Concurrency Locks
    music_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)
    cooldown_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)
    analytics_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)
    music_startup_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    # State Data
    cooldowns: Cooldowns = field(default_factory=dict)
    button_cooldowns: Cooldowns = field(default_factory=dict)
    disabled_users: Set[int] = field(default_factory=set)
    analytics: AnalyticsData = field(default_factory=lambda: {"command_usage": {}, "command_usage_by_user": {}})
    
    # Music state
    music_enabled: bool = True
    all_songs: List[str] = field(default_factory=list)
    shuffle_queue: List[str] = field(default_factory=list)
    search_queue: List[Dict[str, Any]] = field(default_factory=list)
    active_playlist: List[Dict[str, Any]] = field(default_factory=list)
    current_song: Optional[Dict[str, Any]] = None
    is_music_playing: bool = False
    is_music_paused: bool = False
    is_processing_song: bool = False
    music_mode: str = 'shuffle'
    music_volume: float = 0.2
    playlists: Playlists = field(default_factory=dict)

    # Transient state (not saved)
    announcement_context: Optional[Any] = None
    play_next_override: bool = False
    stop_after_clear: bool = False

    def __post_init__(self):
        if self.config:
            self.music_volume = self.config.MUSIC_BOT_VOLUME
            self.music_enabled = self.config.MUSIC_ENABLED

    def to_dict(self) -> dict:
        """Serializes the bot's state into a JSON-compatible dictionary."""
        def clean_song_dict(song: Optional[Dict]) -> Optional[Dict]:
            if not song: return None
            # Exclude the 'ctx' object which cannot be serialized to JSON
            return {k: v for k, v in song.items() if k != 'ctx'}
            
        return {
            "analytics": self.analytics,
            "disabled_users": list(self.disabled_users),
            "music_enabled": self.music_enabled,
            "music_mode": self.music_mode,
            "search_queue": [clean_song_dict(s) for s in self.search_queue],
            "active_playlist": [clean_song_dict(s) for s in self.active_playlist],
            "current_song": clean_song_dict(self.current_song),
            "music_volume": self.music_volume,
            "playlists": self.playlists,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], config: BotConfig) -> 'BotState':
        """Deserializes a dictionary into a BotState object."""
        state = cls(config=config)
        analytics = data.get("analytics", {"command_usage": {}, "command_usage_by_user": {}})
        # Ensure user IDs in analytics are strings for consistency
        analytics["command_usage_by_user"] = {str(k): v for k, v in analytics.get("command_usage_by_user", {}).items()}
        state.analytics = analytics
        state.disabled_users = set(data.get("disabled_users", []))
        # Music state
        state.music_enabled = data.get("music_enabled", config.MUSIC_ENABLED if config else True)
        state.music_mode = data.get("music_mode", 'shuffle')
        state.search_queue = data.get("search_queue", [])
        state.active_playlist = data.get("active_playlist", [])
        state.current_song = data.get("current_song", None)
        state.music_volume = data.get("music_volume", config.MUSIC_BOT_VOLUME if config else 0.2)
        state.playlists = data.get("playlists", {})
        return state

