import discord
from discord import app_commands
from discord.ext import commands
import sqlite3
import os

# ================== НАСТРОЙКИ ==================
TOKEN = "ТВОЙ_ТОКЕН_ЗДЕСЬ"
GUILD_ID = None                # int для быстрой синхронизации на одном сервере, либо None
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


def register_player(discord_id: int, steam_id: str, start_balance: int = 0) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO players (discord_id, steam_id, balance) VALUES (?, ?, ?)",
            (discord_id, steam_id, start_balance)
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


def delete_player(discord_id: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM players WHERE discord_id = ?", (discord_id,))
    changed = cur.rowcount > 0
    conn.commit()
    conn.close()
    return changed


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


# ---------- Хелпер: проверка админа ----------
def is_admin(interaction: discord.Interaction) -> bool:
    return (
        interaction.guild is not None
        and interaction.user.guild_permissions.administrator
    )


# ---------- Группа команд ec ----------
class EcGroup(app_commands.Group):
    pass


ec_group = EcGroup(name="ec", description="Игровые команды (экономика игроков)")


# ==================================================
#                    ПОМОЩЬ
# ==================================================

@ec_group.command(name="help", description="Показать все команды бота")
async def ec_help(interaction: discord.Interaction):
    is_adm = is_admin(interaction)

    embed = discord.Embed(
        title="📖 Список команд бота",
        description="Все команды используют префикс `/ec_`",
        color=discord.Color.blurple()
    )

    # ----- Игровые команды -----
    embed.add_field(
        name="👤 Для игроков",
        value=(
            "`/ec_help` — показать это сообщение\n"
            "`/ec_register <steam_id>` — зарегистрироваться (SteamID64, 17 цифр)\n"
            "`/ec_setsteam <steam_id>` — изменить свой Steam ID\n"
            "`/ec_profile [@user]` — профиль игрока\n"
            "`/ec_balance [@user]` — показать баланс\n"
            "`/ec_top` — топ-10 игроков по балансу"
        ),
        inline=False
    )

    # ----- Админ-команды (видны только админам) -----
    if is_adm:
        embed.add_field(
            name="🛡️ Для администраторов",
            value=(
                "`/ec_addmoney @user <сумма>` — начислить монеты\n"
                "`/ec_removemoney @user <сумма>` — списать монеты\n"
                "`/ec_setmoney @user <сумма>` — установить точный баланс\n"
                "`/ec_addplayer <discord_id> <steam_id> [баланс]` — добавить игрока вручную\n"
                "`/ec_delplayer @user` — удалить игрока из базы"
            ),
            inline=False
        )
        embed.set_footer(text="Ты видишь админ-команды, потому что у тебя есть права администратора.")
    else:
        embed.set_footer(text="Админ-команды скрыты.")

    await interaction.response.send_message(embed=embed, ephemeral=True)


# ==================================================
#                  ИГРОВЫЕ КОМАНДЫ
# ==================================================

@ec_group.command(name="register", description="Зарегистрироваться в системе (указать Steam ID)")
@app_commands.describe(steam_id="Твой SteamID64 (17 цифр)")
async def ec_register(interaction: discord.Interaction, steam_id: str):
    if not (steam_id.isdigit() and len(steam_id) == 17):
        await interaction.response.send_message(
            "❌ Неверный формат Steam ID. Нужен SteamID64 (17 цифр).", ephemeral=True
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


@ec_group.command(name="balance", description="Показать баланс игрока")
@app_commands.describe(member="Игрок (по умолчанию — ты)")
async def ec_balance(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    player = get_player(target.id)

    if player is None:
        await interaction.response.send_message("❌ Игрок не зарегистрирован.", ephemeral=True)
        return

    await interaction.response.send_message(f"💰 Баланс {target.mention}: **{player[2]:,}** монет")


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


# ==================================================
#                  АДМИН-КОМАНДЫ
# ==================================================

@ec_group.command(name="addmoney", description="[АДМИН] Начислить монеты игроку")
@app_commands.describe(member="Игрок", amount="Сумма для начисления")
@app_commands.default_permissions(administrator=True)
async def ec_addmoney(interaction: discord.Interaction, member: discord.Member, amount: int):
    if not is_admin(interaction):
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
        f"✅ {member.mention} получил **{amount:,}** монет.\n💰 Новый баланс: **{new_balance:,}**."
    )


@ec_group.command(name="removemoney", description="[АДМИН] Списать монеты у игрока")
@app_commands.describe(member="Игрок", amount="Сумма для списания")
@app_commands.default_permissions(administrator=True)
async def ec_removemoney(interaction: discord.Interaction, member: discord.Member, amount: int):
    if not is_admin(interaction):
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
        f"✅ У {member.mention} списано **{amount:,}** монет.\n💰 Новый баланс: **{new_balance:,}**."
    )


@ec_group.command(name="setmoney", description="[АДМИН] Установить точный баланс игрока")
@app_commands.describe(member="Игрок", amount="Новое значение баланса")
@app_commands.default_permissions(administrator=True)
async def ec_setmoney(interaction: discord.Interaction, member: discord.Member, amount: int):
    if not is_admin(interaction):
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


# ----- /ec_addplayer — добавление игрока админом -----
@ec_group.command(name="addplayer", description="[АДМИН] Вручную добавить игрока в базу")
@app_commands.describe(
    member="Игрок на сервере (необязательно, если указываешь Discord ID)",
    discord_id="Discord ID игрока (если не выбираешь через @)",
    steam_id="SteamID64 (17 цифр)",
    balance="Начальный баланс (по умолчанию 0)"
)
@app_commands.default_permissions(administrator=True)
async def ec_addplayer(
    interaction: discord.Interaction,
    steam_id: str,
    member: discord.Member = None,
    discord_id: str = None,
    balance: int = 0
):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Только для администраторов.", ephemeral=True)
        return

    # Определяем целевой Discord ID
    if member is not None:
        target_id = member.id
    elif discord_id is not None and discord_id.isdigit():
        target_id = int(discord_id)
    else:
        await interaction.response.send_message(
            "❌ Укажи либо `member` (@игрок), либо `discord_id` (число).", ephemeral=True
        )
        return

    # Проверка Steam ID
    if not (steam_id.isdigit() and len(steam_id) == 17):
        await interaction.response.send_message("❌ SteamID должен быть SteamID64 (17 цифр).", ephemeral=True)
        return

    if balance < 0:
        await interaction.response.send_message("❌ Баланс не может быть отрицательным.", ephemeral=True)
        return

    if get_player(target_id) is not None:
        await interaction.response.send_message(
            f"⚠️ Игрок с Discord ID `{target_id}` уже есть в базе.", ephemeral=True
        )
        return

    if register_player(target_id, steam_id, balance):
        who = member.mention if member else f"`{target_id}`"
        await interaction.response.send_message(
            f"✅ Игрок {who} добавлен.\n"
            f"🎮 Steam ID: `{steam_id}`\n"
            f"💰 Начальный баланс: **{balance:,}** монет."
        )
    else:
        await interaction.response.send_message("❌ Не удалось добавить игрока.", ephemeral=True)


# ----- /ec_delplayer — удаление игрока -----
@ec_group.command(name="delplayer", description="[АДМИН] Удалить игрока из базы")
@app_commands.describe(member="Игрок, которого нужно удалить")
@app_commands.default_permissions(administrator=True)
async def ec_delplayer(interaction: discord.Interaction, member: discord.Member):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Только для администраторов.", ephemeral=True)
        return

    if not delete_player(member.id):
        await interaction.response.send_message("❌ Игрок не найден в базе.", ephemeral=True)
        return

    await interaction.response.send_message(f"🗑️ Игрок {member.mention} удалён из базы.")


# Добавляем группу к дереву команд
bot.tree.add_command(ec_group)


# ---------- Запуск ----------
if __name__ == "__main__":
    if TOKEN == "ТВОЙ_ТОКЕН_ЗДЕСЬ":
        print("⚠️  Укажи токен бота в переменной TOKEN!")
    else:
        bot.run(TOKEN)
