import discord
from discord.ext import commands, tasks
from discord import app_commands
from groq import Groq
import json
import os
import asyncio
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Config

CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "theme": "culture generale",
    "interval_minutes": 60,
    "channel_id": None,
    "custom_message": "Un nouveau sondage est disponible ! Votez maintenant !",
    "thread_hook": "Discutez de vos reponses ici !",
    "poll_duration_hours": 24,
    "next_poll_time": None
}

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            for k, v in DEFAULT_CONFIG.items():
                data.setdefault(k, v)
            return data
    return DEFAULT_CONFIG.copy()

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

# Discord + Groq setup

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
GROQ_API_KEY = os.environ["GROQ_API_KEY"]

groq_client = Groq(api_key=GROQ_API_KEY)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# AI Poll Generation

async def generate_poll(theme: str) -> dict:
    prompt = f"""Genere un sondage Discord amusant et original sur le theme : "{theme}".

Reponds UNIQUEMENT en JSON valide avec cette structure exacte :
{{
  "question": "La question du sondage (max 300 caracteres)",
  "answers": ["Reponse 1", "Reponse 2", "Reponse 3", "Reponse 4", "Reponse 5"]
}}

Regles :
- 3 a 5 reponses maximum
- Question engageante et fun
- Reponses courtes (max 55 caracteres chacune)
- Uniquement du JSON, rien d autre"""

    def _call_groq():
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.9
        )
        return response.choices[0].message.content

    text = await asyncio.to_thread(_call_groq)
    return json.loads(text.strip())

# Poll sender

async def send_scheduled_poll(interaction: discord.Interaction = None):
    cfg = load_config()
    channel_id = cfg.get("channel_id")

    async def report_error(msg: str):
        logger.error(msg)
        if interaction:
            try:
                await interaction.followup.send(f"Erreur : {msg}", ephemeral=True)
            except Exception:
                pass

    if not channel_id:
        await report_error("Aucun salon configure. Utilise /setchannel d'abord.")
        return

    channel = bot.get_channel(int(channel_id))
    if not channel:
        try:
            channel = await bot.fetch_channel(int(channel_id))
        except Exception:
            await report_error(f"Salon introuvable (id: {channel_id}). Reconfigure avec /setchannel.")
            return

    try:
        poll_data = await generate_poll(cfg["theme"])
    except Exception as e:
        logger.error(f"Erreur generation sondage : {e}")
        await report_error(f"Impossible de generer un sondage via Groq : {type(e).__name__}: {e}")
        return

    poll = discord.Poll(
        question=poll_data["question"],
        duration=timedelta(hours=cfg["poll_duration_hours"]),
        multiple=True,
    )
    for ans in poll_data["answers"]:
        poll.add_answer(text=ans)

    try:
        await channel.send(poll=poll)
        custom_msg = await channel.send(cfg["custom_message"])
        thread = await custom_msg.create_thread(
            name=poll_data["question"][:90],
            auto_archive_duration=1440
        )
        await thread.send(cfg["thread_hook"])
    except discord.Forbidden:
        await report_error(
            f"Le bot n'a pas les permissions dans le salon id {channel_id}. "
            "Verifie : Envoyer des messages, Creer des fils publics, Envoyer dans les fils."
        )
        return
    except Exception as e:
        await report_error(f"Erreur lors de l'envoi : {e}")
        return

    logger.info(f"Sondage envoye dans #{channel.name}")
    if interaction:
        try:
            await interaction.followup.send(f"Sondage envoye dans {channel.mention} !", ephemeral=True)
        except Exception:
            pass

    next_time = datetime.utcnow() + timedelta(minutes=cfg["interval_minutes"])
    cfg["next_poll_time"] = next_time.isoformat()
    save_config(cfg)

# Scheduler

@tasks.loop(minutes=1)
async def poll_scheduler():
    await bot.wait_until_ready()
    cfg = load_config()
    if not cfg.get("next_poll_time"):
        return
    try:
        next_time = datetime.fromisoformat(cfg["next_poll_time"])
    except Exception:
        return
    if datetime.utcnow() >= next_time:
        await send_scheduled_poll()

# Slash Commands

@bot.event
async def on_ready():
    await bot.tree.sync()
    poll_scheduler.start()
    logger.info(f"Bot connecte en tant que {bot.user}")

@bot.tree.command(name="settheme", description="Definir le theme des sondages")
@app_commands.describe(theme="Ex: Minecraft, cinema, culture generale...")
@app_commands.checks.has_permissions(administrator=True)
async def settheme(interaction: discord.Interaction, theme: str):
    cfg = load_config()
    cfg["theme"] = theme
    save_config(cfg)
    await interaction.response.send_message(f"Theme mis a jour : **{theme}**", ephemeral=True)

@bot.tree.command(name="setinterval", description="Definir l'intervalle entre les sondages")
@app_commands.describe(minutes="Intervalle en minutes (ex: 60 = 1h, 1440 = 1j)")
@app_commands.checks.has_permissions(administrator=True)
async def setinterval(interaction: discord.Interaction, minutes: int):
    if minutes < 5:
        await interaction.response.send_message("Minimum 5 minutes.", ephemeral=True)
        return
    cfg = load_config()
    cfg["interval_minutes"] = minutes
    save_config(cfg)
    h, m = divmod(minutes, 60)
    label = f"{h}h{m:02d}" if h else f"{m}min"
    await interaction.response.send_message(f"Intervalle mis a jour : **{label}**", ephemeral=True)

