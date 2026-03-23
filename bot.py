import discord
from discord import app_commands
from discord.ext import commands
import requests
import paramiko
import random
import sqlite3
import os

# ================= CONFIG =================
TOKEN = "MTQ4NTI3MzAxNTEyOTM0MjAxNA.GPaUU7.ptQVjQYzwdRdd5SdMdEQ14hsxpCVqw-gosP5KY"

FREEPBX_URL = "http://vps16049.awhost.cloud/admin/api/api/gql"
TOKEN_URL = "http://vps16049.awhost.cloud/admin/api/api/token"

CLIENT_ID = "47e22363a90304539c19347bd27ab6b0787a9bccdbe794d6a68107c77ea05505"
CLIENT_SECRET = "f5aab3a1c643ae2ccbc1fae093be25c1"

SSH_HOST = "194.110.5.240"
SSH_PORT = 2022
SSH_USER = "root"
SSH_PASSWORD = "vmv5w6bM8QaYBPKA"

# Specjalny użytkownik z nieograniczonym dostępem
UNLIMITED_USER_ID = 1404073935259041923
# ==========================================

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="/", intents=intents)
tree = bot.tree

# Inicjalizacja bazy danych
DB_NAME = "accounts.db"

def init_database():
    """Inicjalizuje bazę danych i tworzy tabelę jeśli nie istnieje"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Tworzenie tabeli accounts jeśli nie istnieje
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS accounts (
            user_id INTEGER PRIMARY KEY,
            extension TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            has_account INTEGER DEFAULT 0
        )
    ''')
    
    conn.commit()
    conn.close()

def user_has_account(user_id):
    """Sprawdza czy użytkownik ma już utworzone konto"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute("SELECT has_account FROM accounts WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    
    conn.close()
    
    if result:
        return result[0] == 1
    return False

def set_user_account(user_id, extension):
    """Ustawia dla użytkownika, że ma utworzone konto"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT OR REPLACE INTO accounts (user_id, extension, has_account)
        VALUES (?, ?, 1)
    ''', (user_id, extension))
    
    conn.commit()
    conn.close()

def get_user_extension(user_id):
    """Pobiera numer telefonu dla danego użytkownika"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute("SELECT extension FROM accounts WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    
    conn.close()
    
    if result:
        return result[0]
    return None

