import discord
from discord import app_commands
from discord.ext import commands
import requests
import paramiko
import random
import sqlite3
import os
from datetime import datetime

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
# ==========================================

# Inicjalizacja bota
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="/", intents=intents)
tree = bot.tree

# ================= BAZA DANYCH =================
DB_FILE = "konta.db"

def init_database():
    """Inicjalizuje bazę danych i tworzy tabelę jeśli nie istnieje"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS konta (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            discord_user_id TEXT NOT NULL UNIQUE,
            discord_user_name TEXT NOT NULL,
            extension_number TEXT NOT NULL,
            extension_password TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL,
            is_active BOOLEAN DEFAULT 1
        )
    ''')
    
    conn.commit()
    conn.close()

def save_user_account(discord_user_id, discord_user_name, extension_number, extension_password):
    """Zapisuje informacje o utworzonym koncie do bazy danych"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO konta (discord_user_id, discord_user_name, extension_number, extension_password, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (str(discord_user_id), discord_user_name, extension_number, extension_password, datetime.now()))
        
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False  # Użytkownik już ma konto
    finally:
        conn.close()

def get_user_account(discord_user_id):
    """Pobiera informacje o koncie użytkownika z bazy danych"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT discord_user_id, discord_user_name, extension_number, extension_password, created_at, is_active
        FROM konta 
        WHERE discord_user_id = ? AND is_active = 1
    ''', (str(discord_user_id),))
    
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return {
            'discord_user_id': result[0],
            'discord_user_name': result[1],
            'extension_number': result[2],
            'extension_password': result[3],
            'created_at': result[4],
            'is_active': result[5]
        }
    return None

def check_user_has_extension(discord_user_id):
    """Sprawdza czy użytkownik ma już utworzone konto"""
    return get_user_account(discord_user_id) is not None

def get_user_extensions():
    """Pobiera istniejące numery użytkowników z bazy danych"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT discord_user_id, extension_number 
        FROM konta 
        WHERE is_active = 1
    ''')
    
    results = cursor.fetchall()
    conn.close()
    
    user_extensions = {}
    for discord_user_id, extension_number in results:
        user_extensions[int(discord_user_id)] = extension_number
    
    return user_extensions

def get_all_users():
    """Pobiera wszystkich użytkowników z bazy danych"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT discord_user_id, discord_user_name, extension_number, created_at, is_active
        FROM konta 
        ORDER BY created_at DESC
    ''')
    
    results = cursor.fetchall()
    conn.close()
    
    users = []
    for result in results:
        users.append({
            'discord_user_id': result[0],
            'discord_user_name': result[1],
            'extension_number': result[2],
            'created_at': result[3],
            'is_active': result[4]
        })
    
    return users

def update_user_status(discord_user_id, is_active):
    """Aktualizuje status konta użytkownika"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE konta 
        SET is_active = ?
        WHERE discord_user_id = ?
    ''', (is_active, str(discord_user_id)))
    
    conn.commit()
    conn.close()

def delete_user_account(discord_user_id):
    """Usuwa konto użytkownika z bazy danych (soft delete)"""
    update_user_status(discord_user_id, 0)

def get_stats():
    """Pobiera statystyki z bazy danych"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM konta WHERE is_active = 1')
    active_count = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM konta')
    total_count = cursor.fetchone()[0]
    
    conn.close()
    
    return {'active': active_count, 'total': total_count}