@bot.tree.command(name="setchannel", description="Definir le salon pour les sondages")
@app_commands.describe(channel="Le salon texte cible")
@app_commands.checks.has_permissions(administrator=True)
async def setchannel(interaction: discord.Interaction, channel: discord.TextChannel):
    cfg = load_config()
    cfg["channel_id"] = str(channel.id)
    save_config(cfg)
    await interaction.response.send_message(f"Salon defini : {channel.mention}", ephemeral=True)

@bot.tree.command(name="setmessage", description="Personnaliser le message accompagnant le sondage")
@app_commands.describe(message="Le message a envoyer apres le sondage")
@app_commands.checks.has_permissions(administrator=True)
async def setmessage(interaction: discord.Interaction, message: str):
    cfg = load_config()
    cfg["custom_message"] = message
    save_config(cfg)
    await interaction.response.send_message(f"Message mis a jour : **{message}**", ephemeral=True)

@bot.tree.command(name="setthread", description="Personnaliser la phrase d'accroche du fil")
@app_commands.describe(phrase="La phrase d'introduction dans le fil")
@app_commands.checks.has_permissions(administrator=True)
async def setthread(interaction: discord.Interaction, phrase: str):
    cfg = load_config()
    cfg["thread_hook"] = phrase
    save_config(cfg)
    await interaction.response.send_message(f"Phrase de fil mise a jour : **{phrase}**", ephemeral=True)

@bot.tree.command(name="setpollduration", description="Duree du sondage en heures")
@app_commands.describe(heures="Duree en heures (1 a 168)")
@app_commands.checks.has_permissions(administrator=True)
async def setpollduration(interaction: discord.Interaction, heures: int):
    if not 1 <= heures <= 168:
        await interaction.response.send_message("Entre 1 et 168 heures (1 semaine max).", ephemeral=True)
        return
    cfg = load_config()
    cfg["poll_duration_hours"] = heures
    save_config(cfg)
    await interaction.response.send_message(f"Duree du sondage : **{heures}h**", ephemeral=True)

@bot.tree.command(name="startnow", description="Lancer le prochain sondage immediatement")
@app_commands.checks.has_permissions(administrator=True)
async def startnow(interaction: discord.Interaction):
    cfg = load_config()
    if not cfg.get("channel_id"):
        await interaction.response.send_message("Configure d'abord un salon avec /setchannel.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    await send_scheduled_poll(interaction=interaction)

@bot.tree.command(name="startschedule", description="Demarrer la planification automatique")
@app_commands.checks.has_permissions(administrator=True)
async def startschedule(interaction: discord.Interaction):
    cfg = load_config()
    if not cfg.get("channel_id"):
        await interaction.response.send_message("Configure d'abord un salon avec /setchannel.", ephemeral=True)
        return
    next_time = datetime.utcnow() + timedelta(minutes=cfg["interval_minutes"])
    cfg["next_poll_time"] = next_time.isoformat()
    save_config(cfg)
    h, m = divmod(cfg["interval_minutes"], 60)
    label = f"{h}h{m:02d}" if h else f"{m}min"
    await interaction.response.send_message(
        f"Planification demarree ! Premier sondage dans **{label}**.", ephemeral=True
    )

@bot.tree.command(name="stopschedule", description="Arreter la planification automatique")
@app_commands.checks.has_permissions(administrator=True)
async def stopschedule(interaction: discord.Interaction):
    cfg = load_config()
    cfg["next_poll_time"] = None
    save_config(cfg)
    await interaction.response.send_message("Planification arretee.", ephemeral=True)

@bot.tree.command(name="status", description="Voir la configuration actuelle du bot")
@app_commands.checks.has_permissions(administrator=True)
async def status(interaction: discord.Interaction):
    cfg = load_config()
    channel = bot.get_channel(int(cfg["channel_id"])) if cfg.get("channel_id") else None
    h, m = divmod(cfg["interval_minutes"], 60)
    interval_label = f"{h}h{m:02d}" if h else f"{m}min"

    next_poll = "Non planifie"
    if cfg.get("next_poll_time"):
        try:
            dt = datetime.fromisoformat(cfg["next_poll_time"])
            next_poll = f"<t:{int(dt.timestamp())}:R>"
        except Exception:
            next_poll = "Erreur de parsing"

    embed = discord.Embed(title="Statut du Poll Bot", color=0x5865F2)
    embed.add_field(name="Theme", value=cfg["theme"], inline=True)
    embed.add_field(name="Intervalle", value=interval_label, inline=True)
    embed.add_field(name="Duree sondage", value=f"{cfg['poll_duration_hours']}h", inline=True)
    embed.add_field(name="Salon", value=channel.mention if channel else f"id: {cfg.get('channel_id', 'Non defini')}", inline=True)
    embed.add_field(name="Prochain sondage", value=next_poll, inline=True)
    embed.add_field(name="Message", value=cfg["custom_message"][:100], inline=False)
    embed.add_field(name="Phrase fil", value=cfg["thread_hook"][:100], inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

bot.run(DISCORD_TOKEN)
