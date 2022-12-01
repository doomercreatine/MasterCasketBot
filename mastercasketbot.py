"""
    Project: Master Casket Guess Bot
    Author: DoomerCreatine <https://github.com/doomercreatine> <https://twitch.tv/doomercreatine>
    Description: Twitch chat bot that allows the streamer to start logging chatters guesses for master casket value.
                 Commands are restricted to the broadcaster.
    Basic functionality:
        ?start | Begins logging chatters guesses
        ?end | Stops logging chatters guesses
        ?winner | Takes the casket value and finds the chatter with the lowest absolute difference and tags them in chat.
"""

from email import message
from twitchio.ext import commands
import re
from config import config
import json
import datetime
import aiofiles
import subprocess
import logging
import requests
import time
from tinydb import TinyDB, Query
import pandas as pd
logging.basicConfig(format='%(asctime)s %(message)s', filename='./casket.log', encoding='utf-8', level=logging.ERROR)

class Bot(commands.Bot):

    def __init__(self):
        """
            Token and initial channels are found in config.py which is a dictionary in the format below:
            {
                'token': <TOKEN>,
                'channels': [<CHANNEL>, ...]
            }
            
            Tokens can be generated for your Twitch account at https://twitchapps.com/tmi/
            Remember to KEEP YOUR TOKEN PRIVATE! DO NOT SHARE WITH OTHERS
        """
        super().__init__(token=config['token'], prefix='?', initial_channels=config['channels'])
        self.init_setup()
        
    async def event_ready(self):
        # Notify us when everything is ready!
        # We are logged in and ready to chat and use commands...
        print(f'Logged in as | {self.nick}')
        print(f'User id is | {self.user_id}')
        print(f'Channels | {self.connected_channels}')
        logging.info(f"Bot connected as {self.nick} in channels {self.connected_channels}")
        
    @commands.command()
    async def botcheck(self, ctx: commands.Context):
        if ctx.author.is_broadcaster or ctx.author.display_name == "DoomerCreatine":

            await ctx.send(f'/me is online and running {ctx.author.display_name} POGGIES ')
            print(f'[{datetime.datetime.now().strftime("%H:%M:%S")}] {ctx.author.display_name} has checked if the bot is online in {ctx.channel.name}')

    
    @commands.command()
    @commands.cooldown(1,10,commands.Bucket.user)
    async def stats(self, ctx: commands.Context):
        if ctx.author.is_broadcaster:
            if self.casket_values:
                await ctx.send(f"Today's guesses: {self.total_guesses}. Caskets today: {len(self.casket_values)} \
                    Average casket value: {'{:,}'.format(int(sum(self.casket_values)/len(self.casket_values)))}gp HYPERS")
            else:
                await ctx.send("No caskets logged today.")

    
    """
    Function for telling the chat who won the last round and what they guessed and what the casket value was.
    """
    @commands.command()
    @commands.cooldown(1,10,commands.Bucket.user)
    async def lastwinner(self, ctx: commands.Context):
        if ctx.author.is_broadcaster:
            if self.last_winner:
                await ctx.send(f"The last winner was: {self.last_winner['name']} with a guess of {'{:,}'.format(self.last_winner['guess'])}gp on a \
                            {'{:,}'.format(self.last_winner['casket'])}gp casket.")
            else:
                await ctx.send("No winners today FeelsBadMan")
                
    @commands.command()
    async def refresh(self, ctx: commands.Context):
        if ctx.author.is_broadcaster:
            await ctx.send("Bot is being refreshed")
            self.init_setup()

        
    def init_setup(self):
        self.db = TinyDB('./updated_db.json')
        self.emote_list = self.fetch_emotes()
        self.win_list = self.load_winners()
        self.log_guesses = False
        self.current_guesses = {}
        self.current_messages = {}
        self.current_counts = {}
        self.total_guesses = 0
        self.last_winner = {'name': '', 'guess': 0, 'casket': 0}
        self.casket_values = []
        self.current_chatters = []
        self.stats_cd = False
        self.lw_cd = False
        self.tens = dict(k=1e3, m=1e6, b=1e9)
        self.punc = '''!()-[]{};:'"\,<>./?@#$%^&*_~'''
    
    def load_winners(self):
        df = pd.read_json("./updated_db.json")
        guesses = [item for item in iter(df['_default'])]
        df = pd.DataFrame(guesses,
                columns=['date', 'time', 'name', 'guess', 'casket', 'win'])
        winners = {}

        for _, item in df.iterrows():
            if item['win'] == 'yes':
                if item['name'] in winners.keys():
                    winners[item['name']] += 1
                else:
                    winners[item['name']] = 1

        return(winners)
        
    def fetch_emotes(self):
        emote_list = []
        #bttv = requests.get(
        #    "https://api.betterttv.net/2/channels/hey_jase"
        #)
   
        #ffz = requests.get(
        #    "https://api.frankerfacez.com/v1/room/hey_jase"
        #)
        
        with open("bttv.json", "r") as f:
            bttv = json.load(f)
            
        with open("ffz.json") as f:
            ffz = json.load(f)
            
        for emote in ffz['sets']['318206']['emoticons']:
            emote_list.append(emote['name'])

        for emote in bttv['emotes']:
            emote_list.append(emote['code'])
            
        self.emoji_pattern = re.compile("["
        u"\U0001F600-\U0001F64F"  # emoticons
        u"\U0001F300-\U0001F5FF"  # symbols & pictographs
        u"\U0001F680-\U0001F6FF"  # transport & map symbols
        u"\U0001F1E0-\U0001F1FF"  # flags (iOS)
                           "]+", flags=re.UNICODE)
        return(emote_list)
    


    async def emote_filter(self, text, index):
        new_text = list(text)
        if len(index)>=1:
            for idx in index:
                idx_start = int(idx.split("-")[0])
                idx_end = int(idx.split("-")[1])+1
                for i in range(idx_start, idx_end):
                    new_text[i] = ""
        emote_rem = re.sub(' +', ' ', ''.join(new_text).strip())
        emote_rem = emote_rem.replace('@','')
        emote_rem = ' '.join([word for word in emote_rem.split() if word not in self.emote_list])
        emote_rem = ' '.join([word for word in emote_rem.split() if word not in self.users])
        
        return(self.emoji_pattern.sub(r'', emote_rem))
    
    async def fetch_guess(self, message):
        # Regex to try and wrangle the guesses into a consistent int format
        formatted_v = re.search(r"(?<![\/\\aAcCdDeEfFgGhHiIjJlLnNoOpPqQrRsStTuUvVwWxXyYzZ])[0-9\s,.]+(?![\/\\aAcCdDeEfFgGhHiIjJlLnNoOpPqQrRsStTuUvVwWxXyYzZ]+\b)\s*[,.]*[kKmMbB]{0,1}\s*[0-9]*", 
                                message).group().strip()
        if formatted_v:
            formatted_v = re.sub(r',', '.', formatted_v).lower()
            # If the chatter used k, m, or b for shorthand, attempt to convert to int
            if 'k' in formatted_v or 'm' in formatted_v or 'b' in formatted_v:
                formatted_v = int(float(formatted_v[0:-1]) * self.tens[formatted_v[-1]])
            else:
                formatted_v = re.sub(r'[^\w\s]', '', formatted_v).lower()
                formatted_v = int(formatted_v)
        return(formatted_v)
        

    async def get_userlist(self):
        url = 'https://tmi.twitch.tv/group/user/hey_jase/chatters'
        chatters = json.loads(requests.get(url).text)
        current_viewers = []
        for k in chatters['chatters'].keys():
            current_viewers.append(chatters['chatters'][k])
        current_viewers = [item for sublist in current_viewers for item in sublist]
        return(current_viewers)
    
    @commands.command()
    async def start(self, ctx: commands.Context):
        if ctx.author.is_broadcaster:
            if not self.log_guesses:
                self.current_messages.clear()
                self.current_guesses.clear()
                self.current_counts.clear()
                self.users = await self.get_userlist()
                self.log_guesses = True
                await ctx.send("Guessing for Master Casket value is now OPEN! POGGIES")
                print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {ctx.author.display_name} has started logging guesses in channel: {ctx.channel.name}")
            else:
                await ctx.send("Guessing already enabled, please ?end before starting a new one.")
                
    async def event_message(self, message):
        # Messages with echo set to True are messages sent by the bot...
        # For now we just want to ignore them...
        if message.echo:
            return

        # Parse each users message and extract the guess
        if self.log_guesses and '?' not in message.content and message.author.name != 'nightbot' and message.author.name != 'lehrulesbot':
            # If chatter has not guessed, attempt to find a guess in their message
            # First let's remove all emotes from the message
            emote_idx = message.tags['emotes'].split("/")
            emote_idx = [i for i in emote_idx if i]
            if len(emote_idx) > 0:
                emote_idx = [m.split(":")[1] for m in emote_idx]
            new_message = await self.emote_filter(text=message.content, index=emote_idx)
            try:
                formatted_v = await self.fetch_guess(new_message)
                # If the user has guessed already
                if message.author.display_name in self.current_counts.keys():
                    if self.current_guesses[message.author.display_name] == formatted_v:
                        pass
                    # If user has only 1 guess, they can change it once
                    elif self.current_counts[message.author.display_name] == 1:
                        await message.channel.send(f"@{message.author.display_name}. You guessed {'{:,}'.format(self.current_guesses[message.author.display_name])}, \
                            If you want to keep {'{:,}'.format(formatted_v)} send it again.")
                        self.current_counts[message.author.display_name] += 1
                    # If they send the guess again after first message it will lock in that one
                    elif self.current_counts[message.author.display_name] == 2:
                        self.current_guesses[message.author.display_name] = formatted_v
                        self.current_counts[message.author.display_name] += 1
                # If user is not in current_counts it means they have not guessed yet
                else:
                    self.current_guesses[message.author.display_name] = formatted_v
                    self.current_counts[message.author.display_name] = 1
                    self.total_guesses += 1
            # If no regex match is detected, log that for review
            except Exception as e:
                #await message.channel.send(f"Sorry, could not parse @{message.author.display_name} guess.")
                logging.error(f"Sorry, could not parse @{message.author.display_name} guess. {message.content}")
                logging.error(e)
            self.current_messages[message.author.display_name] = message.content
                
        # Since we have commands and are overriding the default `event_message`
        # We must let the bot know we want to handle and invoke our commands...
        await self.handle_commands(message)
        
        # Closes the guess logging
    @commands.command()
    async def end(self, ctx: commands.Context):
        if ctx.author.is_broadcaster:
            if not self.log_guesses:
                await ctx.send("Guessing is not currently enabled, oops. mericCat")
                print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {ctx.author.display_name} tried to end guessing in {ctx.channel.name} but it was not started.")
            else:
                self.log_guesses = False
                await ctx.send("]=-[]=-[]=-[]=-[]=-[]=-[]=-[]=-[]=-[]=-[")
                print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {ctx.author.display_name} has ended logging guesses in channel: {ctx.channel.name}")
                
    """_summary_
    Command to determine the winner. Find the chatter who's guess was closest to the actual casket value.
    All guesses and raw messages are logged for future review.
    """
    @commands.command()
    async def winner(self, ctx: commands.Context, casket: str):
        if ctx.author.is_broadcaster:
            win_date = datetime.datetime.now().strftime("%Y%m%d")
            win_time = datetime.datetime.now().strftime("%H%M%S")
            # TODO move all of the formatting steps to a standalone function
            formatted_v = re.search(r"(?<![\/\\aAcCdDeEfFgGhHiIjJlLnNoOpPqQrRsStTuUvVwWxXyYzZ])[0-9\s,.]+(?![\/\\aAcCdDeEfFgGhHiIjJlLnNoOpPqQrRsStTuUvVwWxXyYzZ]+\b)\s*[,.]*[kKmMbB]{0,1}\s*[0-9]*", 
                                    casket).group().strip()
            formatted_v = re.sub(r',', '.', formatted_v).lower()
            # If the chatter used k, m, or b for shorthand, attempt to convert to int
            if 'k' in formatted_v or 'm' in formatted_v or 'b' in formatted_v:
                casket = int(float(formatted_v[0:-1]) * self.tens[formatted_v[-1]])
            else:
                formatted_v = re.sub(r'[^\w\s]', '', formatted_v).lower()
                casket = int(formatted_v)
        
            if not self.log_guesses:  
                self.current_guesses = {k: v for k, v in self.current_guesses.items() if v}
                if self.current_guesses:   
                    # Find minimum absolute difference between casket value and chatter guesses 
                    # TODO move this to its own function. Change the dict calls since the guesses dict will have a dict in the value slot for the key
           
                    res_key, res_val = min(self.current_guesses.items(), key=lambda x: abs(casket - x[1]))
                    winners = []
                    for key, item in self.current_guesses.items():
                        if item == res_val:
                            winners.append(key)
                        if key in self.win_list.keys():
                            self.win_list[key] += 1
                        else:
                            self.win_list[key] = 1
                    
                    await ctx.send(f"Closest guess: {' '.join([f'@{item}' for item in winners])} Clap out of {len(self.current_guesses.keys())} entries with a \
                        guess of {'{:,}'.format(res_val)} [Difference: { '{:,}'.format(abs(casket - self.current_guesses[res_key])) }]. {' | '.join([f'{item} {self.win_list[item]} win(s)' for item in winners])}  \
                            ")
                    
                    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Closest guess: {' '.join([f'@{item}' for item in winners])} Clap out of {len(self.current_guesses.keys())} entries with a guess of {'{:,}'.format(res_val)} [Difference: {abs(casket - self.current_guesses[res_key])}] {'They won last time too! jaseLFG' if res_key == self.last_winner['name'] else ''}")
                    self.last_winner['name'] = winners
                    self.last_winner['guess'] = res_val
                    self.last_winner['casket'] = casket
                    self.casket_values.append(casket)


                    for key, val in self.current_guesses.items():
                        self.db.insert({'date': win_date, 'time': win_time, 'name': key, 'guess': val, 'casket': casket, 'win': 'yes' if key in winners else 'no'})
                else:
                    # If for some reason no winner was found we need to review later. Not expected to happen with a large chat
                    await ctx.send("Something went wrong, there were no guesses saved. mericChicken")
                    
                    # Prints out to raspberry pi screen
                    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {ctx.author.display_name} tried picking a winner in {ctx.channel.name}, but no guesses were logged.")
                    
                    # casket.log
                    #logging.error(f'No guesses were found for a winner. {json.dumps([self.current_messages, self.current_guesses], indent=4)}')
                # Make sure to clear the dictionary so that past guesses aren't included
                async with aiofiles.open(f'./logging/{datetime.datetime.now().strftime("%Y%m%d-%H%M%S")}-{ctx.channel.name}.txt', 'w+') as f:
                    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {ctx.author.display_name} has chosen a winner in {ctx.channel.name}. Writing guesses to file.")
                    await f.write(json.dumps([self.current_messages, self.current_guesses, {'casket': casket}], indent=4))
  
            else:
                await ctx.send("Hey you need to ?end the guessing first 4Head")
                print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {ctx.author.display_name} tried to pick a winner in {ctx.channel.name} without ending first.")
        
bot = Bot()
bot.run()
