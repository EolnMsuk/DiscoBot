# -----------------------------------------------------------------------------------
# config.py - Configuration file for the Discord Music Bot
# -----------------------------------------------------------------------------------
# Instructions:
# 1. Fill in the GUILD_ID with your Discord server's ID.
# 2. Optionally, adjust any other settings to your preference.
# 3. Save the file as 'config.py' in the same directory as the bot.
# To find your Server ID, enable Developer Mode in Discord settings,
# then right-click your server icon and select "Copy Server ID".
# -----------------------------------------------------------------------------------

# --- REQUIRED SETTINGS ---
# The ID of the Discord server (guild) where the bot will run.
GUILD_ID = 123456789012345678 # Replace with your server's ID

# --- OPTIONAL SETTINGS ---
# If you want to restrict bot commands to a specific channel, provide its ID here.
# If set to None, commands can be used in any channel.
MUSIC_CONTROL_CHANNEL_ID = None # or e.g., 987654321098765432

# A list of user IDs who have owner-level permissions for the bot (e.g., shutdown command).
ALLOWED_USERS = [
    111111111111111111, # Replace with your user ID
]

# A list of role names that grant admin-level permissions for the bot.
ADMIN_ROLE_NAME = ["Bot Admin", "DJ"]

# The cooldown period (in seconds) for commands to prevent spam.
COMMAND_COOLDOWN = 5

# --- MUSIC SETTINGS ---
# Set to False to disable all music features globally.
MUSIC_ENABLED = True

# The local directory path where your music files are stored.
# Set to None if you only plan to stream from URLs.
MUSIC_LOCATION = None # set path to (with quotes) "C:/Users/YourUser/Music" or None to disable

# The default volume for the bot when it starts (from 0.0 to 1.0).
MUSIC_BOT_VOLUME = 0.2

# The maximum volume the bot can be set to (from 0.0 to 1.0).
MUSIC_MAX_VOLUME = 1.0

# A tuple of supported audio file extensions for local playback.
MUSIC_SUPPORTED_FORMATS = ('.mp3', '.flac', '.wav', '.ogg', '.m4a')

# Whether the bot should announce the currently playing song in the chat.
MUSIC_DEFAULT_ANNOUNCE_SONGS = True

# Whether to apply audio normalization (loudness correction) to local music files.
NORMALIZE_LOCAL_MUSIC = True


# --- GLOBAL HOTKEYS (ADVANCED) ---
# These allow you to control the bot using keyboard hotkeys on the machine running the bot.
# See the 'keyboard' library documentation for key names.
ENABLE_GLOBAL_MSKIP = False
GLOBAL_HOTKEY_MSKIP = '`'

ENABLE_GLOBAL_MPAUSE = False
GLOBAL_HOTKEY_MPAUSE = 'pause'

ENABLE_GLOBAL_MVOLUP = False
GLOBAL_HOTKEY_MVOLUP = ']'

ENABLE_GLOBAL_MVOLDOWN = False
GLOBAL_HOTKEY_MVOLDOWN = '['