def assign_extension_to_user(discord_user_id, extension_number, extension_password):
    """Przypisuje istniejący numer do użytkownika (funkcja dla admina)"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    try:
        user = bot.get_user(int(discord_user_id))
        user_name = user.display_name if user else str(discord_user_id)
        
        cursor.execute('''
            INSERT INTO konta (discord_user_id, discord_user_name, extension_number, extension_password, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (str(discord_user_id), user_name, extension_number, extension_password, datetime.now()))
        
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def remove_user_account(discord_user_id):
    """Usuwa konto użytkownika (hard delete)"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        DELETE FROM konta 
        WHERE discord_user_id = ?
    ''', (str(discord_user_id),))
    
    conn.commit()
    conn.close()

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

    @discord.ui.button(label="Utwórz konto", style=discord.ButtonStyle.green)
    async def create(self, interaction: discord.Interaction, button: discord.ui.Button):

        await interaction.response.defer(ephemeral=True)

        try:
            if check_user_has_extension(interaction.user.id):
                await interaction.followup.send(
                    "Można posiadać tylko jeden numer!",
                    ephemeral=True
                )
                return

            ext = generate_extension()
            create_extension(ext, interaction.user.display_name, interaction.user.id)
            reload_pbx()
            data = get_extension_data(ext)

            real_ext = data["user"]["extension"]
            password = data["user"]["extPassword"]

            success = save_user_account(
                interaction.user.id,
                interaction.user.display_name,
                real_ext,
                password
            )
            
            if not success:
                await interaction.followup.send(
                    "Wystąpił błąd podczas zapisywania konta!",
                    ephemeral=True
                )
                return

            embed = discord.Embed(
                title="Twoje konto VoIP",
                color=0x00ff00
            )

            embed.add_field(name="Numer", value=f"`{real_ext}`", inline=False)
            embed.add_field(name="Hasło", value=f"||{password}||", inline=False)
            embed.add_field(name="Serwer SIP", value="`sip.voxelvoip.pl`", inline=False)
            embed.add_field(name="Domena", value="`sip.voxelvoip.pl`", inline=False)

            await interaction.user.send(embed=embed)

            await interaction.followup.send(
                "Konto utworzone, sprawdź DM",
                ephemeral=True
            )

        except Exception as e:
            await interaction.followup.send(
                f"Error: {e}",
                ephemeral=True
            )

class AdminPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Statystyki", style=discord.ButtonStyle.blurple)
    async def stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        stats = get_stats()
        
        embed = discord.Embed(
            title="Statystyki kont",
            color=0x00ff00
        )
        
        embed.add_field(name="Aktywne konta", value=str(stats['active']), inline=True)
        embed.add_field(name="Wszystkie konta", value=str(stats['total']), inline=True)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Lista użytkowników", style=discord.ButtonStyle.blurple)
    async def list_users(self, interaction: discord.Interaction, button: discord.ui.Button):
        users = get_all_users()
        
        if not users:
            await interaction.response.send_message("Brak użytkowników w bazie.", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="Lista użytkowników",
            color=0x00ff00
        )
        
        for user in users[:10]:
            status = "Aktywny" if user['is_active'] else "Nieaktywny"
            embed.add_field(
                name=f"{user['discord_user_name']} ({user['discord_user_id']})",
                value=f"Numer: {user['extension_number']}\nUtworzono: {user['created_at']}\nStatus: {status}",
                inline=False
            )
        
        if len(users) > 10:
            embed.set_footer(text=f"Pokażę tylko 10 z {len(users)} użytkowników")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

class AssignModal(discord.ui.Modal, title='Przypisz konto'):
    def __init__(self):
        super().__init__()
        
    user_id = discord.ui.TextInput(
        label='ID użytkownika Discord',
        placeholder='Wprowadź ID użytkownika',
        required=True,
        style=discord.TextStyle.short
    )
    
    extension = discord.ui.TextInput(
        label='Numer wewnętrzny',
        placeholder='Wprowadź numer (np. 10001)',
        required=True,
        style=discord.TextStyle.short
    )
    
    password = discord.ui.TextInput(
        label='Hasło SIP',
        placeholder='Wprowadź hasło dla numeru',
        required=True,
        style=discord.TextStyle.short
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            user_id = int(self.user_id.value)
            extension_number = self.extension.value
            extension_password = self.password.value
            
            if check_user_has_extension(user_id):
                await interaction.response.send_message(
                    "Ten użytkownik już ma przypisane konto!",
                    ephemeral=True
                )
                return
            
            success = assign_extension_to_user(user_id, extension_number, extension_password)
            
            if success:
                user = bot.get_user(user_id)
                if user:
                    embed = discord.Embed(
                        title="Twoje konto VoIP",
                        color=0x00ff00
                    )
                    embed.add_field(name="Numer", value=f"`{extension_number}`", inline=False)
                    embed.add_field(name="Hasło", value=f"||{extension_password}||", inline=False)
                    embed.add_field(name="Serwer SIP", value="`sip.voxelvoip.pl`", inline=False)
                    embed.add_field(name="Domena", value="`sip.voxelvoip.pl`", inline=False)
                    embed.set_footer(text="Konto zostało przypisane przez administratora")
                    
                    await user.send(embed=embed)
                
                await interaction.response.send_message(
                    f"Pomyślnie przypisano numer {extension_number} do użytkownika o ID {user_id}",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "Wystąpił błąd podczas przypisywania konta!",
                    ephemeral=True
                )
                
        except ValueError:
            await interaction.response.send_message(
                "Nieprawidłowe ID użytkownika!",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"Błąd: {e}",
                ephemeral=True
            )

class RemoveModal(discord.ui.Modal, title='Usuń konto użytkownika'):
    def __init__(self):
        super().__init__()
        
    user_id = discord.ui.TextInput(
        label='ID użytkownika Discord',
        placeholder='Wprowadź ID użytkownika',
        required=True,
        style=discord.TextStyle.short
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            user_id = int(self.user_id.value)
            
            account = get_user_account(user_id)
            if not account:
                await interaction.response.send_message(
                    "Ten użytkownik nie ma przypisanego konta!",
                    ephemeral=True
                )
                return
            
            remove_user_account(user_id)
            
            await interaction.response.send_message(
                f"Pomyślnie usunięto konto użytkownika o ID {user_id}",
                ephemeral=True
            )
                
        except ValueError:
            await interaction.response.send_message(
                "Nieprawidłowe ID użytkownika!",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"Błąd: {e}",
                ephemeral=True
            )

class AdminPanelExtended(AdminPanel):
    def __init__(self):
        super().__init__()
        
    @discord.ui.button(label="Przypisz konto", style=discord.ButtonStyle.green)
    async def assign_account(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AssignModal())
    
    @discord.ui.button(label="Usuń konto", style=discord.ButtonStyle.red)
    async def remove_account(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RemoveModal())

# ================= COMMANDS =================

@tree.command(name="panel", description="Wysyła panel z guzikiem")
async def panel(interaction: discord.Interaction):
    # Sprawdź czy użytkownik ma uprawnienia administratora
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Nie masz uprawnień do tej komendy!", ephemeral=True)
        return
    
    embed = discord.Embed(
        title="Utwórz konto",
        description="Kliknij przycisk poniżej aby utworzyć konto.",
        color=0x00ff00
    )

    await interaction.channel.send(embed=embed, view=Panel())
    await interaction.response.send_message("Panel wysłany", ephemeral=True)

@tree.command(name="admin", description="Panel administracyjny")
async def admin(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Nie masz uprawnień do tej komendy!", ephemeral=True)
        return
    
    embed = discord.Embed(
        title="Panel Administracyjny",
        description="Panel zarządzania kontami VoIP",
        color=0x00ff00
    )
    
    await interaction.response.send_message(embed=embed, view=AdminPanelExtended(), ephemeral=True)

@tree.command(name="statystyki", description="Wyświetla statystyki kont")
async def statistics(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Nie masz uprawnień do tej komendy!", ephemeral=True)
        return
    
    stats = get_stats()
    
    embed = discord.Embed(
        title="Statystyki kont",
        color=0x00ff00
    )
    
    embed.add_field(name="Aktywne konta", value=str(stats['active']), inline=True)
    embed.add_field(name="Wszystkie konta", value=str(stats['total']), inline=True)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="moje_konto", description="Sprawdza informacje o Twoim koncie VoIP")
async def my_account(interaction: discord.Interaction):
    account = get_user_account(interaction.user.id)
    
    if not account:
        await interaction.response.send_message(
            "Nie masz jeszcze utworzonego konta.",
            ephemeral=True
        )
        return
    
    embed = discord.Embed(
        title="Twoje konto VoIP",
        color=0x00ff00
    )
    
    embed.add_field(name="Numer", value=f"`{account['extension_number']}`", inline=False)
    embed.add_field(name="Hasło", value=f"||{account['extension_password']}||", inline=False)
    embed.add_field(name="Serwer SIP", value="`sip.voxelvoip.pl`", inline=False)
    embed.add_field(name="Domena", value="`sip.voxelvoip.pl`", inline=False)
    embed.add_field(name="Data utworzenia", value=account['created_at'], inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ================= START =================

@bot.event
async def on_ready():
    init_database()
    
    await tree.sync()
    print(f"Zalogowano jako {bot.user}")
    print(f"Baza danych: {DB_FILE}")

if __name__ == "__main__":
    bot.run(TOKEN)
