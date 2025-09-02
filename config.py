# config.py
# This is the configuration file for the SkipCord-Music bot.
# Replace the placeholder values with your actual server and user information.

# --- ⚙️ DISCORD SERVER CONFIGURATION ⚙️ ---
# These IDs are ESSENTIAL. The bot will not work without them.
# How to get IDs: In Discord, go to User Settings > Advanced > enable Developer Mode.
# Then, right-click on your server icon, a channel, or a user and select "Copy ID."

# (Required) The ID of your Discord Server (Guild).
GUILD_ID = 123456789012345678 #

# (Required) The ID of the text channel where users will type music commands and where the bot's menu will appear.
MUSIC_CONTROL_CHANNEL_ID = 123456789012345678

# (Required) The ID of the primary voice channel where the bot will play music.
STREAMING_VC_ID = 123456789012345678 #

# --- 👑 PERMISSIONS 👑 ---
# A set of user IDs for users who should have full owner-level access to the bot (e.g., !shutdown).
# Example: ALLOWED_USERS = {987654321098765432, 123456788932464}
ALLOWED_USERS = {123456789012345678} #

# A list of role names that should have admin-level command access (e.g., !mon, !moff).
# This is case-sensitive. Example: ADMIN_ROLE_NAME = ["Moderator", "DJ"]
ADMIN_ROLE_NAME = ["Admin", "Moderator"] #

# --- 🎵 MUSIC BOT SETTINGS 🎵 ---
# Master toggle for all music features. Set to False to completely disable the music system.
MUSIC_ENABLED = True #

# The FULL path to a folder containing your local music files (e.g., "C:/Users/YourUser/Music").
# Set to None to disable local file searching.
MUSIC_LOCATION = "C:/Users/YourUser/Music" #

# The default volume for the music bot when it starts. This is a float from 0.0 (silent) to 1.0 (100%).
MUSIC_BOT_VOLUME = 0.4 #

# The maximum volume that can be set with the !vol command. Prevents users from setting the volume too high.
MUSIC_MAX_VOLUME = 2.0 #

# If True, the bot will apply audio normalization to local files to make their volume more consistent.
NORMALIZE_LOCAL_MUSIC = True #

# If True, the bot will post a "Now Playing" message in the control channel for every new song.
MUSIC_DEFAULT_ANNOUNCE_SONGS = False #

# The audio file extensions the bot will look for in your MUSIC_LOCATION.
MUSIC_SUPPORTED_FORMATS = ('.mp3', '.flac', '.wav', '.ogg', '.m4a') #

# --- ⚙️ GENERAL BOT SETTINGS ⚙️ ---
# The global cooldown in seconds between using successive commands or buttons.
COMMAND_COOLDOWN = 5 #

# (Optional) A list of additional voice channel IDs where the bot is allowed to play music.
# Example: ALT_VC_ID = [123456789012345678, 987654321098765432]
ALT_VC_ID = [] #

# (Optional) A set of user IDs to completely exclude from command usage statistics.
STATS_EXCLUDED_USERS = {123456789012345678} #

# --- ⌨️ GLOBAL HOTKEYS ⌨️ ---
# Configure system-wide keyboard shortcuts on the host machine to trigger music commands.
# See the 'keyboard' library documentation for key name formats.

ENABLE_GLOBAL_MSKIP = False #
GLOBAL_HOTKEY_MSKIP = 'end' #

ENABLE_GLOBAL_MPAUSE = False #
GLOBAL_HOTKEY_MPAUSE = 'page down' #

ENABLE_GLOBAL_MVOLUP = False #
GLOBAL_HOTKEY_MVOLUP = ']' #

ENABLE_GLOBAL_MVOLDOWN = False #
GLOBAL_HOTKEY_MVOLDOWN = '[' #