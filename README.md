# DyscoBot

DyscoBot is a feature-rich, high-performance Discord music bot designed for a seamless listening experience. It allows users to play music from multiple sources, manage an interactive queue, and save persistent playlists. The bot features intuitive button controls, global hotkey support, and a fully asynchronous architecture for rock-solid stability.

  - [Key Features](https://www.google.com/search?q=%23-key-features)
  - [Command List](https://www.google.com/search?q=%23-command-list)
  - [How to Setup](https://www.google.com/search?q=%23%EF%B8%8F-setup--configuration)

-----

## ✨ Key Features

### 🎵 Integrated Music System

  * **Versatile Playback**: Search and play songs, albums, or playlists from **YouTube**, **Spotify**, or local files on the host machine.
  * **Interactive Queue**: View the song queue with the `!q` command. The paginated menu allows you to browse long queues and instantly jump to any song using a convenient dropdown menu.
  * **Persistent Playlists**: Save the current queue as a named playlist, then load, list, or delete your custom playlists at any time. All playlists are saved and reloaded on bot restart.
  * **Multiple Playback Modes**: Effortlessly cycle between **Shuffle**, **Alphabetical**, and **Loop** modes to fit any mood.
  * **Intuitive Button Menus**: Control playback (`!mpauseplay`, `!mskip`) using a clean, persistent button menu that automatically refreshes in your music command channel.
  * **Automatic Management**: The bot intelligently joins a voice channel when music starts and leaves when it's empty to conserve resources.

### 🎧 High-Performance Audio & Control

  * **Global Hotkeys**: Configure system-wide keyboard shortcuts to trigger commands like `!mskip`, `!mpauseplay`, and volume controls from anywhere on the host machine, even when Discord isn't focused.
  * **Audio Normalization**: Optional loudness normalization for local music files ensures a consistent volume level between your personal library and online streams.
  * **Persistent State**: The bot's current queue, playlists, and settings are saved to `data.json`, ensuring your session is restored after a restart.
  * **Detailed Logging**: Utilizes `loguru` for detailed, color-coded logs of all commands and player activity, saved to `bot.log` for easy troubleshooting.

-----

## 📋 Command List

### 👤 User Commands

  * `!m` / `!msearch <query>`: Searches for a song, playlist, or URL to add to the queue.
  * `!q` / `!queue`: Displays the interactive song queue with a dropdown menu to jump to tracks.
  * `!np` / `!nowplaying`: Shows the currently playing song.
  * `!mskip`: Skips the current song and plays the next one in the queue.
  * `!mpp` / `!mpauseplay`: Toggles between playing and pausing the music.
  * `!mclear`: Prompts to clear all songs from the search queue and stop playback.
  * `!mshuffle`: Cycles the playback mode between **Shuffle**, **Alphabetical**, and **Loop**.
  * `!vol` / `!volume <0-100>`: Sets the music volume as a percentage.
  * `!playlist <save|load|list|delete> [name]`: Manages your saved playlists.

### 🛡️ Admin Commands

*(Requires Admin Role or being an Allowed User)*

  * `!music`: Sends the interactive music control menu to the command channel.
  * `!mon`: Enables all music features.
  * `!moff`: Disables all music features, clears the queue, and disconnects the bot.
  * `!commands`: Shows this list of all available commands.

### 👑 Owner Commands (Allowed Users Only)

  * `!disable <user>`: Prevents a specified user from using any bot commands.
  * `!enable <user>`: Re-enables a disabled user, allowing them to use commands again.
  * `!shutdown`: Safely saves the current state and shuts down the bot.

-----

## ⚙️ Setup & Configuration

### 1\. Prerequisites

  * **Python 3.9+**.
  * **FFmpeg**: Required for audio playback. Must be in your system's PATH.
  * **Dependencies**: Open a terminal or command prompt and run the following command to install the required Python libraries:
    ```bash
    pip install discord.py PyNaCl loguru python-dotenv keyboard mutagen yt-dlp spotipy
    ```

### 2\. Create a Discord Bot

1.  Go to the [Discord Developer Portal](https://discord.com/developers/applications) and create a **New Application**.
2.  Navigate to the **"Bot"** tab and enable the following **Privileged Gateway Intents**:
      * ✅ **Message Content Intent**
      * ✅ **Server Members Intent**
3.  Click **"Reset Token"** to get your bot's token. **Copy and save this token securely**.
4.  Go to **"OAuth2" -\> "URL Generator"**. Select the `bot` and `applications.commands` scopes.
5.  Under "Bot Permissions," select `Administrator`.
6.  Copy the generated URL and use it to invite the bot to your Discord server.

### 3\. Set up Spotify API (Optional)

To play songs from Spotify links, you need API credentials.

1.  Go to the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard/) and create a new app.
2.  Give it a name and description.
3.  Once created, copy your **Client ID** and **Client Secret**.

### 4\. File Setup

1.  Create a folder for your bot and place `bot.py`, `helper.py`, and `tools.py` inside.

2.  In the same folder, create a new file named `.env`.

3.  Open the `.env` file and add your credentials. Replace the placeholder text with your actual tokens.

    ```env
    # .env file
    BOT_TOKEN=YOUR_DISCORD_BOT_TOKEN_HERE
    SPOTIPY_CLIENT_ID=YOUR_SPOTIFY_CLIENT_ID_HERE
    SPOTIPY_CLIENT_SECRET=YOUR_SPOTIFY_CLIENT_SECRET_HERE
    ```

    > **Note:** `BOT_TOKEN` is required. The `SPOTIPY` lines are optional if you don't need Spotify integration.

### 5\. Configure `config.py`

Open `config.py` and fill in the values with your server's specific IDs and your preferences. To get IDs, enable Developer Mode in Discord, then right-click a server, channel, or user and select "Copy ID."

```python
# config.py

# --- REQUIRED SETTINGS ---
GUILD_ID = 123456789012345678 # Your Discord Server ID

# --- OPTIONAL SETTINGS ---
MUSIC_CONTROL_CHANNEL_ID = 123456789012345678 # Channel for music commands and menus

# --- PERMISSIONS ---
ALLOWED_USERS = [123456789012345678] # User IDs with full bot owner access
ADMIN_ROLE_NAME = ["Admin", "DJ"] # Roles that can use admin commands

# --- MUSIC BOT SETTINGS ---
MUSIC_ENABLED = True                       # Master toggle for all music features
MUSIC_LOCATION = "C:/Users/YourUser/Music" # Path to local music files (or None to disable)
MUSIC_BOT_VOLUME = 0.2                     # Default volume (0.0 to 1.0)
MUSIC_MAX_VOLUME = 1.0                     # Max volume for the !vol command (1.0 = 100%)
NORMALIZE_LOCAL_MUSIC = True               # Apply volume normalization to local files
MUSIC_DEFAULT_ANNOUNCE_SONGS = True        # Announce every new song in chat
MUSIC_SUPPORTED_FORMATS = ('.mp3', '.flac', '.wav', '.ogg', '.m4a')

# --- GLOBAL HOTKEYS ---
ENABLE_GLOBAL_MSKIP = False
GLOBAL_HOTKEY_MSKIP = '`'
ENABLE_GLOBAL_MPAUSE = False
GLOBAL_HOTKEY_MPAUSE = 'pause'
ENABLE_GLOBAL_MVOLUP = False
GLOBAL_HOTKEY_MVOLUP = ']'
ENABLE_GLOBAL_MVOLDOWN = False
GLOBAL_HOTKEY_MVOLDOWN = '['
```

-----

## Running the Bot

1.  Open your command prompt or terminal.
2.  Navigate to the bot's folder using `cd path/to/your/bot`.
3.  Run the bot with the command:
    ```bash
    python bot.py
    ```

### Troubleshooting

  * **Token Error**: Make sure your `.env` file is in the same folder as `bot.py` and contains the correct token.
  * **Music Doesn't Play**: Ensure **FFmpeg** is installed and its folder is added to your system's PATH.
  * **Spotify Links Fail**: Double-check your `SPOTIPY_CLIENT_ID` and `SPOTIPY_CLIENT_SECRET` in the `.env` file.
  * **Other Issues**: Check the `bot.log` file in the bot's folder for detailed error messages.
