import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
from datetime import datetime, timedelta
import json
import os
import asyncio
import io
import uuid
import gc
from typing import Optional, Dict, List
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('InfoCommands')

CONFIG_FILE = "info_channels.json"

class InfoCommands(commands.Cog):
    """Professional Free Fire player information bot cog"""
    
    def __init__(self, bot):
        self.bot = bot
        self.info_api_url = "https://ff-info-nine.vercel.app/info"
        self.profile_api_url = "https://profile.thug4ff.com/api/profile"
        self.profile_card_api_url = "https://profile.thug4ff.com/api/profile_card"
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={'User-Agent': 'FreeFireInfoBot/1.0'}
        )
        self.config_data = self.load_config()
        self.cooldowns = {}
        self.request_logs = {}

    def load_config(self) -> dict:
        """Load configuration with proper error handling"""
        default_config = {
            "servers": {},
            "global_settings": {
                "default_all_channels": False,
                "default_cooldown": 30,
                "default_daily_limit": 50,
                "enable_analytics": True,
                "embed_color": 0x5865F2,
                "show_profile_image": True,
                "show_profile_card": True
            }
        }

        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)
                    
                    # Merge with default config
                    merged_config = default_config.copy()
                    merged_config.update(loaded_config)
                    
                    # Ensure nested structures exist
                    merged_config.setdefault("servers", {})
                    merged_config.setdefault("global_settings", {})
                    
                    # Set default values
                    global_settings = merged_config["global_settings"]
                    for key, value in default_config["global_settings"].items():
                        global_settings.setdefault(key, value)
                    
                    return merged_config
        except (json.JSONDecodeError, IOError, KeyError) as e:
            logger.error(f"Error loading config: {e}")
            
        return default_config

    def save_config(self):
        """Save configuration with atomic write"""
        try:
            # Create backup
            if os.path.exists(CONFIG_FILE):
                backup_file = f"{CONFIG_FILE}.backup"
                if os.path.exists(backup_file):
                    os.remove(backup_file)
                os.rename(CONFIG_FILE, backup_file)
            
            # Write new config
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config_data, f, indent=4, ensure_ascii=False, sort_keys=True)
                
            logger.info("Configuration saved successfully")
        except IOError as e:
            logger.error(f"Error saving config: {e}")
            raise

    def convert_unix_timestamp(self, timestamp: int) -> str:
        """Convert Unix timestamp to readable format"""
        try:
            return datetime.utcfromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S UTC')
        except (ValueError, TypeError):
            return "Invalid timestamp"

    def log_request(self, guild_id: str, user_id: int):
        """Log user requests for rate limiting"""
        today = datetime.now().date().isoformat()
        
        if guild_id not in self.request_logs:
            self.request_logs[guild_id] = {}
            
        if today not in self.request_logs[guild_id]:
            self.request_logs[guild_id][today] = {}
            
        if user_id not in self.request_logs[guild_id][today]:
            self.request_logs[guild_id][today][user_id] = 0
            
        self.request_logs[guild_id][today][user_id] += 1

    def get_user_daily_requests(self, guild_id: str, user_id: int) -> int:
        """Get user's daily request count"""
        today = datetime.now().date().isoformat()
        return self.request_logs.get(guild_id, {}).get(today, {}).get(user_id, 0)

    def get_daily_limit(self, guild_id: str) -> int:
        """Get daily limit for a guild"""
        return self.config_data["servers"].get(guild_id, {}).get("config", {}).get(
            "daily_limit", 
            self.config_data["global_settings"]["default_daily_limit"]
        )

    async def is_channel_allowed(self, ctx) -> bool:
        """Check if command is allowed in current channel"""
        try:
            guild_id = str(ctx.guild.id)
            allowed_channels = self.config_data["servers"].get(guild_id, {}).get("info_channels", [])
            
            # Allow all channels if none configured
            if not allowed_channels:
                return True
                
            return str(ctx.channel.id) in allowed_channels
        except Exception as e:
            logger.error(f"Error checking channel permission: {e}")
            return False

    async def fetch_player_data(self, uid: str) -> Optional[dict]:
        """Fetch player data from info API"""
        try:
            async with self.session.get(f"{self.info_api_url}?uid={uid}") as response:
                if response.status == 404:
                    return None
                if response.status != 200:
                    logger.warning(f"API returned status {response.status} for UID {uid}")
                    return None
                
                data = await response.json()
                return data
                
        except aiohttp.ClientError as e:
            logger.error(f"Network error fetching player data: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching player data: {e}")
            return None

    async def generate_profile_image(self, uid: str) -> Optional[io.BytesIO]:
        """Generate profile image from profile API"""
        try:
            async with self.session.get(f"{self.profile_api_url}?uid={uid}") as response:
                if response.status == 200:
                    image_data = await response.read()
                    return io.BytesIO(image_data)
                return None
        except Exception as e:
            logger.error(f"Error generating profile image: {e}")
            return None

    async def generate_profile_card(self, uid: str) -> Optional[io.BytesIO]:
        """Generate profile card from profile card API"""
        try:
            async with self.session.get(f"{self.profile_card_api_url}?uid={uid}") as response:
                if response.status == 200:
                    image_data = await response.read()
                    return io.BytesIO(image_data)
                return None
        except Exception as e:
            logger.error(f"Error generating profile card: {e}")
            return None

    def create_player_embed(self, data: dict, uid: str, ctx) -> discord.Embed:
        """Create professional embed for player information"""
        basic_info = data.get('basicInfo', {})
        captain_info = data.get('captainBasicInfo', {})
        clan_info = data.get('clanBasicInfo', {})
        credit_score_info = data.get('creditScoreInfo', {})
        pet_info = data.get('petInfo', {})
        profile_info = data.get('profileInfo', {})
        social_info = data.get('socialInfo', {})
        
        embed_color = self.config_data["global_settings"].get("embed_color", 0x5865F2)
        
        embed = discord.Embed(
            title="🎮 Free Fire Player Information",
            color=embed_color,
            timestamp=datetime.utcnow()
        )
        
        # Set thumbnail to user avatar
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        
        # Basic Information
        embed.add_field(
            name="📋 Basic Information",
            value=(
                f"**Name:** {basic_info.get('nickname', 'N/A')}\n"
                f"**UID:** `{uid}`\n"
                f"**Level:** {basic_info.get('level', 'N/A')} (Exp: {basic_info.get('exp', 'N/A')})\n"
                f"**Region:** {basic_info.get('region', 'N/A')}\n"
                f"**Likes:** {basic_info.get('liked', 'N/A')}\n"
                f"**Honor Score:** {credit_score_info.get('creditScore', 'N/A')}"
            ),
            inline=True
        )
        
        # Account Activity
        embed.add_field(
            name="📊 Account Activity",
            value=(
                f"**Recent OB:** {basic_info.get('releaseVersion', 'N/A')}\n"
                f"**BP Badges:** {basic_info.get('badgeCnt', 'N/A')}\n"
                f"**BR Rank:** {basic_info.get('rankingPoints', 'N/A')}\n"
                f"**CS Rank:** {basic_info.get('csRankingPoints', 'N/A')}\n"
                f"**Created:** {self.convert_unix_timestamp(int(basic_info.get('createAt', 0)))}\n"
                f"**Last Login:** {self.convert_unix_timestamp(int(basic_info.get('lastLoginAt', 0)))}"
            ),
            inline=True
        )
        
        # Account Overview
        embed.add_field(
            name="🔍 Account Overview",
            value=(
                f"**Avatar ID:** {profile_info.get('avatarId', 'N/A')}\n"
                f"**Banner ID:** {basic_info.get('bannerId', 'N/A')}\n"
                f"**Pin ID:** {captain_info.get('pinId', 'Default') if captain_info else 'Default'}\n"
                f"**Equipped Skills:** {profile_info.get('equipedSkills', 'N/A')}"
            ),
            inline=False
        )
        
        # Pet Information
        if pet_info:
            embed.add_field(
                name="🐾 Pet Details",
                value=(
                    f"**Equipped:** {'✅ Yes' if pet_info.get('isSelected') else '❌ No'}\n"
                    f"**Name:** {pet_info.get('name', 'N/A')}\n"
                    f"**Level:** {pet_info.get('level', 'N/A')}\n"
                    f"**Experience:** {pet_info.get('exp', 'N/A')}"
                ),
                inline=True
            )
        
        # Guild Information
        if clan_info:
            guild_value = (
                f"**Name:** {clan_info.get('clanName', 'N/A')}\n"
                f"**ID:** `{clan_info.get('clanId', 'N/A')}`\n"
                f"**Level:** {clan_info.get('clanLevel', 'N/A')}\n"
                f"**Members:** {clan_info.get('memberNum', 'N/A')}/{clan_info.get('capacity', 'N/A')}"
            )
            
            if captain_info:
                guild_value += f"\n**Leader:** {captain_info.get('nickname', 'N/A')}"
                
            embed.add_field(
                name="🏛️ Guild Information",
                value=guild_value,
                inline=True
            )
        
        # Signature
        signature = social_info.get('signature', 'None')
        if signature and signature != 'None':
            embed.add_field(
                name="💬 Signature",
                value=f"*{signature}*",
                inline=False
            )
        
        # Footer with request info
        embed.set_footer(
            text=f"Requested by {ctx.author.display_name} • Developed by THUG",
            icon_url=ctx.author.display_avatar.url
        )
        
        return embed

    @commands.hybrid_command(name="info", description="Get detailed information about a Free Fire player")
    @app_commands.describe(uid="Free Fire Player UID")
    async def player_info(self, ctx: commands.Context, uid: str):
        """Main command to fetch Free Fire player information"""
        guild_id = str(ctx.guild.id)
        
        # Input validation
        if not uid.isdigit() or len(uid) < 6:
            embed = discord.Embed(
                title="❌ Invalid UID",
                description="UID must contain only numbers and be at least 6 digits long.",
                color=0xE74C3C
            )
            return await ctx.reply(embed=embed, mention_author=False)
        
        # Channel permission check
        if not await self.is_channel_allowed(ctx):
            embed = discord.Embed(
                title="🚫 Channel Restricted",
                description="This command is not allowed in this channel.",
                color=0xE74C3C
            )
            return await ctx.reply(embed=embed, ephemeral=True)
        
        # Cooldown check
        cooldown = self.config_data["servers"].get(guild_id, {}).get("config", {}).get(
            "cooldown", 
            self.config_data["global_settings"]["default_cooldown"]
        )
        
        if ctx.author.id in self.cooldowns:
            last_used = self.cooldowns[ctx.author.id]
            if (datetime.now() - last_used).seconds < cooldown:
                remaining = cooldown - (datetime.now() - last_used).seconds
                embed = discord.Embed(
                    title="⏳ Cooldown Active",
                    description=f"Please wait {remaining} seconds before using this command again.",
                    color=0xF39C12
                )
                return await ctx.reply(embed=embed, ephemeral=True)
        
        # Daily limit check
        daily_limit = self.get_daily_limit(guild_id)
        user_requests = self.get_user_daily_requests(guild_id, ctx.author.id)
        
        if user_requests >= daily_limit:
            embed = discord.Embed(
                title="📊 Daily Limit Reached",
                description=f"You've reached your daily limit of {daily_limit} requests. Try again tomorrow.",
                color=0xE74C3C
            )
            return await ctx.reply(embed=embed, ephemeral=True)
        
        # Update cooldown and log request
        self.cooldowns[ctx.author.id] = datetime.now()
        self.log_request(guild_id, ctx.author.id)
        
        # Send initial response
        loading_embed = discord.Embed(
            title="🔄 Fetching Player Data",
            description="Please wait while we retrieve the player information...",
            color=0xF39C12
        )
        loading_message = await ctx.reply(embed=loading_embed, mention_author=False)
        
        try:
            # Fetch player data
            async with ctx.typing():
                player_data = await self.fetch_player_data(uid)
                
                if not player_data:
                    embed = discord.Embed(
                        title="❌ Player Not Found",
                        description=f"Could not find player with UID `{uid}`.\n\n**Possible reasons:**\n- UID is incorrect\n- Player profile is private\n- Regional restrictions",
                        color=0xE74C3C
                    )
                    await loading_message.edit(embed=embed)
                    return
            
            # Create main embed
            embed = self.create_player_embed(player_data, uid, ctx)
            await loading_message.edit(embed=embed)
            
            # Generate and send profile images
            global_settings = self.config_data["global_settings"]
            
            if global_settings.get("show_profile_image", True):
                profile_image = await self.generate_profile_image(uid)
                if profile_image:
                    file = discord.File(profile_image, filename=f"profile_{uid}_{uuid.uuid4().hex[:8]}.png")
                    await ctx.send(file=file)
            
            if global_settings.get("show_profile_card", True):
                profile_card = await self.generate_profile_card(uid)
                if profile_card:
                    file = discord.File(profile_card, filename=f"card_{uid}_{uuid.uuid4().hex[:8]}.png")
                    await ctx.send(file=file)
                    
        except Exception as e:
            logger.error(f"Error in player_info command: {e}")
            embed = discord.Embed(
                title="⚠️ Unexpected Error",
                description="An error occurred while processing your request. Please try again later.",
                color=0xE74C3C
            )
            await loading_message.edit(embed=embed)
        
        finally:
            # Cleanup
            gc.collect()

    @commands.hybrid_command(name="setinfochannel", description="Allow a channel for info commands")
    @commands.has_permissions(administrator=True)
    async def set_info_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        """Set allowed channel for info commands"""
        guild_id = str(ctx.guild.id)
        self.config_data["servers"].setdefault(guild_id, {"info_channels": [], "config": {}})
        
        if str(channel.id) not in self.config_data["servers"][guild_id]["info_channels"]:
            self.config_data["servers"][guild_id]["info_channels"].append(str(channel.id))
            self.save_config()
            
            embed = discord.Embed(
                title="✅ Channel Added",
                description=f"{channel.mention} is now allowed for info commands.",
                color=0x2ECC71
            )
            await ctx.send(embed=embed)
        else:
            embed = discord.Embed(
                title="ℹ️ Channel Already Added",
                description=f"{channel.mention} is already in the allowed channels list.",
                color=0xF39C12
            )
            await ctx.send(embed=embed)

    @commands.hybrid_command(name="removeinfochannel", description="Remove a channel from info commands")
    @commands.has_permissions(administrator=True)
    async def remove_info_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        """Remove channel from allowed channels"""
        guild_id = str(ctx.guild.id)
        
        if guild_id in self.config_data["servers"]:
            if str(channel.id) in self.config_data["servers"][guild_id]["info_channels"]:
                self.config_data["servers"][guild_id]["info_channels"].remove(str(channel.id))
                self.save_config()
                
                embed = discord.Embed(
                    title="✅ Channel Removed",
                    description=f"{channel.mention} has been removed from allowed channels.",
                    color=0x2ECC71
                )
                await ctx.send(embed=embed)
            else:
                embed = discord.Embed(
                    title="❌ Channel Not Found",
                    description=f"{channel.mention} is not in the allowed channels list.",
                    color=0xE74C3C
                )
                await ctx.send(embed=embed)
        else:
            embed = discord.Embed(
                title="ℹ️ No Configuration",
                description="This server has no channel configuration.",
                color=0xF39C12
            )
            await ctx.send(embed=embed)

    @commands.hybrid_command(name="infochannels", description="List allowed channels for info commands")
    async def list_info_channels(self, ctx: commands.Context):
        """List all allowed channels"""
        guild_id = str(ctx.guild.id)
        
        if guild_id in self.config_data["servers"] and self.config_data["servers"][guild_id]["info_channels"]:
            channels = []
            for channel_id in self.config_data["servers"][guild_id]["info_channels"]:
                channel = ctx.guild.get_channel(int(channel_id))
                channels.append(f"• {channel.mention if channel else f'ID: {channel_id}'}")

            embed = discord.Embed(
                title="📋 Allowed Channels for Info Commands",
                description="\n".join(channels),
                color=0x3498DB
            )
            
            # Add configuration info
            config = self.config_data["servers"][guild_id].get("config", {})
            cooldown = config.get("cooldown", self.config_data["global_settings"]["default_cooldown"])
            daily_limit = config.get("daily_limit", self.config_data["global_settings"]["default_daily_limit"])
            
            embed.add_field(
                name="⚙️ Current Settings",
                value=f"**Cooldown:** {cooldown}s\n**Daily Limit:** {daily_limit} requests",
                inline=False
            )
        else:
            embed = discord.Embed(
                title="📋 Allowed Channels for Info Commands",
                description="All channels are allowed (no restrictions configured)",
                color=0x3498DB
            )

        await ctx.send(embed=embed)

    @commands.hybrid_command(name="infostats", description="Check your info command usage")
    async def info_stats(self, ctx: commands.Context):
        """Show user's command usage statistics"""
        guild_id = str(ctx.guild.id)
        user_requests = self.get_user_daily_requests(guild_id, ctx.author.id)
        daily_limit = self.get_daily_limit(guild_id)
        
        embed = discord.Embed(
            title="📊 Your Info Command Usage",
            color=0x9B59B6
        )
        
        embed.add_field(
            name="Today's Usage",
            value=f"**Requests:** {user_requests}/{daily_limit}",
            inline=True
        )
        
        embed.add_field(
            name="Remaining",
            value=f"**Available:** {daily_limit - user_requests} requests",
            inline=True
        )
        
        progress = (user_requests / daily_limit) * 100
        bar_length = 10
        filled = int(bar_length * (user_requests / daily_limit))
        bar = "█" * filled + "░" * (bar_length - filled)
        
        embed.add_field(
            name="Progress",
            value=f"`{bar}` {progress:.1f}%",
            inline=False
        )
        
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="infoconfig", description="Configure bot settings (Admin only)")
    @commands.has_permissions(administrator=True)
    @app_commands.describe(
        cooldown="Cooldown in seconds between commands",
        daily_limit="Daily request limit per user",
        embed_color="Embed color in hex (e.g., 5865F2)"
    )
    async def config_bot(self, ctx: commands.Context, 
                        cooldown: int = None, 
                        daily_limit: int = None,
                        embed_color: str = None):
        """Configure bot settings"""
        guild_id = str(ctx.guild.id)
        
        # Ensure server config exists
        if guild_id not in self.config_data["servers"]:
            self.config_data["servers"][guild_id] = {"info_channels": [], "config": {}}
        
        config = self.config_data["servers"][guild_id]["config"]
        changes = []
        
        # Update cooldown
        if cooldown is not None:
            if 5 <= cooldown <= 3600:  # 5 seconds to 1 hour
                config["cooldown"] = cooldown
                changes.append(f"**Cooldown:** {cooldown}s")
            else:
                await ctx.send("❌ Cooldown must be between 5 and 3600 seconds.", ephemeral=True)
                return
        
        # Update daily limit
        if daily_limit is not None:
            if 1 <= daily_limit <= 1000:  # 1 to 1000 requests
                config["daily_limit"] = daily_limit
                changes.append(f"**Daily Limit:** {daily_limit} requests")
            else:
                await ctx.send("❌ Daily limit must be between 1 and 1000.", ephemeral=True)
                return
        
        # Update embed color
        if embed_color is not None:
            try:
                # Remove # if present and convert to int
                color = int(embed_color.replace('#', ''), 16)
                config["embed_color"] = color
                changes.append(f"**Embed Color:** `#{embed_color.replace('#', '')}`")
            except ValueError:
                await ctx.send("❌ Invalid color format. Use hex like `5865F2` or `#5865F2`.", ephemeral=True)
                return
        
        if changes:
            self.save_config()
            embed = discord.Embed(
                title="✅ Configuration Updated",
                description="\n".join(changes),
                color=0x2ECC71
            )
            await ctx.send(embed=embed)
        else:
            embed = discord.Embed(
                title="⚙️ Current Configuration",
                color=0x3498DB
            )
            
            current_cooldown = config.get("cooldown", self.config_data["global_settings"]["default_cooldown"])
            current_daily_limit = config.get("daily_limit", self.config_data["global_settings"]["default_daily_limit"])
            current_color = config.get("embed_color", self.config_data["global_settings"]["embed_color"])
            
            embed.add_field(name="Cooldown", value=f"{current_cooldown}s", inline=True)
            embed.add_field(name="Daily Limit", value=f"{current_daily_limit} requests", inline=True)
            embed.add_field(name="Embed Color", value=f"`#{hex(current_color)[2:].upper()}`", inline=True)
            
            embed.set_footer(text="Use /infoconfig <cooldown> <daily_limit> <embed_color> to change settings")
            await ctx.send(embed=embed)

    async def cog_unload(self):
        """Cleanup when cog is unloaded"""
        await self.session.close()

async def setup(bot):
    """Setup function for the cog"""
    await bot.add_cog(InfoCommands(bot))
