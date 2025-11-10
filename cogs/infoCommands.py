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
        self.api_url = "http://deepinfosukh.vercel.app/info"
        self.generate_url = "https://profile.thug4ff.com/api/profile"
        self.session = aiohttp.ClientSession()
        self.config_data = self.load_config()
        self.cooldowns = {}

    def convert_unix_timestamp(self, timestamp) -> str:
        """Safely convert Unix timestamp to readable date"""
        try:
            # Handle cases where timestamp might be "Not found" or other strings
            if isinstance(timestamp, str) and not timestamp.isdigit():
                return "Not found"
            timestamp_int = int(timestamp)
            return datetime.utcfromtimestamp(timestamp_int).strftime('%Y-%m-%d %H:%M:%S')
        except (ValueError, TypeError, OSError, OverflowError):
            return "Not found"

    def safe_get(self, data_dict, key, default="Not found"):
        """Safely get value from dictionary and handle timestamp conversion if needed"""
        value = data_dict.get(key, default)
        if value == "Not found" or value is None:
            return default
        return value

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

            # Allow all channels if no channels configured for this server
            if not allowed_channels:
                return True

            # Otherwise check if current channel is in allowed list
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
            await ctx.send(f"<a:tickkk:1425921741859065888> {channel.mention} is now allowed for `!info` commands")
        else:
            await ctx.send(f"<a:info:1428004794542329988> {channel.mention} is already allowed for `!info` commands")

    @commands.hybrid_command(name="removeinfochannel", description="Remove a channel from !info commands")
    @commands.has_permissions(administrator=True)
    async def remove_info_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        guild_id = str(ctx.guild.id)
        if guild_id in self.config_data["servers"]:
            if str(channel.id) in self.config_data["servers"][guild_id]["info_channels"]:
                self.config_data["servers"][guild_id]["info_channels"].remove(str(channel.id))
                self.save_config()
                await ctx.send(f"<a:tickkk:1425921741859065888> {channel.mention} has been removed from allowed channels")
            else:
                await ctx.send(f"<a:Cross:1115898865460203551> {channel.mention} is not in the list of allowed channels")
        else:
            await ctx.send("<a:info:1428004794542329988> This server has no saved configuration")

    @commands.hybrid_command(name="infochannels", description="List allowed channels")
    async def list_info_channels(self, ctx: commands.Context):
        guild_id = str(ctx.guild.id)

        if guild_id in self.config_data["servers"] and self.config_data["servers"][guild_id]["info_channels"]:
            channels = []
            for channel_id in self.config_data["servers"][guild_id]["info_channels"]:
                channel = ctx.guild.get_channel(int(channel_id))
                channels.append(f"<a:rflx_s:1156555221359657020> {channel.mention if channel else f'ID: {channel_id}'}")

            embed = discord.Embed(
                title="<a:server:1426187760968012008> Allowed channels for !info",
                description="\n".join(channels),
                color=discord.Color.blue()
            )
            cooldown = self.config_data["servers"][guild_id]["config"].get("cooldown", self.config_data["global_settings"]["default_cooldown"])
            embed.set_footer(text=f"<a:blackheart:1426552537879674989> Current cooldown: {cooldown} seconds")
        else:
            embed = discord.Embed(
                title="<a:server:1426187760968012008> Allowed channels for !info",
                description="<a:tick_tick:1156192844483153942> All channels are allowed (no restriction configured)",
                color=discord.Color.blue()
            )

        await ctx.send(embed=embed)

    @commands.hybrid_command(name="info", description="Displays information about a Free Fire player")
    @app_commands.describe(uid="FREE FIRE INFO")
    async def player_info(self, ctx: commands.Context, uid: str):
        guild_id = str(ctx.guild.id)

        if not uid.isdigit() or len(uid) < 6:
            return await ctx.reply("<a:Cross:1115898865460203551> Invalid UID! It must:\n- Be only numbers\n- Have at least 6 digits", mention_author=False)

        if not await self.is_channel_allowed(ctx):
            return await ctx.send("<a:Cross:1115898865460203551> This command is not allowed in this channel.", ephemeral=True)

        cooldown = self.config_data["global_settings"]["default_cooldown"]
        if guild_id in self.config_data["servers"]:
            cooldown = self.config_data["servers"][guild_id]["config"].get("cooldown", cooldown)

        if ctx.author.id in self.cooldowns:
            last_used = self.cooldowns[ctx.author.id]
            if (datetime.now() - last_used).seconds < cooldown:
                remaining = cooldown - (datetime.now() - last_used).seconds
                return await ctx.send(f"<a:info:1428004794542329988> Please wait {remaining}s before using this command again", ephemeral=True)

        self.cooldowns[ctx.author.id] = datetime.now()

        try:
            async with ctx.typing():
                async with self.session.get(f"{self.api_url}?uid={uid}") as response:
                    if response.status == 404:
                        return await ctx.send(f"<a:Cross:1115898865460203551> Player with UID `{uid}` not found.")
                    if response.status != 200:
                        return await ctx.send("<a:warningg:1428005394189516891> API error. Try again later.")
                    data = await response.json()

            basic_info = data.get('basicInfo', {})
            captain_info = data.get('captainBasicInfo', {})
            clan_info = data.get('clanBasicInfo', {})
            credit_score_info = data.get('creditScoreInfo', {})
            pet_info = data.get('petInfo', {})
            profile_info = data.get('profileInfo', {})
            social_info = data.get('socialInfo', {})

            # Use safe_get for all fields to handle "Not found" values
            region = self.safe_get(basic_info, 'region')
            nickname = self.safe_get(basic_info, 'nickname')
            level = self.safe_get(basic_info, 'level')
            exp = self.safe_get(basic_info, 'exp', '?')
            liked = self.safe_get(basic_info, 'liked')
            credit_score = self.safe_get(credit_score_info, 'creditScore')
            signature = self.safe_get(social_info, 'signature', 'None')

            embed = discord.Embed(
                title="<a:planetz:1425921073794519041> Player Information",
                color=discord.Color.blurple(),
                timestamp=datetime.now()
            )
            embed.set_thumbnail(url=ctx.author.display_avatar.url)

            embed.add_field(name="", value="\n".join([
                "**┌ <a:rflx_c:1156555179848650762> ACCOUNT BASIC INFO**",
                f"**├─ <a:rflx_d:1156555183388627044> Name**: {nickname}",
                f"**├─ <a:rflx_f:1156555186790215731> UID**: `{uid}`",
                f"**├─ <a:rflx_g:1156555190938374198> Level**: {level} (Exp: {exp})",
                f"**├─ <a:rflx_i:1156555194985893900> Region**: {region}",
                f"**├─ <a:rflx_j:1156555198551040076> Likes**: {liked}",
                f"**├─ <a:rflx_k:1156555201508032544> Honor Score**: {credit_score}",
                f"**└─ <a:rflx_l:1156555205937205258> Signature**: {signature}"
            ]), inline=False)

            # Safely handle timestamps
            create_at = self.convert_unix_timestamp(self.safe_get(basic_info, 'createAt'))
            last_login = self.convert_unix_timestamp(self.safe_get(basic_info, 'lastLoginAt'))

            embed.add_field(name="", value="\n".join([
                "**┌ <a:rflx_m:1156555208843862076> ACCOUNT ACTIVITY**",
                f"**├─ <a:rflx_p:1156555213239496734> Most Recent OB**: {self.safe_get(basic_info, 'releaseVersion', '?')}",
                f"**├─ <a:rflx_q:1156555217437991002> Current BP Badges**: {self.safe_get(basic_info, 'badgeCnt')}",
                f"**├─ <a:rflx_s:1156555221359657020> BR Rank**: {'' if basic_info.get('showBrRank') else 'Not found'} {self.safe_get(basic_info, 'rankingPoints', '?')}",
                f"**├─ <a:rflx_u:1156555226845823017> CS Rank**: {'' if basic_info.get('showCsRank') else 'Not found'} {self.safe_get(basic_info, 'csRankingPoints', '?')} ",
                f"**├─ <a:S_:1156555169513881630> Created At**: {create_at}",
                f"**└─ <a:U_:1156555176841330748> Last Login**: {last_login}"
            ]), inline=False)

            embed.add_field(name="", value="\n".join([
                "**┌ <a:nexus_crown:1426857837258084445> ACCOUNT OVERVIEW**",
                f"**├─ <:RH_red_diamond:1426858687191973908> Avatar ID**: {self.safe_get(profile_info, 'avatarId')}",
                f"**├─ <:RH_red_diamond:1426858687191973908> Banner ID**: {self.safe_get(basic_info, 'bannerId')}",
                f"**├─ <:RH_red_diamond:1426858687191973908> Pin ID**: {self.safe_get(captain_info, 'pinId', 'Default') if captain_info else 'Default'}",
                f"**└─ <:RH_red_diamond:1426858687191973908> Equipped Skills**: {self.safe_get(profile_info, 'equipedSkills')}"
            ]), inline=False)

            embed.add_field(name="", value="\n".join([
                "**┌ <a:blackheart:1426552537879674989> PET DETAILS**",
                f"**├─ <:RH_red_diamond:1426858687191973908> Equipped?**: {'<:yes_blurple:1426196883507777607>' if pet_info.get('isSelected') else '<:no_blurple:1426199509225967779>'}",
                f"**├─ <:RH_red_diamond:1426858687191973908> Pet Name**: {self.safe_get(pet_info, 'name')}",
                f"**├─ <:RH_red_diamond:1426858687191973908> Pet Exp**: {self.safe_get(pet_info, 'exp')}",
                f"**└─ <:RH_red_diamond:1426858687191973908> Pet Level**: {self.safe_get(pet_info, 'level')}"
            ]), inline=False)

            if clan_info:
                guild_info = [
                    "**┌ <a:Crown:1156196421905678356> GUILD INFO**",
                    f"**├─ <:RH_red_diamond:1426858687191973908> Guild Name**: {self.safe_get(clan_info, 'clanName')}",
                    f"**├─ <:RH_red_diamond:1426858687191973908> Guild ID**: `{self.safe_get(clan_info, 'clanId')}`",
                    f"**├─ <:RH_red_diamond:1426858687191973908> Guild Level**: {self.safe_get(clan_info, 'clanLevel')}",
                    f"**├─ <:RH_red_diamond:1426858687191973908> Live Members**: {self.safe_get(clan_info, 'memberNum')}/{self.safe_get(clan_info, 'capacity', '?')}"
                ]
                if captain_info:
                    # Safely handle captain timestamps
                    captain_last_login = self.convert_unix_timestamp(self.safe_get(captain_info, 'lastLoginAt'))
                    
                    guild_info.extend([
                        "**└─ <a:icons_crown:1426881532181741621> Leader Info**:",
                        f"    **├─ <:RH_red_diamond:1426858687191973908> Leader Name**: {self.safe_get(captain_info, 'nickname')}",
                        f"    **├─ <:RH_red_diamond:1426858687191973908> Leader UID**: `{self.safe_get(captain_info, 'accountId')}`",
                        f"    **├─ <:RH_red_diamond:1426858687191973908> Leader Level**: {self.safe_get(captain_info, 'level')} (Exp: {self.safe_get(captain_info, 'exp', '?')})",
                        f"    **├─ <:RH_red_diamond:1426858687191973908> Last Login**: {captain_last_login}",
                        f"    **├─ <:RH_red_diamond:1426858687191973908> Title**: {self.safe_get(captain_info, 'title')}",
                        f"    **├─ <:RH_red_diamond:1426858687191973908> BP Badges**: {self.safe_get(captain_info, 'badgeCnt', '?')}",
                        f"    **├─ <:RH_red_diamond:1426858687191973908> BR Rank**: {'' if captain_info.get('showBrRank') else 'Not found'} {self.safe_get(captain_info, 'rankingPoints')}",
                        f"    **└─ <:RH_red_diamond:1426858687191973908> CS Rank**: {'' if captain_info.get('showCsRank') else 'Not found'} {self.safe_get(captain_info, 'csRankingPoints')} "
                    ])
                embed.add_field(name="", value="\n".join(guild_info), inline=False)

            embed.set_footer(text="<a:developers:1426863340642373724> DEVELOPED BY SUMEDH")
            await ctx.send(embed=embed)

            # Image generation part
            region = self.safe_get(basic_info, 'region')
            if region and region != "Not found" and uid:
                try:
                    image_url = f"{self.generate_url}?uid={uid}"
                    print(f"<a:info:1428004794542329988> Image URL = {image_url}")
                    if image_url:
                        async with self.session.get(image_url) as img_file:
                            if img_file.status == 200:
                                with io.BytesIO(await img_file.read()) as buf:
                                    file = discord.File(buf, filename=f"outfit_{uuid.uuid4().hex[:8]}.png")
                                    await ctx.send(file=file)
                                    print("<a:tickkk:1425921741859065888> Image sent successfully")
                            else:
                                print(f"<a:Cross:1115898865460203551> HTTP Error: {img_file.status}")
                except Exception as e:
                    print("<a:Cross:1115898865460203551> Image generation failed:", e)

        except Exception as e:
            await ctx.send(f"<a:Cross:1115898865460203551> Unexpected error: `{e}`")
        finally:
            gc.collect()

    async def cog_unload(self):
        await self.session.close()

    async def _send_player_not_found(self, ctx, uid):
        embed = discord.Embed(
            title="<a:Cross:1115898865460203551> Player Not Found",
            description=(
                f"UID `{uid}` not found or inaccessible.\n\n"
                "<a:warningg:1428005394189516891> **Note:** IND servers are currently not working."
            ),
            color=0xE74C3C
        )
        embed.add_field(
            name="<a:info:1428004794542329988> Tip",
            value="- Make sure the UID is correct\n- Try a different UID",
            inline=False
        )
        await ctx.send(embed=embed, ephemeral=True)

    async def _send_api_error(self, ctx):
        await ctx.send(embed=discord.Embed(
            title="<a:warningg:1428005394189516891> API Error",
            description="The Free Fire API is not responding. Try again later.",
            color=0xF39C12
        ))

async def setup(bot):
    await bot.add_cog(InfoCommands(bot))