def get_all_user_extensions():
    """Pobiera wszystkie numery użytkowników z bazy danych"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute("SELECT user_id, extension FROM accounts WHERE has_account = 1")
    results = cursor.fetchall()
    
    conn.close()
    
    extensions_dict = {}
    for user_id, extension in results:
        extensions_dict[user_id] = extension
    
    return extensions_dict

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
            # Sprawdzenie czy użytkownik ma specjalne uprawnienia
            is_unlimited = interaction.user.id == UNLIMITED_USER_ID
            
            # Jeśli nie jest specjalnym użytkownikiem, sprawdź czy ma już konto
            if not is_unlimited and user_has_account(interaction.user.id):
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
            set_user_account(interaction.user.id, real_ext)

            # Tworzenie wiadomości o utworzeniu konta
            if is_unlimited:
                embed = discord.Embed(
                    title="📞 Twoje konto na naszym serwerze VoIP",
                    description=f"To jest Twoje **{self.get_account_count(interaction.user.id)}** konto!",
                    color=0x00ff00
                )
            else:
                embed = discord.Embed(
                    title="📞 Twoje konto na naszym serwerze VoIP",
                    color=0x00ff00
                )

            embed.add_field(name="Numer", value=f"`{real_ext}`", inline=False)
            embed.add_field(name="Hasło", value=f"||{password}||", inline=False)
            embed.add_field(name="Serwer SIP", value="`sip.voxelvoip.pl`", inline=False)
            embed.add_field(name="Domena", value="`sip.voxelvoip.pl`", inline=False)

            await interaction.user.send(embed=embed)

            # Komunikat potwierdzający
            if is_unlimited:
                await interaction.followup.send(
                    "✅ Konto utworzone pomyślnie! Sprawdź DM.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "✅ Konto utworzone pomyślnie! Sprawdź DM.",
                    ephemeral=True
                )

        except Exception as e:
            await interaction.followup.send(
                f"❌ Błąd: {e}",
                ephemeral=True
            )
    
    def get_account_count(self, user_id):
        """Liczy ile kont ma dany użytkownik"""
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM accounts WHERE user_id = ?", (user_id,))
        count = cursor.fetchone()[0]
        
        conn.close()
        return count

@discord.ui.button(label="📊 Sprawdź konto", style=discord.ButtonStyle.blurple)
async def check_account(self, interaction: discord.Interaction, button: discord.ui.Button):
    """Przycisk do sprawdzania czy użytkownik ma konto"""
    await interaction.response.defer(ephemeral=True)
    
    is_unlimited = interaction.user.id == UNLIMITED_USER_ID
    
    if user_has_account(interaction.user.id):
        extension = get_user_extension(interaction.user.id)
        
        embed = discord.Embed(
            title="📊 Informacje o koncie",
            color=0x00ff00
        )
        embed.add_field(name="Status", value="✅ Posiadasz konto VoIP", inline=False)
        embed.add_field(name="Twój numer", value=f"`{extension}`", inline=False)
        
        if is_unlimited:
            account_count = self.get_account_count(interaction.user.id)
            embed.add_field(name="Ilość kont", value=f"Posiadasz {account_count} kont", inline=False)
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    else:
        embed = discord.Embed(
            title="📊 Informacje o koncie",
            description="❌ Nie posiadasz jeszcze konta VoIP",
            color=0xff0000
        )
        embed.add_field(name="Co teraz?", value="Kliknij przycisk 'Utwórz konto' aby rozpocząć!", inline=False)
        
        await interaction.followup.send(embed=embed, ephemeral=True)

# Dodanie drugiego przycisku do panelu
class Panel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="📞 Utwórz konto", style=discord.ButtonStyle.green)
    async def create(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        try:
            # Sprawdzenie czy użytkownik ma specjalne uprawnienia
            is_unlimited = interaction.user.id == UNLIMITED_USER_ID
            
            # Jeśli nie jest specjalnym użytkownikiem, sprawdź czy ma już konto
            if not is_unlimited and user_has_account(interaction.user.id):
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
            set_user_account(interaction.user.id, real_ext)

            # Tworzenie wiadomości o utworzeniu konta
            account_count = self.get_account_count(interaction.user.id)
            
            if is_unlimited:
                embed = discord.Embed(
                    title="📞 Twoje nowe konto VoIP (nieograniczone)",
                    description=f"To jest Twoje **{account_count}** konto!",
                    color=0x00ff00
                )
            else:
                embed = discord.Embed(
                    title="📞 Twoje konto VoIP",
                    color=0x00ff00
                )

            embed.add_field(name="Numer", value=f"`{real_ext}`", inline=False)
            embed.add_field(name="Hasło", value=f"||{password}||", inline=False)
            embed.add_field(name="Serwer SIP", value="`sip.voxelvoip.pl`", inline=False)
            embed.add_field(name="Domena", value="`sip.voxelvoip.pl`", inline=False)

            if is_unlimited:
                embed.add_field(name="ℹ️ Informacja", value="Jako uprzywilejowany użytkownik możesz tworzyć nieograniczoną liczbę kont!", inline=False)

            await interaction.user.send(embed=embed)

            # Komunikat potwierdzający
            if is_unlimited:
                await interaction.followup.send(
                    f"✅ Konto {real_ext} utworzone pomyślnie! Sprawdź DM. (To Twoje {account_count} konto)",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "✅ Konto utworzone pomyślnie! Sprawdź DM.",
                    ephemeral=True
                )

        except Exception as e:
            await interaction.followup.send(
                f"❌ Błąd: {e}",
                ephemeral=True
            )
    
    @discord.ui.button(label="📊 Sprawdź konto", style=discord.ButtonStyle.blurple)
    async def check_account(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Przycisk do sprawdzania czy użytkownik ma konto"""
        await interaction.response.defer(ephemeral=True)
        
        is_unlimited = interaction.user.id == UNLIMITED_USER_ID
        
        if user_has_account(interaction.user.id):
            extension = get_user_extension(interaction.user.id)
            
            embed = discord.Embed(
                title="📊 Informacje o koncie",
                color=0x00ff00
            )
            embed.add_field(name="Status", value="✅ Posiadasz konto VoIP", inline=False)
            embed.add_field(name="Twój numer", value=f"`{extension}`", inline=False)
            
            if is_unlimited:
                account_count = self.get_account_count(interaction.user.id)
                embed.add_field(name="Ilość kont", value=f"Posiadasz {account_count} kont", inline=False)
            
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            embed = discord.Embed(
                title="📊 Informacje o koncie",
                description="❌ Nie posiadasz jeszcze konta VoIP",
                color=0xff0000
            )
            embed.add_field(name="Co teraz?", value="Kliknij przycisk 'Utwórz konto' aby rozpocząć!", inline=False)
            
            await interaction.followup.send(embed=embed, ephemeral=True)
    
    def get_account_count(self, user_id):
        """Liczy ile kont ma dany użytkownik"""
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM accounts WHERE user_id = ?", (user_id,))
        count = cursor.fetchone()[0]
        
        conn.close()
        return count

