import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
from datetime import datetime
import json
import os
import asyncio
import io
import uuid
import gc
from datetime import datetime

CONFIG_FILE = "info_channels.json"


class InfoCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.api_url = "http://raw.thug4ff.com/info"
        self.generate_url = "https://profile.thug4ff.com/api/profile"
        self.session = aiohttp.ClientSession()
        self.config_data = self.load_config()
        self.cooldowns = {}

    # Custom emojis dictionary
    EMOJIS = {
        "success": "<a:tickkk:1425921741859065888>",
        "info": "<a:info:1428004794542329988>",
        "warning": "<a:warningg:1428005394189516891>",
        "error": "<a:Cross:1115898865460203551>",
        "diamond": "<a:RH_red_diamond:1426858687191973908>",
        "sword": "<a:sword:1425920542283792454>",
        "crown": "<a:Crown:1156196421905678356>",
        "server": "<a:server:1426187760968012008>",
        "verify": "<a:verify:1426189197282377749>",
        "developer": "<a:developers:1437474706436526110>",
        "music": "<a:Musicz:1425914953059139645>",
        "planet": "<a:planetz:1425921073794519041>",
        "friends": "<a:friends:1426860993874624597>",
        "general": "<a:general:1426192503656157285>",
        "moon": "<:moon:1425919313470292102>",
        "heart": "<a:blackheart:1426552537879674989>",
        "thunder": "<a:Black_Thunder:1426549197489831967>",
        "mic": "<:icons_mic:1426851311391080468>",
        "tick": "<a:tick_tick:1156192844483153942>",
        "nexus_crown": "<:nexus_crown:1426857837258084445>",
        "nexus_mod": "<:nexus_mod:1425916239598981183>",
        "vip": "<:vip:1426883326417043497>",
        "yes": "<:yes_blurple:1426196883507777607>",
        "no": "<:no_blurple:1426199509225967779>",
        "tick_icon": "<:tick_icons:1426853626328121396>",
        "wumpus": "<a:Discord_WumpusWave:1425919940485189855>",
        "giveaway": "<a:nexus_giveaways:1425847077564448931>",
        "ticket": "<:nexus_Ticket:1425916239598981183>",
        "commands": "<:CommandsList:1425915564404248596>",
        "butterfly": "<:black_butterfly:1426194247769395371>",
        "automod": "<:automod:1426886073287442433>",
        "co_owner": "<:co_owner:1426885640620081285>"
    }

    def convert_unix_timestamp(self, timestamp: int) -> str:
        return datetime.utcfromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')

    def check_request_limit(self, guild_id):
        try:
            return self.is_server_subscribed(guild_id) or not self.is_limit_reached(guild_id)
        except Exception as e:
            print(f"Error checking request limit: {e}")
            return False

    def load_config(self):
        default_config = {
            "servers": {},
            "global_settings": {
                "default_all_channels": False,
                "default_cooldown": 30,
                "default_daily_limit": 30
            }
        }

        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    loaded_config = json.load(f)
                    loaded_config.setdefault("global_settings", {})
                    loaded_config["global_settings"].setdefault("default_all_channels", False)
                    loaded_config["global_settings"].setdefault("default_cooldown", 30)
                    loaded_config["global_settings"].setdefault("default_daily_limit", 30)
                    loaded_config.setdefault("servers", {})
                    return loaded_config
            except (json.JSONDecodeError, IOError) as e:
                print(f"Error loading config: {e}")
                return default_config
        return default_config

    def save_config(self):
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config_data, f, indent=4, ensure_ascii=False)
        except IOError as e:
            print(f"Error saving config: {e}")

    async def is_channel_allowed(self, ctx):
        try:
            guild_id = str(ctx.guild.id)
            allowed_channels = self.config_data["servers"].get(guild_id, {}).get("info_channels", [])

            if not allowed_channels:
                return True

            return str(ctx.channel.id) in allowed_channels
        except Exception as e:
            print(f"Error checking channel permission: {e}")
            return False

    @commands.hybrid_command(name="setinfochannel", description="Allow a channel for !info commands")
    @commands.has_permissions(administrator=True)
    async def set_info_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        guild_id = str(ctx.guild.id)
        self.config_data["servers"].setdefault(guild_id, {"info_channels": [], "config": {}})
        if str(channel.id) not in self.config_data["servers"][guild_id]["info_channels"]:
            self.config_data["servers"][guild_id]["info_channels"].append(str(channel.id))
            self.save_config()
            await ctx.send(f"{self.EMOJIS['success']} {channel.mention} is now allowed for `!info` commands")
        else:
            await ctx.send(f"{self.EMOJIS['info']} {channel.mention} is already allowed for `!info` commands")

    @commands.hybrid_command(name="removeinfochannel", description="Remove a channel from !info commands")
    @commands.has_permissions(administrator=True)
    async def remove_info_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        guild_id = str(ctx.guild.id)
        if guild_id in self.config_data["servers"]:
            if str(channel.id) in self.config_data["servers"][guild_id]["info_channels"]:
                self.config_data["servers"][guild_id]["info_channels"].remove(str(channel.id))
                self.save_config()
                await ctx.send(f"{self.EMOJIS['success']} {channel.mention} has been removed from allowed channels")
            else:
                await ctx.send(f"{self.EMOJIS['error']} {channel.mention} is not in the list of allowed channels")
        else:
            await ctx.send(f"{self.EMOJIS['info']} This server has no saved configuration")

    @commands.hybrid_command(name="infochannels", description="List allowed channels")
    async def list_info_channels(self, ctx: commands.Context):
        guild_id = str(ctx.guild.id)

        if guild_id in self.config_data["servers"] and self.config_data["servers"][guild_id]["info_channels"]:
            channels = []
            for channel_id in self.config_data["servers"][guild_id]["info_channels"]:
                channel = ctx.guild.get_channel(int(channel_id))
                channels.append(f"{self.EMOJIS['diamond']} {channel.mention if channel else f'ID: {channel_id}'}")

            embed = discord.Embed(
                title=f"{self.EMOJIS['server']} Allowed channels for !info",
                description="\n".join(channels),
                color=discord.Color.blue()
            )
            cooldown = self.config_data["servers"][guild_id]["config"].get("cooldown", self.config_data["global_settings"]["default_cooldown"])
            embed.set_footer(text=f"{self.EMOJIS['tick']} Current cooldown: {cooldown} seconds")
        else:
            embed = discord.Embed(
                title=f"{self.EMOJIS['server']} Allowed channels for !info",
                description=f"{self.EMOJIS['info']} All channels are allowed (no restriction configured)",
                color=discord.Color.blue()
            )

        await ctx.send(embed=embed)

    @commands.hybrid_command(name="info", description="Displays information about a Free Fire player")
    @app_commands.describe(uid="FREE FIRE INFO")
    async def player_info(self, ctx: commands.Context, uid: str):
        guild_id = str(ctx.guild.id)

        if not uid.isdigit() or len(uid) < 6:
            return await ctx.reply(f"{self.EMOJIS['error']} Invalid UID! It must:\n{self.EMOJIS['diamond']} Be only numbers\n{self.EMOJIS['diamond']} Have at least 6 digits", mention_author=False)

        if not await self.is_channel_allowed(ctx):
            return await ctx.send(f"{self.EMOJIS['error']} This command is not allowed in this channel.", ephemeral=True)

        cooldown = self.config_data["global_settings"]["default_cooldown"]
        if guild_id in self.config_data["servers"]:
            cooldown = self.config_data["servers"][guild_id]["config"].get("cooldown", cooldown)

        if ctx.author.id in self.cooldowns:
            last_used = self.cooldowns[ctx.author.id]
            if (datetime.now() - last_used).seconds < cooldown:
                remaining = cooldown - (datetime.now() - last_used).seconds
                return await ctx.send(f"{self.EMOJIS['warning']} Please wait {remaining}s before using this command again", ephemeral=True)

        self.cooldowns[ctx.author.id] = datetime.now()

        try:
            async with ctx.typing():
                async with self.session.get(f"{self.api_url}?uid={uid}") as response:
                    if response.status == 404:
                        return await ctx.send(f"{self.EMOJIS['error']} Player with UID `{uid}` not found.")
                    if response.status != 200:
                        return await ctx.send(f"{self.EMOJIS['error']} API error. Try again later.")
                    data = await response.json()

            basic_info = data.get('basicInfo', {})
            captain_info = data.get('captainBasicInfo', {})
            clan_info = data.get('clanBasicInfo', {})
            credit_score_info = data.get('creditScoreInfo', {})
            pet_info = data.get('petInfo', {})
            profile_info = data.get('profileInfo', {})
            social_info = data.get('socialInfo', {})

            region = basic_info.get('region', 'Not found')

            embed = discord.Embed(
                title=f"{self.EMOJIS['nexus_crown']} Player Information",
                color=discord.Color.blurple(),
                timestamp=datetime.now()
            )
            embed.set_thumbnail(url=ctx.author.display_avatar.url)

            # Basic Info Section
            embed.add_field(name="", value="\n".join([
                f"**┌ {self.EMOJIS['server']} ACCOUNT BASIC INFO**",
                f"**├ {self.EMOJIS['diamond']} Name**: {basic_info.get('nickname', 'Not found')}",
                f"**├ {self.EMOJIS['diamond']} UID**: `{uid}`",
                f"**├ {self.EMOJIS['diamond']} Level**: {basic_info.get('level', 'Not found')} (Exp: {basic_info.get('exp', '?')})",
                f"**├ {self.EMOJIS['diamond']} Region**: {region}",
                f"**├ {self.EMOJIS['diamond']} Likes**: {basic_info.get('liked', 'Not found')}",
                f"**├ {self.EMOJIS['diamond']} Honor Score**: {credit_score_info.get('creditScore', 'Not found')}",
                f"**└ {self.EMOJIS['diamond']} Signature**: {social_info.get('signature', 'None') or 'None'}"
            ]), inline=False)

            # Account Activity Section
            embed.add_field(name="", value="\n".join([
                f"**┌ {self.EMOJIS['thunder']} ACCOUNT ACTIVITY**",
                f"**├ {self.EMOJIS['diamond']} Most Recent OB**: {basic_info.get('releaseVersion', '?')}",
                f"**├ {self.EMOJIS['diamond']} Current BP Badges**: {basic_info.get('badgeCnt', 'Not found')}",
                f"**├ {self.EMOJIS['diamond']} BR Rank**: {self.EMOJIS['yes'] if basic_info.get('showBrRank') else self.EMOJIS['no']} {basic_info.get('rankingPoints', '?')}",
                f"**├ {self.EMOJIS['diamond']} CS Rank**: {self.EMOJIS['yes'] if basic_info.get('showCsRank') else self.EMOJIS['no']} {basic_info.get('csRankingPoints', '?')}",
                f"**├ {self.EMOJIS['diamond']} Created At**: {self.convert_unix_timestamp(int(basic_info.get('createAt', 'Not found')))}",
                f"**└ {self.EMOJIS['diamond']} Last Login**: {self.convert_unix_timestamp(int(basic_info.get('lastLoginAt', 'Not found')))}"
            ]), inline=False)

            # Account Overview Section
            embed.add_field(name="", value="\n".join([
                f"**┌ {self.EMOJIS['nexus_crown']} ACCOUNT OVERVIEW**",
                f"**├ {self.EMOJIS['diamond']} Avatar ID**: {profile_info.get('avatarId', 'Not found')}",
                f"**├ {self.EMOJIS['diamond']} Banner ID**: {basic_info.get('bannerId', 'Not found')}",
                f"**├ {self.EMOJIS['diamond']} Pin ID**: {captain_info.get('pinId', 'Not found') if captain_info else 'Default'}",
                f"**└ {self.EMOJIS['diamond']} Equipped Skills**: {profile_info.get('equipedSkills', 'Not found')}"
            ]), inline=False)

            # Pet Details Section
            embed.add_field(name="", value="\n".join([
                f"**┌ {self.EMOJIS['heart']} PET DETAILS**",
                f"**├ {self.EMOJIS['diamond']} Equipped?**: {self.EMOJIS['yes'] if pet_info.get('isSelected') else self.EMOJIS['no']}",
                f"**├ {self.EMOJIS['diamond']} Pet Name**: {pet_info.get('name', 'Not Found')}",
                f"**├ {self.EMOJIS['diamond']} Pet Exp**: {pet_info.get('exp', 'Not Found')}",
                f"**└ {self.EMOJIS['diamond']} Pet Level**: {pet_info.get('level', 'Not Found')}"
            ]), inline=False)

            # Guild Info Section
            if clan_info:
                guild_info = [
                    f"**┌ {self.EMOJIS['crown']} GUILD INFO**",
                    f"**├ {self.EMOJIS['diamond']} Guild Name**: {clan_info.get('clanName', 'Not found')}",
                    f"**├ {self.EMOJIS['diamond']} Guild ID**: `{clan_info.get('clanId', 'Not found')}`",
                    f"**├ {self.EMOJIS['diamond']} Guild Level**: {clan_info.get('clanLevel', 'Not found')}",
                    f"**├ {self.EMOJIS['diamond']} Live Members**: {clan_info.get('memberNum', 'Not found')}/{clan_info.get('capacity', '?')}"
                ]
                if captain_info:
                    guild_info.extend([
                        f"**└ {self.EMOJIS['vip']} Leader Info**:",
                        f"    **├ {self.EMOJIS['diamond']} Leader Name**: {captain_info.get('nickname', 'Not found')}",
                        f"    **├ {self.EMOJIS['diamond']} Leader UID**: `{captain_info.get('accountId', 'Not found')}`",
                        f"    **├ {self.EMOJIS['diamond']} Leader Level**: {captain_info.get('level', 'Not found')} (Exp: {captain_info.get('exp', '?')})",
                        f"    **├ {self.EMOJIS['diamond']} Last Login**: {self.convert_unix_timestamp(int(captain_info.get('lastLoginAt', 'Not found')))}",
                        f"    **├ {self.EMOJIS['diamond']} Title**: {captain_info.get('title', 'Not found')}",
                        f"    **├ {self.EMOJIS['diamond']} BP Badges**: {captain_info.get('badgeCnt', '?')}",
                        f"    **├ {self.EMOJIS['diamond']} BR Rank**: {self.EMOJIS['yes'] if captain_info.get('showBrRank') else self.EMOJIS['no']} {captain_info.get('rankingPoints', 'Not found')}",
                        f"    **└ {self.EMOJIS['diamond']} CS Rank**: {self.EMOJIS['yes'] if captain_info.get('showCsRank') else self.EMOJIS['no']} {captain_info.get('csRankingPoints', 'Not found')}"
                    ])
                embed.add_field(name="", value="\n".join(guild_info), inline=False)

            embed.set_footer(text=f"{self.EMOJIS['null']} DEVELOPED BY SUMEDH")
            await ctx.send(embed=embed)

            # Generate and send profile image
            if region and uid:
                try:
                    image_url = f"{self.generate_url}?uid={uid}"
                    print(f"Image URL = {image_url}")
                    if image_url:
                        async with self.session.get(image_url) as img_file:
                            if img_file.status == 200:
                                with io.BytesIO(await img_file.read()) as buf:
                                    file = discord.File(buf, filename=f"outfit_{uuid.uuid4().hex[:8]}.png")
                                    await ctx.send(file=file)
                                    print(f"{self.EMOJIS['success']} Image sent successfully")
                            else:
                                print(f"{self.EMOJIS['error']} HTTP Error: {img_file.status}")
                except Exception as e:
                    print(f"{self.EMOJIS['error']} Image generation failed: {e}")

        except Exception as e:
            await ctx.send(f"{self.EMOJIS['error']} Unexpected error: `{e}`")
        finally:
            gc.collect()

    async def cog_unload(self):
        await self.session.close()

    async def _send_player_not_found(self, ctx, uid):
        embed = discord.Embed(
            title=f"{self.EMOJIS['error']} Player Not Found",
            description=(
                f"UID `{uid}` not found or inaccessible.\n\n"
                f"{self.EMOJIS['warning']} **Note:** IND servers are currently not working."
            ),
            color=0xE74C3C
        )
        embed.add_field(
            name=f"{self.EMOJIS['info']} Tip",
            value=f"{self.EMOJIS['diamond']} Make sure the UID is correct\n{self.EMOJIS['diamond']} Try a different UID",
            inline=False
        )
        await ctx.send(embed=embed, ephemeral=True)

    async def _send_api_error(self, ctx):
        await ctx.send(embed=discord.Embed(
            title=f"{self.EMOJIS['warning']} API Error",
            description="The Free Fire API is not responding. Try again later.",
            color=0xF39C12
        ))

async def setup(bot):
    await bot.add_cog(InfoCommands(bot))
