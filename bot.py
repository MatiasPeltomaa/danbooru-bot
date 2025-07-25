import os
import re
import json
import discord
import aiohttp
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
DANBOORU_LOGIN = os.getenv('DANBOORU_LOGIN')
DANBOORU_API_KEY = os.getenv('DANBOORU_API_KEY')

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

#json files for persitent claims
CLAIMS_FILE = "claims.json"
COLLECTIONS_FILE = "user_collections.json"

def load_claims():
    if os.path.exists(CLAIMS_FILE):
        with open(CLAIMS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_claims(data):
    with open(CLAIMS_FILE, "w") as f:
        json.dump(data, f, indent=2)
        
def load_collections():
    if os.path.exists(COLLECTIONS_FILE):
        with open(COLLECTIONS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_collections(data):
    with open(COLLECTIONS_FILE, "w") as f:
        json.dump(data, f, indent=2)

#initialize in-memory data
claimed_posts = load_claims()
user_collections = load_collections()

#claim button
class ClaimView(discord.ui.View):
    def __init__(self, message_id, post_info):
        super().__init__(timeout=None)
        self.message_id = str(message_id)
        self.post_info = post_info

    @discord.ui.button(label="Claim", style=discord.ButtonStyle.primary)
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = str(interaction.user.id)

        if self.message_id in claimed_posts:
            await interaction.response.send_message("❌ This post has already been claimed!", ephemeral=True)
            return

        #mark claim
        claimed_posts[self.message_id] = user_id
        user_collections.setdefault(user_id, []).append(self.post_info)
        save_claims(claimed_posts)
        save_collections(user_collections)

        await interaction.response.send_message("✅ You have claimed this post!", ephemeral=True)
        #self.disable_all_items()
        await interaction.message.edit(view=self)

@bot.event
async def on_ready():
    print(f'{bot.user} is online and connected to Discord!')

async def fetch_danbooru_post(tag=""):
    url = "https://danbooru.donmai.us/posts.json"
    params = {
        "tags": tag,
        "limit": 1,
        "random": "true",
        "login": DANBOORU_LOGIN,
        "api_key": DANBOORU_API_KEY,
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as response:
            if response.status == 200:
                data = await response.json()
                if data:
                    post = data[0]
                    image_url = post.get("file_url", "No image URL found.")
                    characters = post.get("tag_string_character", "")
                    copyrights = post.get("tag_string_copyright", "")
                    artist = post.get("tag_string_artist", "")
                    created_at = post.get("created_at", "")
                    return image_url, characters, copyrights, artist, created_at
    return None, "", "", "", ""

class ClaimsPaginator(discord.ui.View):
    def __init__(self, claims, user_id, timeout=120):
        super().__init__(timeout=timeout)
        self.claims = claims
        self.user_id = user_id
        self.page = 0
        self.max_page = len(claims) - 1
        self.update_buttons()

    def update_buttons(self):
        self.first_page.disabled = self.page == 0
        self.prev_page.disabled = self.page == 0
        self.next_page.disabled = self.page == self.max_page
        self.last_page.disabled = self.page == self.max_page

    def get_page_embed(self):
        post = self.claims[self.page]

        characters_raw = post.get('characters') or 'Unknown'
        characters = escape_markdown(characters_raw)
        date = post.get('date') or 'Unknown date'
        image_url = post.get('image') or ''
        source = escape_markdown(post.get('source') or 'Unknown')
        artist_raw = post.get('artist') or 'Unknown'
        artist = escape_markdown(artist_raw)

        embed = discord.Embed(
            title=f"Claim #{self.page+1}/{self.max_page+1}",
            description=f"**Characters:** {characters}\n**Source:** {source}\n**Date:** {date}\n**Artist:** {artist}",
            color=discord.Color.blurple()
        )
        if image_url:
            embed.set_image(url=image_url)

        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != int(self.user_id):
            await interaction.response.send_message("You can't interact with this menu!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="<< First", style=discord.ButtonStyle.secondary)
    async def first_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = 0
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_page_embed(), view=self)

    @discord.ui.button(label="< Prev", style=discord.ButtonStyle.primary)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_page_embed(), view=self)

    @discord.ui.button(label="Next >", style=discord.ButtonStyle.primary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page < self.max_page:
            self.page += 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_page_embed(), view=self)

    @discord.ui.button(label="Last >>", style=discord.ButtonStyle.secondary)
    async def last_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = self.max_page
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_page_embed(), view=self)

    @discord.ui.button(label="🗑️ Clear claim", style=discord.ButtonStyle.danger, row=1)
    async def clear_claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        #get the claim to remove
        claim_to_remove = self.claims[self.page]

        #remove from user_collections
        user_claims = user_collections.get(str(self.user_id), [])
        if claim_to_remove in user_claims:
            user_claims.remove(claim_to_remove)

        #remove from claimed_posts
        for message_id, user_id in list(claimed_posts.items()):
            if user_id == str(self.user_id):
                post = next((p for p in user_claims if p.get("image") == claim_to_remove.get("image")), None)
                if post is None:
                    claimed_posts.pop(message_id)

        save_claims(claimed_posts)
        save_collections(user_collections)

        #update paginator state
        self.claims = user_claims
        if not self.claims:
            await interaction.response.edit_message(content="You don't have any claims.", embed=None, view=None)
            return

        self.max_page = len(self.claims) - 1
        self.page = min(self.page, self.max_page)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_page_embed(), view=self)

@bot.command()
async def danbooru(ctx, *, tag=""):
    image_url, characters, copyrights, artist, created_at = await fetch_danbooru_post(tag)
    
    characters_escaped = escape_markdown(characters)
    copyrights_escaped = escape_markdown(copyrights)
    artist_escaped = escape_markdown(artist)

    if not image_url:
        await ctx.send("No results found.")
        return

    #format danbooru post
    embed = discord.Embed(title="Danbooru Post", color=discord.Color.purple())
    embed.set_image(url=image_url)
    if characters:
        embed.add_field(name="Characters", value=characters_escaped, inline=False)
    if copyrights:
        embed.add_field(name="Source", value=copyrights_escaped, inline=False)
    if artist:
        embed.add_field(name="Artist", value=artist_escaped, inline=False)
    if created_at:
        embed.set_footer(text=f"Posted on {created_at.split('T')[0]}")

    sent_msg = await ctx.send(embed=embed)

    #add claim button
    post_info = {
        "image": image_url,
        "characters": characters,
        "source": copyrights,
        "artist": artist,
        "date": created_at.split("T")[0] if created_at else ""
    }
    await sent_msg.edit(view=ClaimView(sent_msg.id, post_info))

#view claims
@bot.command()
async def myclaims(ctx):
    user_id = str(ctx.author.id)
    claims = user_collections.get(user_id, [])

    if not claims:
        await ctx.send("You don't have any claims.")
        return

    paginator = ClaimsPaginator(claims, user_id)
    await ctx.send(embed=paginator.get_page_embed(), view=paginator)
        
def escape_markdown(text):
    return re.sub(r'([_*~`])', r'\\\1', text or "")

bot.run(TOKEN)
