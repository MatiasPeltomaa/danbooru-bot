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

        await interaction.response.send_message("✅ You claimed this post!", ephemeral=True)
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
                    created_at = post.get("created_at", "")
                    return image_url, characters, copyrights, created_at
    return None, "", "", ""

@bot.command()
async def danbooru(ctx, *, tag=""):
    image_url, characters, copyrights, created_at = await fetch_danbooru_post(tag)

    if not image_url:
        await ctx.send("No results found.")
        return

    #format danbooru post
    embed = discord.Embed(title="Danbooru Post", color=discord.Color.purple())
    embed.set_image(url=image_url)
    if characters:
        embed.add_field(name="Characters", value=characters, inline=False)
    if copyrights:
        embed.add_field(name="Source", value=copyrights, inline=False)
    if created_at:
        embed.set_footer(text=f"Posted on {created_at.split('T')[0]}")

    sent_msg = await ctx.send(embed=embed)

    #add claim button
    post_info = {
        "image": image_url,
        "characters": characters,
        "source": copyrights,
        "date": created_at.split("T")[0] if created_at else ""
    }
    await sent_msg.edit(view=ClaimView(sent_msg.id, post_info))

#view claims
@bot.command()
async def myclaims(ctx):
    user_id = str(ctx.author.id)
    user_claims = [v for k, v in claimed_posts.items() if v == user_id]

    if not user_claims:
        await ctx.send("You don't have any claimed posts.")
        return

    #get users claims
    claims = user_collections.get(user_id, [])
    lines = []
    for i, post in enumerate(claims, 1):
        characters_raw = post.get('characters') or 'Unknown'
        characters = re.sub(r'([_*~`])', r'\\\1', characters_raw)
        date = post.get('date') or 'Unknown date'
        image_url = post.get('image') or '[No image]'
        lines.append(f"**{i}.** [{characters}] - {date}\nImage: {image_url}")

    #send in chunks if too long
    chunks = [lines[i:i + 5] for i in range(0, len(lines), 5)]
    for chunk in chunks:
        await ctx.send("\n".join(chunk))

bot.run(TOKEN)
