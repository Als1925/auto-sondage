# 🤖 Discord Poll Bot — Guide d'installation

Bot Discord qui génère automatiquement des sondages via Gemini AI,
avec message personnalisé et fil de discussion public.

---

## 📋 Prérequis

- Un compte Discord (évidemment 😄)
- Un compte Google (pour Gemini)
- Un compte Railway (gratuit)
- Un compte GitHub (pour déployer sur Railway)

---

## 🔑 Étape 1 — Créer le bot Discord

1. Va sur https://discord.com/developers/applications
2. Clique **"New Application"** → donne un nom
3. Va dans **"Bot"** → clique **"Add Bot"**
4. Copie le **Token** (garde-le secret !)
5. Dans **"Bot"**, active ces **Privileged Intents** :
   - ✅ Message Content Intent
6. Va dans **"OAuth2" > "URL Generator"** :
   - Coche `bot` + `applications.commands`
   - Permissions bot :
     - ✅ Send Messages
     - ✅ Create Public Threads
     - ✅ Send Messages in Threads
     - ✅ Embed Links
     - ✅ Use Application Commands
7. Copie l'URL générée et invite le bot sur ton serveur

---

## 🧠 Étape 2 — Obtenir une clé Gemini (gratuit)

1. Va sur https://aistudio.google.com/app/apikey
2. Clique **"Create API Key"**
3. Copie la clé

---

## 🚀 Étape 3 — Déployer sur Railway

### 3a. Mettre le code sur GitHub
1. Crée un repo GitHub (public ou privé)
2. Upload tous les fichiers du bot dedans :
   - `bot.py`
   - `requirements.txt`
   - `railway.toml`
   - `nixpacks.toml`

### 3b. Déployer sur Railway
1. Va sur https://railway.app → **"New Project"**
2. Choisis **"Deploy from GitHub repo"**
3. Sélectionne ton repo
4. Va dans **"Variables"** et ajoute :
   ```
   DISCORD_TOKEN=ton_token_discord_ici
   GEMINI_API_KEY=ta_clé_gemini_ici
   ```
5. Railway démarre automatiquement le bot ✅

---

## ⚙️ Étape 4 — Configurer le bot sur Discord

Une fois le bot en ligne, utilise les commandes slash (admin uniquement) :

| Commande | Description |
|----------|-------------|
| `/setchannel #salon` | Définir le salon où envoyer les sondages |
| `/settheme Minecraft` | Thème des sondages générés par l'IA |
| `/setinterval 60` | Intervalle en minutes entre chaque sondage |
| `/setpollduration 24` | Durée du sondage en heures (1-168) |
| `/setmessage Votez !` | Message personnalisé après le sondage |
| `/setthread Discutez ici !` | Phrase d'accroche dans le fil |
| `/startschedule` | ▶️ Démarrer la planification automatique |
| `/stopschedule` | ⏹️ Arrêter la planification |
| `/startnow` | ⚡ Envoyer un sondage immédiatement |
| `/status` | 📊 Voir toute la configuration actuelle |

### Exemple de démarrage rapide :
```
/setchannel #sondages
/settheme Minecraft
/setinterval 1440
/setmessage 🗳️ Nouveau sondage ! Donnez votre avis !
/setthread 💬 Discutez de vos réponses ici !
/startschedule
```

---

## 🔁 Ce que fait le bot à chaque cycle

1. 🤖 **Génère** une question + réponses via Gemini AI selon le thème
2. 📊 **Crée un sondage** Discord natif (boutons de vote)
3. 💬 **Envoie le message** personnalisé de l'admin
4. 🧵 **Ouvre un fil public** sur ce message avec la phrase d'accroche
5. ⏰ **Planifie** le prochain sondage selon l'intervalle défini

---

## ❓ Dépannage

**Le bot ne répond pas aux commandes slash ?**
→ Attends 1-2 minutes après le démarrage pour la synchro des commandes.

**Erreur "channel not found" ?**
→ Vérifie que le bot a bien accès au salon configuré.

**Sondage pas généré ?**
→ Vérifie ta clé Gemini dans les variables Railway.
