import discord
from discord.ext import commands, tasks
from discord import app_commands
import google.generativeai as genai
import json
import os
import asyncio
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── Config ───────────────────────────────────────────────────────────────────

CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "theme": "culture générale",
    "interval_minutes": 60,
    "channel_id": None,
    "custom_message": "🗳️ Un nouveau sondage est disponible ! Votez maintenant !",
    "thread_hook": "💬 Discutez de vos réponses ici !",
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

config = load_config()

# ─── Discord + Gemini setup ───────────────────────────────────────────────────

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

genai.configure(api_key=GEMINI_API_KEY)
gemini = genai.GenerativeModel("gemini-1.5-flash")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ─── AI Poll Generation ───────────────────────────────────────────────────────

async def generate_poll(theme: str) -> dict:
    prompt = f"""Génère un sondage Discord amusant et original sur le thème : "{theme}".

Réponds UNIQUEMENT en JSON valide avec cette structure exacte :
{{
  "question": "La question du sondage (max 300 caractères)",
  "answers": ["Réponse 1", "Réponse 2", "Réponse 3", "Réponse 4", "Réponse 5"]
}}

Règles :
- 3 à 5 réponses maximum
- Question engageante et fun
- Réponses courtes (max 55 caractères chacune)
- Uniquement du JSON, rien d'autre"""

    response = await asyncio.to_thread(gemini.generate_content, prompt)
    text = response.text.strip()

    # Strip markdown fences if present
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()

    data = json.loads(text)
    return data

# ─── Poll sender ──────────────────────────────────────────────────────────────

async def send_scheduled_poll():
    cfg = load_config()
    channel_id = cfg.get("channel_id")
    if not channel_id:
        logger.warning("Aucun salon configuré pour les sondages.")
        return

    channel = bot.get_channel(int(channel_id))
    if not channel:
        logger.error(f"Salon {channel_id} introuvable.")
        return

    try:
        poll_data = await generate_poll(cfg["theme"])
    except Exception as e:
        logger.error(f"Erreur génération sondage : {e}")
        await channel.send("⚠️ Impossible de générer un sondage pour le moment.")
        return

    # Build Discord Poll
    answers = [
        discord.PollAnswer(text=ans) for ans in poll_data["answers"]
    ]
    poll = discord.Poll(
        question=poll_data["question"],
        duration=timedelta(hours=cfg["poll_duration_hours"]),
        multiple=True,
        answers=answers
    )

    # Send poll
    poll_msg = await channel.send(poll=poll)

    # Send custom message
    custom_msg = await channel.send(cfg["custom_message"])

    # Create public thread on custom message
    thread = await custom_msg.create_thread(
        name=f"💬 {poll_data['question'][:90]}",
        auto_archive_duration=1440
    )
    await thread.send(cfg["thread_hook"])

    logger.info(f"✅ Sondage envoyé dans #{channel.name}")

    # Schedule next
    next_time = datetime.utcnow() + timedelta(minutes=cfg["interval_minutes"])
    cfg["next_poll_time"] = next_time.isoformat()
    save_config(cfg)

# ─── Scheduler ────────────────────────────────────────────────────────────────

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

# ─── Slash Commands ───────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    await bot.tree.sync()
    poll_scheduler.start()
    logger.info(f"✅ Bot connecté en tant que {bot.user}")

@bot.tree.command(name="settheme", description="Définir le thème des sondages")
@app_commands.describe(theme="Ex: Minecraft, cinéma, culture générale...")
@app_commands.checks.has_permissions(administrator=True)
async def settheme(interaction: discord.Interaction, theme: str):
    cfg = load_config()
    cfg["theme"] = theme
    save_config(cfg)
    await interaction.response.send_message(f"✅ Thème mis à jour : **{theme}**", ephemeral=True)

@bot.tree.command(name="setinterval", description="Définir l'intervalle entre les sondages")
@app_commands.describe(minutes="Intervalle en minutes (ex: 60 = 1h, 1440 = 1j)")
@app_commands.checks.has_permissions(administrator=True)
async def setinterval(interaction: discord.Interaction, minutes: int):
    if minutes < 5:
        await interaction.response.send_message("❌ Minimum 5 minutes.", ephemeral=True)
        return
    cfg = load_config()
    cfg["interval_minutes"] = minutes
    save_config(cfg)
    h, m = divmod(minutes, 60)
    label = f"{h}h{m:02d}" if h else f"{m}min"
    await interaction.response.send_message(f"✅ Intervalle mis à jour : **{label}**", ephemeral=True)

@bot.tree.command(name="setchannel", description="Définir le salon pour les sondages")
@app_commands.describe(channel="Le salon texte cible")
@app_commands.checks.has_permissions(administrator=True)
async def setchannel(interaction: discord.Interaction, channel: discord.TextChannel):
    cfg = load_config()
    cfg["channel_id"] = str(channel.id)
    save_config(cfg)
    await interaction.response.send_message(f"✅ Salon défini : {channel.mention}", ephemeral=True)

