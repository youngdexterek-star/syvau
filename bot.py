import discord
from discord import app_commands
from discord.ext import commands
import requests
import paramiko
import random

# ================= CONFIG =================
TOKEN = "MTQ4NTI3MzAxNTEyOTM0MjAxNA.GeI1LB.2Xtz4E_EdQewRlXaMCVQsKMcvMh_nhK8nX5Fp8"

FREEPBX_URL = "http://vps16049.awhost.cloud/admin/api/api/gql"
TOKEN_URL = "http://vps16049.awhost.cloud/admin/api/api/token"

CLIENT_ID = "47e22363a90304539c19347bd27ab6b0787a9bccdbe794d6a68107c77ea05505"
CLIENT_SECRET = "f5aab3a1c643ae2ccbc1fae093be25c1"

SSH_HOST = "194.110.5.240"
SSH_PORT = 2022
SSH_USER = "root"
SSH_PASSWORD = "vmv5w6bM8QaYBPKA"
# ==========================================

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="/", intents=intents)
tree = bot.tree

# Słownik do przechowywania utworzonych numerów dla użytkowników
user_extensions = {}

# ================= FREEPBX =================

def get_token():
    res = requests.post(TOKEN_URL, data={
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET
    })
    return res.json()["access_token"]


def gql(query):
    token = get_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    res = requests.post(FREEPBX_URL, json={"query": query}, headers=headers)
    return res.json()


def generate_extension():
    return str(random.randint(10000, 99999))


def create_extension(ext, name, uid):
    mutation = f"""
    mutation {{
        addExtension(
            input: {{
                extensionId: "{ext}"
                name: "{name}"
                tech: "pjsip"
                email: "{uid}"
                maxContacts: "1"
            }}
        ) {{
            status
            message
        }}
    }}
    """

    res = gql(mutation)

    if "errors" in res:
        raise Exception(res)


def get_extension_data(ext):
    query = f"""
    query {{
        fetchExtension(extensionId: "{ext}") {{
            user {{
                extension
                extPassword
            }}
        }}
    }}
    """

    res = gql(query)

    if "errors" in res:
        raise Exception(res)

    return res["data"]["fetchExtension"]


def check_user_has_extension(user_id):
    """Sprawdza czy użytkownik ma już utworzony numer"""
    # Tutaj możesz dodać sprawdzanie w bazie danych lub innym źródle
    # Na razie używamy prostego słownika w pamięci
    return user_id in user_extensions


def get_user_extensions():
    """Pobiera istniejące numery użytkowników z systemu"""
    # Tutaj możesz zaimplementować pobieranie z API FreePBX
    # Na razie zwracamy pustą listę
    return []


# ================= SSH =================

def reload_pbx():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    ssh.connect(
        SSH_HOST,
        port=SSH_PORT,
        username=SSH_USER,
        password=SSH_PASSWORD
    )

    ssh.exec_command("fwconsole reload")
    ssh.close()


# ================= DISCORD =================

class Panel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📞 Utwórz konto", style=discord.ButtonStyle.green)
    async def create(self, interaction: discord.Interaction, button: discord.ui.Button):

        await interaction.response.defer(ephemeral=True)

        try:
            # Sprawdzenie czy użytkownik ma już numer
            if check_user_has_extension(interaction.user.id):
                await interaction.followup.send(
                    "❌ Można posiadać tylko jeden numer!",
                    ephemeral=True
                )
                return

            ext = generate_extension()

            # create extension
            create_extension(ext, interaction.user.display_name, interaction.user.id)

            # reload pbx
            reload_pbx()

            # fetch real password
            data = get_extension_data(ext)

            real_ext = data["user"]["extension"]
            password = data["user"]["extPassword"]

            # Zapisz utworzony numer dla użytkownika
            user_extensions[interaction.user.id] = real_ext

            embed = discord.Embed(
                title="📞 Twoje konto VoIP",
                color=0x00ff00
            )

            embed.add_field(name="Numer", value=f"`{real_ext}`", inline=False)
            embed.add_field(name="Hasło", value=f"||{password}||", inline=False)
            embed.add_field(name="Serwer SIP", value="`sip.voxelvoip.pl`", inline=False)
            embed.add_field(name="Domena", value="`sip.voxelvoip.pl`", inline=False)

            await interaction.user.send(embed=embed)

            await interaction.followup.send(
                "✅ konto utworzone, sprawdź DM",
                ephemeral=True
            )

        except Exception as e:
            await interaction.followup.send(
                f"❌ error: {e}",
                ephemeral=True
            )


# ================= COMMAND =================

@tree.command(name="panel", description="wysyła panel z guzikiem")
async def panel(interaction: discord.Interaction):

    embed = discord.Embed(
        title="📞 System VoIP",
        description="Kliknij przycisk poniżej aby utworzyć konto.",
        color=0x00ff00
    )

    await interaction.channel.send(embed=embed, view=Panel())
    await interaction.response.send_message("✅ panel wysłany", ephemeral=True)


# ================= START =================

@bot.event
async def on_ready():
    await tree.sync()
    print(f"zalogowano jako {bot.user}")
    user_extensions.update(get_user_extensions())


bot.run(TOKEN)
