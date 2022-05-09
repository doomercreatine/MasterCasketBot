# MasterCasketBot
A Twitch chatbot for handling guesses for master casket loot

# About
This is a Twitch bot built off [TwitchIO](https://github.com/TwitchIO/TwitchIO). The purpose of this bot is for the casket opening streams on the [Hey_Jase Twitch Streams](https://twitch.tv/hey_jase). As a basic overview the broadcaster will trigger the bot to start logging "casket value guesses" for a time. Then the broadcaster will end the logging and declare the true casket value. The bot will determine who had a guess that was closest to the actual value and shout them out in the chat.

# Set up
In order to set up a bot of your own you will need a [Twitch](https://twitch.tv) accounts. Then you will need to generate an oauth token at https://twitchapps.com/tmi/ (you will only need the code after `oauth:`). Then you will need to add this information to `config.py`. For `channels` this is a list of channel you want the bot to reside in.

## Running
As the broadcaster you will follow the below steps:

1. `?start` | This triggers the bot to begin logging guesses.
2. `?end` | This triggers the bot to end logging.
3. `?winner <number>` | This declares the true casket value. This can be an `<INT>` or shorthand number formats like `100k | 100,000 | 100.000`

## Broadcaster commands

1. `?stats` | Display stats for the current livestream. This will display how many guesses have been logged cumulatively as well as how many caskets have been opened and their average value.
2. `?lastwinner` | Displays who won the last round of guessing.

## Data retention
All guesses and casket values are stored to a `TinyDB` JSON database. Future plans include linking this to an interactive dashboard that would allow users to view all guesses in the channel and seeing who has the closest guesses of all time. Features would include filtering by username, date, casket values, etc. 

## Hardware
The bot is currently run off a Raspberry Pi system with Raspbian OS. However, it could be run on just about any system with a stable internet and power connection.