@bot.tree.command(name="setmessage", description="Personnaliser le message accompagnant le sondage")
@app_commands.describe(message="Le message à envoyer après le sondage")
@app_commands.checks.has_permissions(administrator=True)
async def setmessage(interaction: discord.Interaction, message: str):
    cfg = load_config()
    cfg["custom_message"] = message
    save_config(cfg)
    await interaction.response.send_message(f"✅ Message mis à jour : **{message}**", ephemeral=True)

@bot.tree.command(name="setthread", description="Personnaliser la phrase d'accroche du fil")
@app_commands.describe(phrase="La phrase d'introduction dans le fil")
@app_commands.checks.has_permissions(administrator=True)
async def setthread(interaction: discord.Interaction, phrase: str):
    cfg = load_config()
    cfg["thread_hook"] = phrase
    save_config(cfg)
    await interaction.response.send_message(f"✅ Phrase de fil mise à jour : **{phrase}**", ephemeral=True)

@bot.tree.command(name="setpollduration", description="Durée du sondage en heures")
@app_commands.describe(heures="Durée en heures (1 à 168)")
@app_commands.checks.has_permissions(administrator=True)
async def setpollduration(interaction: discord.Interaction, heures: int):
    if not 1 <= heures <= 168:
        await interaction.response.send_message("❌ Entre 1 et 168 heures (1 semaine max).", ephemeral=True)
        return
    cfg = load_config()
    cfg["poll_duration_hours"] = heures
    save_config(cfg)
    await interaction.response.send_message(f"✅ Durée du sondage : **{heures}h**", ephemeral=True)

@bot.tree.command(name="startnow", description="Lancer le prochain sondage immédiatement")
@app_commands.checks.has_permissions(administrator=True)
async def startnow(interaction: discord.Interaction):
    cfg = load_config()
    if not cfg.get("channel_id"):
        await interaction.response.send_message("❌ Configure d'abord un salon avec `/setchannel`.", ephemeral=True)
        return
    await interaction.response.send_message("⏳ Génération du sondage en cours...", ephemeral=True)
    await send_scheduled_poll()

@bot.tree.command(name="startschedule", description="Démarrer la planification automatique")
@app_commands.checks.has_permissions(administrator=True)
async def startschedule(interaction: discord.Interaction):
    cfg = load_config()
    if not cfg.get("channel_id"):
        await interaction.response.send_message("❌ Configure d'abord un salon avec `/setchannel`.", ephemeral=True)
        return
    next_time = datetime.utcnow() + timedelta(minutes=cfg["interval_minutes"])
    cfg["next_poll_time"] = next_time.isoformat()
    save_config(cfg)
    h, m = divmod(cfg["interval_minutes"], 60)
    label = f"{h}h{m:02d}" if h else f"{m}min"
    await interaction.response.send_message(
        f"✅ Planification démarrée ! Premier sondage dans **{label}**.", ephemeral=True
    )

@bot.tree.command(name="stopschedule", description="Arrêter la planification automatique")
@app_commands.checks.has_permissions(administrator=True)
async def stopschedule(interaction: discord.Interaction):
    cfg = load_config()
    cfg["next_poll_time"] = None
    save_config(cfg)
    await interaction.response.send_message("⏹️ Planification arrêtée.", ephemeral=True)

@bot.tree.command(name="status", description="Voir la configuration actuelle du bot")
@app_commands.checks.has_permissions(administrator=True)
async def status(interaction: discord.Interaction):
    cfg = load_config()
    channel = bot.get_channel(int(cfg["channel_id"])) if cfg.get("channel_id") else None
    h, m = divmod(cfg["interval_minutes"], 60)
    interval_label = f"{h}h{m:02d}" if h else f"{m}min"

    next_poll = "Non planifié"
    if cfg.get("next_poll_time"):
        try:
            dt = datetime.fromisoformat(cfg["next_poll_time"])
            next_poll = f"<t:{int(dt.timestamp())}:R>"
        except Exception:
            next_poll = "Erreur de parsing"

    embed = discord.Embed(title="📊 Statut du Poll Bot", color=0x5865F2)
    embed.add_field(name="🎯 Thème", value=cfg["theme"], inline=True)
    embed.add_field(name="⏱️ Intervalle", value=interval_label, inline=True)
    embed.add_field(name="⏳ Durée sondage", value=f"{cfg['poll_duration_hours']}h", inline=True)
    embed.add_field(name="📢 Salon", value=channel.mention if channel else "Non défini", inline=True)
    embed.add_field(name="🕐 Prochain sondage", value=next_poll, inline=True)
    embed.add_field(name="💬 Message", value=cfg["custom_message"][:100], inline=False)
    embed.add_field(name="🧵 Phrase fil", value=cfg["thread_hook"][:100], inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

bot.run(DISCORD_TOKEN)
