import discord
from discord import app_commands
from discord.ext import commands
import sqlite3
import os

# ================== НАСТРОЙКИ ==================
TOKEN = "ТВОЙ_ТОКЕН_ЗДЕСЬ"     # Токен бота
GUILD_ID = None                # ID сервера (int) для мгновенной синхронизации,
                               # либо None для глобальной синхронизации
DB_PATH = "players.db"
# ===============================================


# ---------- Работа с базой данных ----------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS players (
            discord_id  INTEGER PRIMARY KEY,
            steam_id    TEXT,
            balance     INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()


def get_player(discord_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT discord_id, steam_id, balance FROM players WHERE discord_id = ?", (discord_id,))
    row = cur.fetchone()
    conn.close()
    return row


def register_player(discord_id: int, steam_id: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO players (discord_id, steam_id, balance) VALUES (?, ?, 0)",
            (discord_id, steam_id)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def update_steam_id(discord_id: int, steam_id: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE players SET steam_id = ? WHERE discord_id = ?", (steam_id, discord_id))
    conn.commit()
    conn.close()


def change_balance(discord_id: int, amount: int):
    """Меняет баланс. Возвращает (ok, new_balance)."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT balance FROM players WHERE discord_id = ?", (discord_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return False, None
    new_balance = row[0] + amount
    if new_balance < 0:
        conn.close()
        return False, row[0]
    cur.execute("UPDATE players SET balance = ? WHERE discord_id = ?", (new_balance, discord_id))
    conn.commit()
    conn.close()
    return True, new_balance


# ---------- Бот ----------
intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    init_db()
    try:
        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
        else:
            synced = await bot.tree.sync()
        print(f"✅ Бот запущен как {bot.user} (ID: {bot.user.id})")
        print(f"🔄 Синхронизировано команд: {len(synced)}")
        print(f"📁 База данных: {os.path.abspath(DB_PATH)}")
    except Exception as e:
        print(f"❌ Ошибка синхронизации команд: {e}")


# ---------- Группа команд ec_ ----------
class EcGroup(app_commands.Group):
    pass


ec_group = EcGroup(name="ec", description="Игровые команды (экономика игроков)")


# ----- /ec_register -----
@ec_group.command(name="register", description="Зарегистрироваться в системе (указать Steam ID)")
@app_commands.describe(steam_id="Твой SteamID64 (17 цифр)")
async def ec_register(interaction: discord.Interaction, steam_id: str):
    if not (steam_id.isdigit() and len(steam_id) == 17):
        await interaction.response.send_message(
            "❌ Неверный формат Steam ID. Нужен SteamID64 (17 цифр).",
            ephemeral=True
        )
        return

    if register_player(interaction.user.id, steam_id):
        await interaction.response.send_message(
            f"✅ Ты зарегистрирован! Steam ID: `{steam_id}`\n💰 Баланс: **0** монет.",
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            "⚠️ Ты уже зарегистрирован. Используй `/ec_setsteam`, чтобы изменить Steam ID.",
            ephemeral=True
        )


# ----- /ec_setsteam -----
@ec_group.command(name="setsteam", description="Изменить свой Steam ID")
@app_commands.describe(steam_id="Новый SteamID64 (17 цифр)")
async def ec_setsteam(interaction: discord.Interaction, steam_id: str):
    if not (steam_id.isdigit() and len(steam_id) == 17):
        await interaction.response.send_message("❌ Некорректный SteamID64.", ephemeral=True)
        return

    if get_player(interaction.user.id) is None:
        await interaction.response.send_message(
            "❌ Ты ещё не зарегистрирован. Используй `/ec_register`.", ephemeral=True
        )
        return

    update_steam_id(interaction.user.id, steam_id)
    await interaction.response.send_message(f"✅ Steam ID обновлён: `{steam_id}`", ephemeral=True)


# ----- /ec_profile -----
@ec_group.command(name="profile", description="Показать профиль игрока")
@app_commands.describe(member="Игрок (по умолчанию — ты)")
async def ec_profile(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    player = get_player(target.id)

    if player is None:
        await interaction.response.send_message(
            f"❌ {target.mention} не зарегистрирован.", ephemeral=True
        )
        return

    discord_id, steam_id, balance = player
    embed = discord.Embed(title="📋 Профиль игрока", color=discord.Color.blue())
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="👤 Игрок", value=target.mention, inline=False)
    embed.add_field(name="🆔 Discord ID", value=f"`{discord_id}`", inline=True)
    embed.add_field(name="🎮 Steam ID", value=f"`{steam_id}`", inline=True)
    embed.add_field(name="💰 Баланс", value=f"**{balance:,}** монет", inline=False)

    await interaction.response.send_message(embed=embed)


# ----- /ec_balance -----
@ec_group.command(name="balance", description="Показать баланс игрока")
@app_commands.describe(member="Игрок (по умолчанию — ты)")
async def ec_balance(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    player = get_player(target.id)

    if player is None:
        await interaction.response.send_message("❌ Игрок не зарегистрирован.", ephemeral=True)
        return

    await interaction.response.send_message(f"💰 Баланс {target.mention}: **{player[2]:,}** монет")


# ----- /ec_addmoney (только админ) -----
@ec_group.command(name="addmoney", description="[АДМИН] Начислить монеты игроку")
@app_commands.describe(member="Игрок", amount="Сумма для начисления")
@app_commands.default_permissions(administrator=True)
async def ec_addmoney(interaction: discord.Interaction, member: discord.Member, amount: int):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Только для администраторов.", ephemeral=True)
        return

    if amount <= 0:
        await interaction.response.send_message("❌ Сумма должна быть больше нуля.", ephemeral=True)
        return

    if get_player(member.id) is None:
        await interaction.response.send_message("❌ Игрок не зарегистрирован.", ephemeral=True)
        return

    ok, new_balance = change_balance(member.id, amount)
    if not ok:
        await interaction.response.send_message("❌ Не удалось изменить баланс.", ephemeral=True)
        return

    await interaction.response.send_message(
        f"✅ {member.mention} получил **{amount:,}** монет.\n"
        f"💰 Новый баланс: **{new_balance:,}**."
    )


# ----- /ec_removemoney (только админ) -----
@ec_group.command(name="removemoney", description="[АДМИН] Списать монеты у игрока")
@app_commands.describe(member="Игрок", amount="Сумма для списания")
@app_commands.default_permissions(administrator=True)
async def ec_removemoney(interaction: discord.Interaction, member: discord.Member, amount: int):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Только для администраторов.", ephemeral=True)
        return

    if amount <= 0:
        await interaction.response.send_message("❌ Сумма должна быть больше нуля.", ephemeral=True)
        return

    if get_player(member.id) is None:
        await interaction.response.send_message("❌ Игрок не зарегистрирован.", ephemeral=True)
        return

    ok, new_balance = change_balance(member.id, -amount)
    if not ok:
        await interaction.response.send_message(
            f"❌ Недостаточно средств. Текущий баланс: **{new_balance:,}** монет.", ephemeral=True
        )
        return

    await interaction.response.send_message(
        f"✅ У {member.mention} списано **{amount:,}** монет.\n"
        f"💰 Новый баланс: **{new_balance:,}**."
    )


# ----- /ec_setmoney (только админ, установить точное значение) -----
@ec_group.command(name="setmoney", description="[АДМИН] Установить точный баланс игрока")
@app_commands.describe(member="Игрок", amount="Новое значение баланса")
@app_commands.default_permissions(administrator=True)
async def ec_setmoney(interaction: discord.Interaction, member: discord.Member, amount: int):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Только для администраторов.", ephemeral=True)
        return

    if amount < 0:
        await interaction.response.send_message("❌ Баланс не может быть отрицательным.", ephemeral=True)
        return

    player = get_player(member.id)
    if player is None:
        await interaction.response.send_message("❌ Игрок не зарегистрирован.", ephemeral=True)
        return

    diff = amount - player[2]
    ok, new_balance = change_balance(member.id, diff)
    if not ok:
        await interaction.response.send_message("❌ Не удалось изменить баланс.", ephemeral=True)
        return

    await interaction.response.send_message(
        f"✅ Баланс {member.mention} установлен: **{new_balance:,}** монет."
    )


# ----- /ec_top (топ игроков по балансу) -----
@ec_group.command(name="top", description="Топ-10 игроков по балансу")
async def ec_top(interaction: discord.Interaction):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT discord_id, steam_id, balance FROM players ORDER BY balance DESC LIMIT 10")
    rows = cur.fetchall()
    conn.close()

    if not rows:
        await interaction.response.send_message("📭 Пока нет зарегистрированных игроков.", ephemeral=True)
        return

    embed = discord.Embed(title="🏆 Топ-10 игроков по балансу", color=discord.Color.gold())
    medals = ["🥇", "🥈", "🥉"]
    for i, (discord_id, steam_id, balance) in enumerate(rows):
        prefix = medals[i] if i < 3 else f"`#{i+1}`"
        try:
            user = await bot.fetch_user(discord_id)
            name = user.display_name
        except Exception:
            name = f"ID {discord_id}"
        embed.add_field(
            name=f"{prefix} {name}",
            value=f"💰 **{balance:,}** монет\n🎮 `{steam_id}`",
            inline=False
        )
    await interaction.response.send_message(embed=embed)


# Добавляем группу к дереву команд
bot.tree.add_command(ec_group)


# ---------- Запуск ----------
if __name__ == "__main__":
    if TOKEN == "ТВОЙ_ТОКЕН_ЗДЕСЬ":
        print("⚠️  Укажи токен бота в переменной TOKEN!")
    else:
        bot.run(TOKEN)