# ================= COMMAND =================

@tree.command(name="panel", description="Wysyła panel z guzikami")
async def panel(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📞 System VoIP",
        description="Kliknij przycisk poniżej aby utworzyć konto lub sprawdzić swoje konto.",
        color=0x00ff00
    )
    
    # Dodanie informacji o specjalnym użytkowniku jeśli to on wywołuje komendę
    if interaction.user.id == UNLIMITED_USER_ID:
        embed.add_field(
            name="👑 Uprzywilejowany dostęp",
            value="Jesteś uprzywilejowanym użytkownikiem! Możesz tworzyć nieograniczoną liczbę kont.",
            inline=False
        )
    
    await interaction.channel.send(embed=embed, view=Panel())
    await interaction.response.send_message("✅ Panel został wysłany", ephemeral=True)

@tree.command(name="admin_list_accounts", description="Lista wszystkich kont (tylko dla admina)")
async def admin_list_accounts(interaction: discord.Interaction):
    """Komenda admina do wyświetlenia wszystkich kont"""
    if interaction.user.id != UNLIMITED_USER_ID:
        await interaction.response.send_message("❌ Nie masz uprawnień do tej komendy!", ephemeral=True)
        return
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute("SELECT user_id, extension, created_at FROM accounts WHERE has_account = 1 ORDER BY created_at DESC")
    accounts = cursor.fetchall()
    
    conn.close()
    
    if not accounts:
        await interaction.response.send_message("📊 Brak utworzonych kont w bazie.", ephemeral=True)
        return
    
    embed = discord.Embed(
        title="📊 Lista wszystkich kont",
        color=0x00ff00
    )
    
    for user_id, extension, created_at in accounts[:25]:  # Limit 25 kont na embed
        embed.add_field(
            name=f"Użytkownik: {user_id}",
            value=f"Numer: {extension}\nUtworzono: {created_at}",
            inline=False
        )
    
    embed.set_footer(text=f"Łączna liczba kont: {len(accounts)}")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="admin_reset_user", description="Resetuje konto użytkownika (tylko dla admina)")
async def admin_reset_user(interaction: discord.Interaction, user_id: str):
    """Komenda admina do resetowania konta użytkownika"""
    if interaction.user.id != UNLIMITED_USER_ID:
        await interaction.response.send_message("❌ Nie masz uprawnień do tej komendy!", ephemeral=True)
        return
    
    try:
        user_id_int = int(user_id)
        
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM accounts WHERE user_id = ?", (user_id_int,))
        conn.commit()
        
        if cursor.rowcount > 0:
            await interaction.response.send_message(f"✅ Usunięto konto dla użytkownika {user_id}", ephemeral=True)
        else:
            await interaction.response.send_message(f"ℹ️ Nie znaleziono konta dla użytkownika {user_id}", ephemeral=True)
        
        conn.close()
        
    except ValueError:
        await interaction.response.send_message("❌ Nieprawidłowe ID użytkownika!", ephemeral=True)

# ================= START =================

@bot.event
async def on_ready():
    # Inicjalizacja bazy danych
    init_database()
    
    # Synchronizacja komend
    await tree.sync()
    print(f"✅ Zalogowano jako {bot.user}")
    print(f"📊 Baza danych: {DB_NAME}")
    print(f"👑 Użytkownik specjalny: {UNLIMITED_USER_ID}")
    
    # Wczytanie istniejących kont do pamięci (opcjonalne)
    extensions = get_all_user_extensions()
    print(f"📞 Wczytano {len(extensions)} istniejących kont z bazy")

bot.run(TOKEN)
