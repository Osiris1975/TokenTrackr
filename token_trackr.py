import discord
from discord import app_commands
import sqlite3
from discord.ext import commands
import os
from dotenv import load_dotenv
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Load environment variables
load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
CHROMEDRIVER_PATH = os.getenv("CHROMEDRIVER_PATH", "chromedriver")

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Intents and bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


# Sync Commands on Ready
@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()  # Sync commands globally
        logger.info(f"Synced {len(synced)} command(s).")
    except Exception as e:
        logger.error(f"Failed to sync commands: {e}")


# SQLite database setup
def init_db():
    with sqlite3.connect('tokens.db') as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS awarded_tokens (
                        user_id INTEGER,
                        awarded_by TEXT,
                        reason TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                      )''')
        conn.commit()


# Define the /hello command
@bot.tree.command(name="hello", description="Say hello to the bot")
async def hello(interaction: discord.Interaction):
    await interaction.response.send_message(f"Hello, {interaction.user.name}!")


# award a token
async def award_token(user_id, interaction, reason):
    with sqlite3.connect('tokens.db') as conn:
        c = conn.cursor()
        c.execute("INSERT INTO awarded_tokens (user_id, awarded_by, reason) VALUES (?, ?, ?)",
                  (user_id, interaction.user.name, reason))
        conn.commit()


# Slash command to log a kill
@bot.tree.command(name="award_token")
@app_commands.describe(
    ship_killed="The name of the ship killed",
    pilot_killed="The name of the pilot killed"
)
async def logkill(interaction: discord.Interaction, ship_killed: str, pilot_killed: str):
    if not ship_killed or not pilot_killed:
        await interaction.response.send_message("Both 'ship_killed' and 'pilot_killed' are required.")
        return

    # Log the kill to the database
    await log_kill(interaction.user.id, ship_killed, pilot_killed)

    await interaction.response.send_message(
        f"Kill logged: {interaction.user.name} killed {pilot_killed} in their {ship_killed}.")


# Slash command to view kill statistics
@bot.tree.command(name="killstats")
async def killstats(interaction: discord.Interaction):
    with sqlite3.connect('kill_log.db') as conn:
        c = conn.cursor()
        c.execute(
            "SELECT user_id, ship_killed, pilot_killed, COUNT(*) FROM kills GROUP BY user_id, ship_killed, pilot_killed")
        stats = c.fetchall()

    if stats:
        stats_message = "Kill Stats:\n"
        for stat in stats:
            stats_message += f"User ID: {stat[0]}\n  Ship: {stat[1]}\n  Pilot: {stat[2]}\n  Kills: {stat[3]}\n\n"
        await interaction.response.send_message(stats_message)
    else:
        await interaction.response.send_message("No kill data available.")


# Define the /lookup command
@bot.tree.command(name="lookup", description="Look up an RSI user profile by RSI Handle")
async def lookup(interaction: discord.Interaction, rsi_handle: str):
    await interaction.response.defer()

    try:
        # Set up Selenium WebDriver
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")

        service = Service(CHROMEDRIVER_PATH)
        driver = webdriver.Chrome(service=service, options=options)

        # Open the RSI profile page
        url = f"https://robertsspaceindustries.com/citizens/{rsi_handle}"
        driver.get(url)

        # Wait for elements to load
        wait = WebDriverWait(driver, 10)

        # Locate and extract profile bio
        try:
            profile_bio = wait.until(
                EC.presence_of_element_located(
                    (By.XPATH, "//div[@class='value' and not(strong)]")
                )
            ).text.strip()
        except Exception:
            profile_bio = "Bio not found"

        try:
            profile_avatar = wait.until(
                EC.presence_of_element_located((By.CLASS_NAME, "profile-avatar"))
            ).get_attribute("src")
        except Exception:
            profile_avatar = "Avatar not found"

        # Close the browser
        driver.quit()

        # Format and send the response
        profile_info = (
            f"**RSI Handle:** {rsi_handle}\n"
            f"Bio: {profile_bio}\n"
            f"Avatar: {profile_avatar}\n"
            f"[Profile Link]({url})"
        )
        await interaction.followup.send(profile_info)

    except Exception as e:
        logger.error(f"Error during lookup: {e}")
        await interaction.followup.send("An error occurred while fetching the profile. Please try again later.")

    finally:
        driver.quit()


# Initialize database
init_db()

# Run the bot
if TOKEN:
    bot.run(TOKEN)
else:
    logger.error("Bot token not found. Please set it in the .env file.")