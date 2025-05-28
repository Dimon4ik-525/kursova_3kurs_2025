import asyncio
import logging
from typing import Dict, List, Union, Optional
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.utils.markdown import hbold
import re
import asyncpg
from config import BOT_TOKEN, DB_USER, DB_PASS, DB_HOST, DB_NAME, ADMIN_IDS


# Configure logging
logging.basicConfig(level=logging.INFO)

# Initialize bot and dispatcher
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Routers
main_router = Router()
admin_router = Router()

# Connection pool
pool: Optional[asyncpg.Pool] = None

class UserStates(StatesGroup):
    searching = State()
    search_skin_weapon = State()
    search_skin = State()  # Новий стан для пошуку скіна

# FSM States
class AdminStates(StatesGroup):
    # Case states
    add_case = State()
    edit_case_select = State()
    edit_case_name = State()
    edit_case_image = State()
    delete_case_confirm = State()

    # Skin states
    add_skin = State()
    add_skin_name = State()
    add_skin_rarity = State()
    add_skin_stattrak = State()
    add_skin_souvenir = State()
    add_skin_image = State()
    add_skin_weapon = State()

    edit_skin_select = State()
    edit_skin_field = State()
    edit_skin_value = State()

    delete_skin_confirm = State()

    # Weapon states
    add_weapon = State()
    add_weapon_name = State()
    edit_weapon_select = State()
    edit_weapon_name = State()
    delete_weapon_confirm = State()

    # Skinwear states
    add_skinwear = State()
    add_skinwear_skin = State()
    add_skinwear_weartype = State()
    add_skinwear_floatmin = State()
    add_skinwear_floatmax = State()

    # CaseSkins states
    add_caseskin = State()
    add_caseskin_case = State()
    add_caseskin_skin = State()
    remove_caseskin = State()
    remove_caseskin_confirm = State()


# Database functions
async def init_db():
    global pool
    pool = await asyncpg.create_pool(
        user=DB_USER,
        password=DB_PASS,
        host=DB_HOST,
        database=DB_NAME
    )

    # Create tables if they don't exist
    async with pool.acquire() as conn:
        await conn.execute('''
        CREATE TABLE IF NOT EXISTS cases (
            case_id SERIAL PRIMARY KEY,
            case_name TEXT NOT NULL UNIQUE,
            image_case TEXT
        )
        ''')

        await conn.execute('''
        CREATE TABLE IF NOT EXISTS weapons (
            weapon_id SERIAL PRIMARY KEY,
            weapon_name TEXT NOT NULL UNIQUE
        )
        ''')

        await conn.execute('''
        CREATE TABLE IF NOT EXISTS skins (
            skin_id SERIAL PRIMARY KEY,
            skin_name TEXT NOT NULL,
            rarity TEXT,
            stattrak BOOLEAN DEFAULT FALSE,
            souvenir BOOLEAN DEFAULT FALSE,
            image_skin TEXT,
            weapon_id INTEGER REFERENCES weapons(weapon_id) ON DELETE CASCADE
        )
        ''')

        await conn.execute('''
        CREATE TABLE IF NOT EXISTS skinwear (
            skinwear_id SERIAL PRIMARY KEY,
            skin_id INTEGER REFERENCES skins(skin_id) ON DELETE CASCADE,
            weartype TEXT,
            floatmin FLOAT,
            floatmax FLOAT
        )
        ''')

        await conn.execute('''
        CREATE TABLE IF NOT EXISTS caseskins (
            case_id INTEGER REFERENCES cases(case_id) ON DELETE CASCADE,
            skin_id INTEGER REFERENCES skins(skin_id) ON DELETE CASCADE,
            PRIMARY KEY (case_id, skin_id)
        )
        ''')


# Utility functions for database operations
async def get_all_cases() -> List[asyncpg.Record]:
    async with pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM cases ORDER BY case_name")


async def get_case(case_id: int) -> asyncpg.Record:
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM cases WHERE case_id = $1", case_id)



async def get_case_skins(case_id: int) -> List[asyncpg.Record]:
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT s.*, w.weapon_name FROM skins s
            JOIN weapons w ON s.weapon_id = w.weapon_id
            JOIN caseskins cs ON s.skin_id = cs.skin_id
            WHERE cs.case_id = $1
            ORDER BY s.rarity DESC, w.weapon_name, s.skin_name
        """, case_id)


async def get_all_weapons() -> List[asyncpg.Record]:
    async with pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM weapons ORDER BY weapon_name")


async def get_weapon(weapon_id: int) -> asyncpg.Record:
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM weapons WHERE weapon_id = $1", weapon_id)


async def get_weapon_skins(weapon_id: int) -> List[asyncpg.Record]:
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT s.*, w.weapon_name FROM skins s
            JOIN weapons w ON s.weapon_id = w.weapon_id
            WHERE s.weapon_id = $1
            ORDER BY s.rarity DESC, s.skin_name
        """, weapon_id)


async def get_all_skins() -> List[asyncpg.Record]:
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT s.*, w.weapon_name FROM skins s
            JOIN weapons w ON s.weapon_id = w.weapon_id
            ORDER BY w.weapon_name, s.skin_name
        """)


async def get_skin(skin_id: int) -> asyncpg.Record:
    async with pool.acquire() as conn:
        return await conn.fetchrow("""
            SELECT s.*, w.weapon_name FROM skins s
            JOIN weapons w ON s.weapon_id = w.weapon_id
            WHERE s.skin_id = $1
        """, skin_id)


async def get_skin_wear(skin_id: int) -> List[asyncpg.Record]:
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT * FROM skinwear
            WHERE skin_id = $1
            ORDER BY weartype
        """, skin_id)


async def add_case_to_db(case_name: str, image_case: str = None) -> int:
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "INSERT INTO cases (case_name, image_case) VALUES ($1, $2) RETURNING case_id",
            case_name, image_case
        )


async def update_case(case_id: int, field: str, value: str) -> bool:
    async with pool.acquire() as conn:
        await conn.execute(
            f"UPDATE cases SET {field} = $1 WHERE case_id = $2",
            value, case_id
        )
        return True


async def delete_case(case_id: int) -> bool:
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM cases WHERE case_id = $1", case_id)
        return True


async def add_weapon_to_db(weapon_name: str) -> int:
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "INSERT INTO weapons (weapon_name) VALUES ($1) RETURNING weapon_id",
            weapon_name
        )


async def update_weapon(weapon_id: int, weapon_name: str) -> bool:
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE weapons SET weapon_name = $1 WHERE weapon_id = $2",
            weapon_name, weapon_id
        )
        return True


async def delete_weapon(weapon_id: int) -> bool:
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM weapons WHERE weapon_id = $1", weapon_id)
        return True


async def add_skin_to_db(skin_name: str, weapon_id: int, rarity: str = None,
                         stattrak: bool = False, souvenir: bool = False,
                         image_skin: str = None) -> int:
    async with pool.acquire() as conn:
        return await conn.fetchval(
            """INSERT INTO skins (skin_name, weapon_id, rarity, stattrak, souvenir, image_skin)
               VALUES ($1, $2, $3, $4, $5, $6) RETURNING skin_id""",
            skin_name, weapon_id, rarity, stattrak, souvenir, image_skin
        )


async def update_skin(skin_id: int, field: str, value: str) -> bool:
    async with pool.acquire() as conn:
        if field in ('stattrak', 'souvenir'):
            # Convert string to boolean for boolean fields
            value = value.lower() in ('true', 'yes', '1')

        await conn.execute(
            f"UPDATE skins SET {field} = $1 WHERE skin_id = $2",
            value, skin_id
        )
        return True


async def delete_skin(skin_id: int) -> bool:
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM skins WHERE skin_id = $1", skin_id)
        return True


async def add_skinwear_to_db(skin_id: int, weartype: str, floatmin: float, floatmax: float) -> int:
    async with pool.acquire() as conn:
        return await conn.fetchval(
            """INSERT INTO skinwear (skin_id, weartype, floatmin, floatmax)
               VALUES ($1, $2, $3, $4) RETURNING skinwear_id""",
            skin_id, weartype, floatmin, floatmax
        )


async def add_skin_to_case(case_id: int, skin_id: int) -> bool:
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO caseskins (case_id, skin_id) VALUES ($1, $2)",
                case_id, skin_id
            )
            return True
    except asyncpg.UniqueViolationError:
        logging.error(f"Skin {skin_id} already exists in case {case_id}")
        return False
    except Exception as e:
        logging.error(f"Error adding skin to case: {e}")
        return False


async def remove_skin_from_case(case_id: int, skin_id: int) -> bool:
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM caseskins WHERE case_id = $1 AND skin_id = $2",
            case_id, skin_id
        )
        return True


# Helper function to check if user is admin
def is_admin(user_id: int) -> bool:
    logging.info(f"Checking if user_id={user_id} is admin. ADMIN_IDS={ADMIN_IDS}")
    return user_id in ADMIN_IDS


# Keyboard builders
def build_main_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="Кейси", callback_data="view_cases")
    kb.button(text="Зброя", callback_data="view_weapons")
    kb.button(text="Всі скіни", callback_data="view_skins")
    kb.button(text="Пошук скіна", callback_data = "search_skin")
    kb.adjust(2)
    return kb.as_markup()

def build_admin_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="Керування кейсами", callback_data="admin_cases")
    kb.button(text="Керування зброєю", callback_data="admin_weapons")
    kb.button(text="Керування скінами", callback_data="admin_skins")
    kb.button(text="Кейс-Скін зв'язок", callback_data="admin_caseskins")
    kb.button(text="⬅️ Повернутись в меню", callback_data="main_menu")
    kb.adjust(2, 2, 1)
    return kb.as_markup()


def build_cases_keyboard(cases: List[asyncpg.Record]):
    kb = InlineKeyboardBuilder()
    for case in cases:
        kb.button(
            text=f"{case['case_name']}",
            callback_data=f"case_{case['case_id']}"
        )
    kb.button(text="⬅️ Назад", callback_data="main_menu")
    kb.adjust(1)
    return kb.as_markup()


def build_weapons_keyboard(weapons: List[asyncpg.Record]):
    kb = InlineKeyboardBuilder()
    for weapon in weapons:
        kb.button(
            text=f"{weapon['weapon_name']}",
            callback_data=f"weapon_{weapon['weapon_id']}"
        )
    kb.button(text="⬅️ Назад", callback_data="main_menu")
    kb.adjust(1)
    return kb.as_markup()


def build_admin_cases_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Додати кейс", callback_data="add_case")
    kb.button(text="✏️ Редагувати кейс", callback_data="edit_case")
    kb.button(text="🗑️ Видалити кейс", callback_data="delete_case")
    kb.button(text="⬅️ Назад", callback_data="admin_menu")
    kb.adjust(2, 2)
    markup = kb.as_markup()
    logging.info(f"Built admin_cases keyboard: {markup}")
    return kb.as_markup()


def build_admin_weapons_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Додати зброю", callback_data="add_weapon")
    kb.button(text="✏️ Редагувати зброю", callback_data="edit_weapon")
    kb.button(text="🗑️ Видалити зброю", callback_data="delete_weapon")
    kb.button(text="⬅️ Назад", callback_data="admin_menu")
    kb.adjust(2, 2)
    markup = kb.as_markup()
    logging.info(f"Built admin_weapons keyboard: {markup}")
    return kb.as_markup()


def build_admin_skins_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Додати скін", callback_data="add_skin")
    kb.button(text="✏️ Редагувати скін", callback_data="edit_skin")
    kb.button(text="🗑️ Видалити скін", callback_data="delete_skin")
    kb.button(text="➕ Додати Skin Wear", callback_data="add_skinwear")
    kb.button(text="⬅️ Назад", callback_data="admin_menu")
    kb.adjust(2, 2)
    markup = kb.as_markup()
    logging.info(f"Built admin_skins keyboard: {markup}")
    return kb.as_markup()


def build_admin_caseskins_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Додати скін до кейса", callback_data="add_caseskin")
    kb.button(text="➖ Видалити скін з кейса", callback_data="remove_caseskin")
    kb.button(text="⬅️ Назад", callback_data="admin_menu")
    kb.adjust(1)
    return kb.as_markup()


def build_select_case_keyboard(cases: List[asyncpg.Record], action_prefix: str):
    kb = InlineKeyboardBuilder()
    for case in cases:
        kb_data = f"{action_prefix}_{case['case_id']}"
        kb.button(text=f"{case['case_name']}", callback_data=kb_data)
    kb.button(text="⬅️ Скасувати", callback_data="admin_menu")
    kb.adjust(1)
    return kb.as_markup()


def build_select_weapon_keyboard(weapons: List[asyncpg.Record], action_prefix: str):
    kb = InlineKeyboardBuilder()
    for weapon in weapons:
        kb_data = f"{action_prefix}_{weapon['weapon_id']}"
        kb.button(text=f"{weapon['weapon_name']}", callback_data=kb_data)
    kb.button(text="⬅️ Скасувати", callback_data="admin_menu")
    kb.adjust(1)
    return kb.as_markup()


def build_select_skin_keyboard(skins: List[asyncpg.Record], action_prefix: str):
    kb = InlineKeyboardBuilder()
    for skin in skins:
        kb_data = f"{action_prefix}_{skin['skin_id']}"
        kb.button(
            text=f"{skin['weapon_name']} | {skin['skin_name']}",
            callback_data=kb_data
        )
    kb.button(text="⬅️ Скасувати", callback_data="admin_menu")
    kb.adjust(1)
    return kb.as_markup()


def build_edit_skin_fields_keyboard(skin_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="Назва", callback_data=f"edit_skin_field_{skin_id}_skin_name")
    kb.button(text="Rarity", callback_data=f"edit_skin_field_{skin_id}_rarity")
    kb.button(text="StatTrak", callback_data=f"edit_skin_field_{skin_id}_stattrak")
    kb.button(text="Souvenir", callback_data=f"edit_skin_field_{skin_id}_souvenir")
    kb.button(text="Image URL", callback_data=f"edit_skin_field_{skin_id}_image_skin")
    kb.button(text="⬅️ Скасувати", callback_data="admin_menu")
    kb.adjust(2, 2, 1, 1)
    return kb.as_markup()


def build_wear_types_keyboard(skin_id: int):
    kb = InlineKeyboardBuilder()
    wear_types = ["Factory New", "Minimal Wear", "Field-Tested", "Well-Worn", "Battle-Scarred"]
    for wear in wear_types:
        kb.button(text=wear, callback_data=f"wear_type_{skin_id}_{wear}")
    kb.button(text="⬅️ Скасувати", callback_data="admin_menu")
    kb.adjust(1)
    return kb.as_markup()


def build_case_skin_view_keyboard(case_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Повернутись до кейсів", callback_data="view_cases")
    kb.button(text="🏠 Головне меню", callback_data="main_menu")
    kb.adjust(1)
    return kb.as_markup()


def build_weapon_skin_view_keyboard(weapon_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Повернутись до зброї", callback_data="view_weapons")
    kb.button(text="🏠 Головне меню", callback_data="main_menu")
    kb.adjust(1)
    return kb.as_markup()


def build_skin_view_keyboard(skin_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Повернутись до скінів", callback_data="view_skins")
    kb.button(text="🏠 Головне меню", callback_data="main_menu")
    kb.adjust(1)
    return kb.as_markup()


def build_confirm_keyboard(action: str, item_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Так", callback_data=f"confirm_{action}_{item_id}")
    kb.button(text="❌ Ні", callback_data="admin_menu")
    kb.adjust(2)
    return kb.as_markup()

def build_search_weapons_keyboard(weapons: List[asyncpg.Record]):
    kb = InlineKeyboardBuilder()
    for weapon in weapons:
        kb.button(
            text=f"{weapon['weapon_name']}",
            callback_data=f"search_weapon_{weapon['weapon_id']}"
        )
    kb.button(text="⬅️ Скасувати", callback_data="admin_menu")
    kb.adjust(1)
    return kb.as_markup()


# Main menu handlers
@main_router.message(Command("start"))
async def cmd_start(message: Message):
    logging.info(f"User ID: {message.from_user.id}")
    await message.answer(
        f"Ласкаво просимо до CS2 Items Management Bot, {(message.from_user.full_name)}!\n\n"
        f"Цей бот дозволяє вам переглядати предмети CS2, включаючи кейси, зброю та скіни.\n\n"
        f"Виберіть варіант:",
        reply_markup=build_main_keyboard()
    )


@main_router.message(Command("admin"))
async def cmd_admin(message: Message):
    user_id = message.from_user.id
    logging.info(f"Processing /admin command for user_id={user_id}, ADMIN_IDS={ADMIN_IDS}")
    if is_admin(user_id):
        logging.info("User is admin, showing admin panel")
        await message.answer(
            f"Ласкаво просимо до панелі адміністратора, {message.from_user.full_name}!\n\n"
            f"Тут ви можете керувати елементами CS2 у базі даних.\n\n"
            f"Виберіть варіант:",
            reply_markup=build_admin_keyboard()
        )
    else:
        logging.warning(f"User_id={user_id} is not an admin")
        await message.answer("У вас немає дозволу на доступ до панелі адміністратора.")


@main_router.callback_query(F.data == "main_menu")
async def show_main_menu(callback: CallbackQuery):
    await callback.message.edit_text(
        "CS2 Items Management Bot\n\n"
        "Виберіть варіант:",
        reply_markup=build_main_keyboard()
    )
    await callback.answer()


@main_router.callback_query(F.data == "admin_menu")
async def show_admin_menu(callback: CallbackQuery):
    if is_admin(callback.from_user.id):
        await callback.message.edit_text(
            "Панель адміна\n\n"
            "Виберіть варіант::",
            reply_markup=build_admin_keyboard()
        )
    else:
        await callback.message.edit_text(
            "У вас немає дозволу на доступ до панелі адміністратора.",
            reply_markup=build_main_keyboard()
        )
    await callback.answer()


@main_router.callback_query(F.data == "view_cases")
async def show_cases(callback: CallbackQuery):
    cases = await get_all_cases()
    if cases:
        await callback.message.edit_text(
            "📦 Доступні кейси:\n\n"
            "Виберіть кейс, щоб переглянути його скіни:",
            reply_markup=build_cases_keyboard(cases)
        )
    else:
        await callback.message.edit_text(
            "Кейсів не знайдено.",
            reply_markup=build_main_keyboard()
        )
    await callback.answer()


@main_router.callback_query(F.data.startswith("case_"))
async def show_case_details(callback: CallbackQuery):
    case_id = int(callback.data.split("_")[1])
    case = await get_case(case_id)
    skins = await get_case_skins(case_id)

    if case:
        case_info = f"📦 {(case['case_name'])}\n\n"

        if skins:
            case_info += "🎨 Скіни в цьому кейсі:\n\n"

            current_rarity = None
            for skin in skins:
                # Group skins by rarity
                if skin['rarity'] != current_rarity:
                    current_rarity = skin['rarity']
                    case_info += f"\n{(current_rarity)}:\n"

                # Add StatTrak and Souvenir indicators
                special = []
                if skin['stattrak']:
                    special.append("StatTrak™")
                if skin['souvenir']:
                    special.append("Souvenir")

                special_text = f" ({', '.join(special)})" if special else ""

                case_info += f"• {skin['weapon_name']} | {skin['skin_name']}{special_text}\n"
        else:
            case_info += "В цьому кейсів немає скінів."

        await callback.message.edit_text(
            case_info,
            reply_markup=build_case_skin_view_keyboard(case_id)
        )
    else:
        await callback.message.edit_text(
            "Кейс не знайдено.",
            reply_markup=build_main_keyboard()
        )
    await callback.answer()


@main_router.callback_query(F.data == "view_weapons")
async def show_weapons(callback: CallbackQuery):
    weapons = await get_all_weapons()
    if weapons:
        await callback.message.edit_text(
            "🔫 Доступна зброя:\n\n"
            "Виберіть зброю, щоб переглянути її скіни:",
            reply_markup=build_weapons_keyboard(weapons)
        )
    else:
        await callback.message.edit_text(
            "Зброю не знайдено.",
            reply_markup=build_main_keyboard()
        )
    await callback.answer()


@main_router.callback_query(F.data.startswith("weapon_"))
async def show_weapon_details(callback: CallbackQuery):
    weapon_id = int(callback.data.split("_")[1])
    weapon = await get_weapon(weapon_id)
    skins = await get_weapon_skins(weapon_id)

    if weapon:
        weapon_info = f"🔫 {(weapon['weapon_name'])}\n\n"

        if skins:
            weapon_info += "🎨 Доступні скіни:\n\n"

            current_rarity = None
            for skin in skins:
                # Group skins by rarity
                if skin['rarity'] != current_rarity:
                    current_rarity = skin['rarity']
                    weapon_info += f"\n{(current_rarity)}:\n"

                # Add StatTrak and Souvenir indicators
                special = []
                if skin['stattrak']:
                    special.append("StatTrak™")
                if skin['souvenir']:
                    special.append("Souvenir")

                special_text = f" ({', '.join(special)})" if special else ""

                weapon_info += f"• {skin['skin_name']}{special_text}\n"
        else:
            weapon_info += "Для цієї зброї немає скінів."

        await callback.message.edit_text(
            weapon_info,
            reply_markup=build_weapon_skin_view_keyboard(weapon_id)
        )
    else:
        await callback.message.edit_text(
            "Зброя не знайдена.",
            reply_markup=build_main_keyboard()
        )
    await callback.answer()


@main_router.callback_query(F.data == "view_skins")
async def show_all_skins(callback: CallbackQuery):
    skins = await get_all_skins()

    if skins:
        # Group skins by weapon
        weapons_dict = {}
        for skin in skins:
            weapon_name = skin['weapon_name']
            if weapon_name not in weapons_dict:
                weapons_dict[weapon_name] = []

            # Add StatTrak and Souvenir indicators
            special = []
            if skin['stattrak']:
                special.append("StatTrak™")
            if skin['souvenir']:
                special.append("Souvenir")

            special_text = f" ({', '.join(special)})" if special else ""

            weapons_dict[weapon_name].append({
                "name": skin['skin_name'],
                "rarity": skin['rarity'],
                "special": special_text
            })

        # Build message with all skins grouped by weapon
        skins_info = "🎨 Усі доступні скіни:\n\n"

        for weapon, weapon_skins in sorted(weapons_dict.items()):
            skins_info += f"\n{(weapon)}:\n"

            # Group by rarity within each weapon
            rarity_dict = {}
            for skin in weapon_skins:
                rarity = skin['rarity'] or "Невідомо"
                if rarity not in rarity_dict:
                    rarity_dict[rarity] = []
                rarity_dict[rarity].append(f"• {skin['name']}{skin['special']}")

            # Add skins by rarity
            for rarity in sorted(rarity_dict.keys()):
                skins_info += f"{rarity}:\n"
                skins_info += "\n".join(rarity_dict[rarity]) + "\n\n"

        # Send in chunks if too long
        if len(skins_info) > 4096:
            chunks = [skins_info[i:i + 4096] for i in range(0, len(skins_info), 4096)]
            for i, chunk in enumerate(chunks):
                if i == 0:
                    await callback.message.edit_text(
                        chunk,
                        reply_markup=build_main_keyboard()
                    )
                else:
                    await callback.message.answer(chunk)
        else:
            await callback.message.edit_text(
                skins_info,
                reply_markup=build_main_keyboard()
            )
    else:
        await callback.message.edit_text(
            "У базі даних не знайдено скінів.",
            reply_markup=build_main_keyboard()
        )
    await callback.answer()


@main_router.callback_query(F.data == "search_skin")
async def start_skin_search(callback: CallbackQuery, state: FSMContext):
    try:
        weapons = await get_all_weapons()
        if weapons:
            keyboard = build_search_weapons_keyboard(weapons)  # Без await
            print(f"Type of keyboard: {type(keyboard)}")  # Для дебагу
            await callback.message.edit_text(
                "🎨 Пошук скіна\n\n"
                "Спочатку виберіть зброю:",
                reply_markup=keyboard
            )
            await state.set_state(UserStates.search_skin_weapon)
        else:
            await callback.message.edit_text(
                "⚠️ У базі даних немає зброї. Додайте зброю через адмін-панель.",
                reply_markup=build_main_keyboard()
            )
            await state.clear()
        await callback.answer()
    except Exception as e:
        logging.error(f"Error in start_skin_search: {e}")
        current_text = callback.message.text or ""
        if "⚠️ Виникла помилка." not in current_text:  # Уникаємо TelegramBadRequest
            try:
                await callback.message.edit_text(
                    "⚠️ Виникла помилка.",
                    reply_markup=build_main_keyboard()
                )
            except Exception as edit_error:
                logging.error(f"Failed to edit message in error handler: {edit_error}")
        await state.clear()

@main_router.callback_query(F.data.startswith("search_weapon_"))
async def select_weapon_for_search(callback: CallbackQuery, state: FSMContext):
    try:
        weapon_id = int(callback.data.split("_")[2])
        weapon = await get_weapon(weapon_id)
        if weapon:
            await state.update_data(weapon_id=weapon_id, weapon_name=weapon['weapon_name'])
            await callback.message.edit_text(
                f"🎨 Пошук скіна для {weapon['weapon_name']}\n\n"
                "Введіть назву скіна для пошуку (наприклад, 'Dragon Lore'):"
            )
            await state.set_state(UserStates.search_skin)
        else:
            await callback.message.edit_text(
                "⚠️ Зброю не знайдено.",
                reply_markup=build_main_keyboard()
            )
            await state.clear()
        await callback.answer()
    except Exception as e:
        logging.error(f"Error in select_weapon_for_search: {e}")
        await callback.message.edit_text("⚠️ Виникла помилка.", reply_markup=build_main_keyboard())
        await state.clear()

@admin_router.callback_query(F.data == "admin_cases")
async def admin_cases(callback: CallbackQuery, state: FSMContext):
    logging.info(f"Processing admin_cases for user_id={callback.from_user.id}")
    logging.info(f"Callback data: {callback.data}")
    current_state = await state.get_state()
    logging.info(f"Current FSM state: {current_state}")
    await state.clear()
    if is_admin(callback.from_user.id):
        current_text = callback.message.text or ""
        new_text = "📦 Управління кейсами\n\nВиберіть дію:"
        logging.info(f"Current text: '{current_text}' | New text: '{new_text}'")
        try:
            if current_text != new_text:
                await callback.message.edit_text(
                    new_text,
                    reply_markup=build_admin_cases_keyboard()
                )
                logging.info("Cases menu displayed")
            else:
                logging.info("Text unchanged, skipping edit")
        except Exception as e:
            logging.error(f"Error editing message in admin_cases: {e}")
            await callback.message.edit_text(
                "⚠️ Виникла помилка під час відображення меню кейсів.",
                reply_markup=build_admin_keyboard()
            )
    else:
        await callback.message.edit_text(
            "У вас немає дозволу на доступ до цього розділу.",
            reply_markup=build_main_keyboard()
        )
        logging.info("User is not admin")
    await callback.answer()

@main_router.message(UserStates.search_skin)
async def process_skin_search(message: Message, state: FSMContext):
    try:
        search_term = message.text.strip().lower()
        if not search_term:
            await message.answer("⚠️ Будь ласка, введіть коректну назву скіна.")
            return

        data = await state.get_data()
        weapon_id = data.get("weapon_id")
        weapon_name = data.get("weapon_name")

        async with pool.acquire() as conn:
            logging.info("Acquired connection for skins query")
            skins = await conn.fetch("""
                SELECT s.*, w.weapon_name 
                FROM skins s
                JOIN weapons w ON s.weapon_id = w.weapon_id
                WHERE LOWER(s.skin_name) LIKE $1 AND s.weapon_id = $2
                ORDER BY s.skin_name
            """, f"%{search_term}%", weapon_id)
            logging.info(f"Fetched {len(skins)} skins")

            if not skins:
                await message.answer(
                    f"⚠️ Скінів за запитом '{search_term}' для {weapon_name} не знайдено.",
                    reply_markup=build_main_keyboard()
                )
                await state.clear()
                return

            result = []
            for skin in skins:
                skin_id = skin['skin_id']
                wears = await get_skin_wear(skin_id)
                logging.info(f"Fetching cases for skin_id={skin_id}")
                cases = await conn.fetch("""
                    SELECT c.* 
                    FROM cases c
                    JOIN caseskins cs ON c.case_id = cs.case_id
                    WHERE cs.skin_id = $1
                    ORDER BY c.case_name
                """, skin_id)
                logging.info(f"Fetched {len(cases)} cases for skin_id={skin_id}")
                stattrak = "StatTrak™ " if skin['stattrak'] else ""
                souvenir = "Souvenir " if skin['souvenir'] else ""
                skin_info = [
                    f"🎨 Скін: {stattrak}{souvenir}{skin['weapon_name']} | {skin['skin_name']}",
                    f"Рідкість: {skin['rarity'] or 'Невідомо'}"
                ]
                if wears:
                    skin_info.append("\nТипи зносу:")
                    for wear in wears:
                        skin_info.append(f"• {wear['weartype']} (Float: {wear['floatmin']} - {wear['floatmax']})")
                if cases:
                    skin_info.append("\nМожна знайти в кейсах:")
                    for case in cases:
                        skin_info.append(f"• {case['case_name']}")
                result.append("\n".join(skin_info))

        final_message = "\n\n".join(result)
        if len(final_message) > 4096:
            chunks = [final_message[i:i + 4096] for i in range(0, len(final_message), 4096)]
            for i, chunk in enumerate(chunks):
                if i == 0:
                    await message.answer(
                        chunk,
                        reply_markup=build_main_keyboard()
                    )
                else:
                    await message.answer(chunk)
        else:
            await message.answer(
                final_message,
                reply_markup=build_main_keyboard()
            )
        await state.clear()
    except Exception as e:
        logging.error(f"Error in process_skin_search: {e}")
        await message.answer("⚠️ Виникла помилка під час пошуку.", reply_markup=build_main_keyboard())
        await state.clear()

#@main_router.callback_query()
#async def debug_callback(callback: CallbackQuery):
#    logging.info(f"Received unhandled callback data: {callback.data}")
#    await callback.message.edit_text(
#        f"⚠️ Ця дія не підтримується: {callback.data}",
#        reply_markup=build_main_keyboard()
#    )
#    await callback.answer()


# Admin panel handlers
@admin_router.callback_query(F.data == "admin_cases")
async def admin_cases(callback: CallbackQuery, state: FSMContext):
    logging.info(f"Processing admin_cases for user_id={callback.from_user.id}")
    logging.info(f"Callback data: {callback.data}")
    current_state = await state.get_state()
    logging.info(f"Current FSM state: {current_state}")
    await state.clear()
    if is_admin(callback.from_user.id):
        current_text = callback.message.text or ""
        new_text = "📦 Управління кейсами\n\nВиберіть дію:"
        logging.info(f"Current text: '{current_text}' | New text: '{new_text}'")
        try:
            if current_text != new_text:
                await callback.message.edit_text(
                    new_text,
                    reply_markup=build_admin_cases_keyboard()
                )
                logging.info("Cases menu displayed")
            else:
                logging.info("Text unchanged, skipping edit")
        except Exception as e:
            logging.error(f"Error editing message in admin_cases: {e}")
    else:
        await callback.message.edit_text(
            "У вас немає дозволу на доступ до цього розділу.",
            reply_markup=build_main_keyboard()
        )
        logging.info("User is not admin")
    await callback.answer()


@admin_router.callback_query(F.data == "admin_weapons")
async def admin_weapons(callback: CallbackQuery, state: FSMContext):
    logging.info(f"Processing admin_weapons for user_id={callback.from_user.id}")
    current_state = await state.get_state()
    logging.info(f"Current FSM state: {current_state}")
    if is_admin(callback.from_user.id):
        current_text = callback.message.text or ""
        new_text = "🔫 Управління зброєю\n\nВиберіть дію:"
        logging.info(f"Current text: '{current_text}' | New text: '{new_text}'")
        try:
            if current_text != new_text:
                await callback.message.edit_text(
                    new_text,
                    reply_markup=build_admin_weapons_keyboard()
                )
                logging.info("Weapons menu displayed")
            else:
                logging.info("Text unchanged, skipping edit")
        except Exception as e:
            logging.error(f"Error editing message in admin_weapons: {e}")
            await callback.message.edit_text(
                "⚠️ Виникла помилка під час відображення меню зброї.",
                reply_markup=build_admin_keyboard()
            )
        finally:
            await state.clear()  # Очищаємо стан лише після успішного виконання
    else:
        await callback.message.edit_text(
            "У вас немає дозволу на доступ до цього розділу.",
            reply_markup=build_main_keyboard()
        )
        logging.info("User is not admin")
    await callback.answer()


@admin_router.callback_query(F.data == "admin_skins")
async def admin_skins(callback: CallbackQuery, state: FSMContext):
    logging.info(f"Processing admin_skins for user_id={callback.from_user.id}")
    current_state = await state.get_state()
    logging.info(f"Current FSM state: {current_state}")
    if is_admin(callback.from_user.id):
        current_text = callback.message.text or ""
        new_text = "🎨 Управління скінами\n\nВиберіть дію:"
        logging.info(f"Current text: '{current_text}' | New text: '{new_text}'")
        try:
            if current_text != new_text:
                await callback.message.edit_text(
                    new_text,
                    reply_markup=build_admin_skins_keyboard()
                )
                logging.info("Skins menu displayed")
            else:
                logging.info("Text unchanged, skipping edit")
        except Exception as e:
            logging.error(f"Error editing message in admin_skins: {e}")
            await callback.message.edit_text(
                "⚠️ Виникла помилка під час відображення меню скінів.",
                reply_markup=build_admin_keyboard()
            )
        finally:
            await state.clear()  # Очищаємо стан лише після успішного виконання
    else:
        await callback.message.edit_text(
            "У вас немає дозволу на доступ до цього розділу.",
            reply_markup=build_main_keyboard()
        )
        logging.info("User is not admin")
    await callback.answer()

# Case management handlers
@admin_router.callback_query(F.data == "add_case")
async def add_case(callback: CallbackQuery, state: FSMContext):
    if is_admin(callback.from_user.id):
        await state.set_state(AdminStates.add_case)
        await callback.message.edit_text(
            "📦 Додавання нового кейсу\n\n"
            "Введіть назву кейсу:",
            reply_markup=InlineKeyboardBuilder().button(
                text="⬅️ Скасувати", callback_data="admin_menu"
            ).as_markup()
        )
    else:
        await callback.message.edit_text(
             "У вас немає дозволу на доступ до цього розділу.",
            reply_markup=build_main_keyboard()
        )
    await callback.answer()


@admin_router.message(AdminStates.add_case)
async def process_case_name(message: Message, state: FSMContext):
    case_name = message.text.strip()

    if not case_name:
        await message.answer(
            "⚠️ Назва кейсу не може бути пустою. Спробуйте ще раз або скасуйте:"
        )
        return

    # Add case to database
    case_id = await add_case_to_db(case_name)

    # Clear state
    await state.clear()

    # Send confirmation message
    await message.answer(
        f"✅ Кейс '{case_name}' успішно додано!",
        reply_markup=build_admin_cases_keyboard()
    )


@admin_router.callback_query(F.data == "edit_case")
async def edit_case(callback: CallbackQuery, state: FSMContext):
    if is_admin(callback.from_user.id):
        cases = await get_all_cases()
        if cases:
            await state.set_state(AdminStates.edit_case_select)
            await callback.message.edit_text(
                "✏️ Редагувати кейс\n\n"
                "Виберіть кейс для редагування:",
                reply_markup=build_select_case_keyboard(cases, "edit_case")
            )
        else:
            await callback.message.edit_text(
                "У базі даних випадків не знайдено.",
                reply_markup=build_admin_cases_keyboard()
            )
    else:
        await callback.message.edit_text(
            "У вас немає дозволу на доступ до цього розділу.",
            reply_markup=build_main_keyboard()
        )
    await callback.answer()


@admin_router.callback_query(F.data.regexp(r'^edit_case_(\d+)$'))
async def select_case_field(callback: CallbackQuery, state: FSMContext):
    logging.info(f"Processing select_case_field with callback.data: {callback.data}")
    try:
        match = re.match(r'^edit_case_(\d+)$', callback.data)
        if not match:
            raise ValueError("Invalid callback data format")
        case_id = int(match.group(1))
        case = await get_case(case_id)

        if case:
            await state.update_data(case_id=case_id)

            kb = InlineKeyboardBuilder()
            kb.button(text="Назва", callback_data=f"edit_case_name_{case_id}")
            kb.button(text="Картинка", callback_data=f"edit_case_image_{case_id}")
            kb.button(text="⬅️ Скасувати", callback_data="admin_menu")
            kb.adjust(2, 1)

            await callback.message.edit_text(
                f"✏️ Редагувати кейс: {case['case_name']}\n\n"
                f"Виберіть поле для редагування:",
                reply_markup=kb.as_markup()
            )
        else:
            await callback.message.edit_text(
                "Кейс не знайдено",
                reply_markup=build_admin_cases_keyboard()
            )
    except Exception as e:
        logging.error(f"Error in select_case_field: {e}")
        await callback.message.edit_text(
            "⚠️ Виникла помилка під час редагування кейсу.",
            reply_markup=build_admin_cases_keyboard()
        )
    await callback.answer()


@admin_router.callback_query(F.data.startswith("edit_case_name_"))
async def edit_case_name(callback: CallbackQuery, state: FSMContext):
    case_id = int(callback.data.split("_")[3])
    case = await get_case(case_id)

    if case:
        await state.set_state(AdminStates.edit_case_name)
        await state.update_data(case_id=case_id)
        await callback.message.edit_text(
            f"✏️ Редагування назви для кейсу: {case['case_name']}\n\n"
            f"Введіть нове ім'я:",
            reply_markup=InlineKeyboardBuilder().button(
                text="⬅️ Скасувати", callback_data="admin_menu"
            ).as_markup()
        )
    else:
        await callback.message.edit_text(
            "Кейс не знайдено",
            reply_markup=build_admin_cases_keyboard()
        )
    await callback.answer()


@admin_router.message(AdminStates.edit_case_name)
async def process_case_name_edit(message: Message, state: FSMContext):
    data = await state.get_data()
    case_id = data.get("case_id")
    new_name = message.text.strip()

    if not new_name:
        await message.answer(
            "⚠️ Назва кейсу не може бути пустою. Повторіть спробу або скасуйте:"
        )
        return

    # Update case in database
    await update_case(case_id, "case_name", new_name)

    # Clear state
    await state.clear()

    # Send confirmation message
    await message.answer(
        f"✅ Назву кейсу оновлено на '{new_name}'!",
        reply_markup=build_admin_cases_keyboard()
    )


@admin_router.callback_query(F.data.startswith("edit_case_image_"))
async def edit_case_image(callback: CallbackQuery, state: FSMContext):
    case_id = int(callback.data.split("_")[3])
    case = await get_case(case_id)

    if case:
        await state.set_state(AdminStates.edit_case_image)
        await state.update_data(case_id=case_id)
        await callback.message.edit_text(
            f"✏️ Редагування URL-адреси зображення для кейсу: {case['case_name']}\n\n"
            f"Поточна URL-адреса зображення: {case['image_case'] or 'Нема'}\n\n"
            f"Введіть нову URL-адресу зображення:",
            reply_markup=InlineKeyboardBuilder().button(
                text="⬅️ Скасувати", callback_data="admin_menu"
            ).as_markup()
        )
    else:
        await callback.message.edit_text(
            "Case not found.",
            reply_markup=build_admin_cases_keyboard()
        )
    await callback.answer()


@admin_router.message(AdminStates.edit_case_image)
async def process_case_image_edit(message: Message, state: FSMContext):
    data = await state.get_data()
    case_id = data.get("case_id")
    new_image = message.text.strip()

    # Update case in database
    await update_case(case_id, "image_case", new_image)

    # Clear state
    await state.clear()

    # Send confirmation message
    await message.answer(
        f"✅ URL-адресу зображення справи оновлено!",
        reply_markup=build_admin_cases_keyboard()
    )


@admin_router.callback_query(F.data == "delete_case")
async def delete_case_select(callback: CallbackQuery, state: FSMContext):
    if is_admin(callback.from_user.id):
        cases = await get_all_cases()
        if cases:
            await state.set_state(AdminStates.delete_case_confirm)
            await callback.message.edit_text(
                "🗑️ Видалити кейс\n\n"
                "Виберіть кейс для видалення:",
                reply_markup=build_select_case_keyboard(cases, "delete_case")
            )
        else:
            await callback.message.edit_text(
                "У базі даних кейсів не знайдено.",
                reply_markup=build_admin_cases_keyboard()
            )
    else:
        await callback.message.edit_text(
            "У вас немає дозволу на доступ до цього розділу.",
            reply_markup=build_main_keyboard()
        )
    await callback.answer()


@admin_router.callback_query(F.data.startswith("delete_case_"))
async def confirm_delete_case(callback: CallbackQuery, state: FSMContext):
    case_id = int(callback.data.split("_")[2])
    case = await get_case(case_id)

    if case:
        await callback.message.edit_text(
            f"🗑️ Ви впевнені, що хочете видалити кейс: {case['case_name']}?\n\n"
            f"Це також видалить усі асоціації зі скінами.",
            reply_markup=build_confirm_keyboard("delete_case", case_id)
        )
    else:
        await callback.message.edit_text(
            "Кейс не знайдено",
            reply_markup=build_admin_cases_keyboard()
        )
    await callback.answer()


@admin_router.callback_query(F.data.startswith("confirm_delete_case_"))
async def process_delete_case(callback: CallbackQuery, state: FSMContext):
    case_id = int(callback.data.split("_")[3])
    case = await get_case(case_id)

    if case:
        case_name = case['case_name']

        # Delete case from database
        await delete_case(case_id)

        # Clear state
        await state.clear()

        await callback.message.edit_text(
            f"✅ Кейс '{case_name}' успішно видалено!",
            reply_markup=build_admin_cases_keyboard()
        )
    else:
        await callback.message.edit_text(
            "Кейс не знайдено",
            reply_markup=build_admin_cases_keyboard()
        )
    await callback.answer()


# Weapon management handlers
@admin_router.callback_query(F.data == "add_weapon")
async def add_weapon(callback: CallbackQuery, state: FSMContext):
    if is_admin(callback.from_user.id):
        await state.set_state(AdminStates.add_weapon)
        await callback.message.edit_text(
            "🔫 Додавання нової зброї\n\n"
            "Будь ласка, введіть назву зброї:",
            reply_markup=InlineKeyboardBuilder().button(
                text="⬅️ Скасувати", callback_data="admin_menu"
            ).as_markup()
        )
    else:
        await callback.message.edit_text(
            "У вас немає дозволу на доступ до цього розділу.",
            reply_markup=build_main_keyboard()
        )
    await callback.answer()

def build_cancel_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Скасувати", callback_data="admin_menu")
    kb.adjust(1)
    return kb.as_markup()


@admin_router.message(AdminStates.add_weapon)
async def process_weapon_name(message: Message, state: FSMContext):
    logging.info(f"Processing weapon name input for user_id={message.from_user.id}")
    if is_admin(message.from_user.id):
        weapon_name = message.text.strip()
        if not weapon_name:
            logging.warning("Empty weapon name received")
            await message.answer(
                "⚠️ Назва зброї не може бути порожньою. Введіть назву ще раз:",
                reply_markup=build_cancel_keyboard()
            )
            return

        # Зберігаємо назву зброї в FSM
        await state.update_data(weapon_name=weapon_name)
        logging.info(f"Stored weapon name: {weapon_name}")

        try:
            # Зберігаємо зброю в базу даних (якщо це фінальний крок)
            async with pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO weapons (weapon_name) VALUES ($1)",
                    weapon_name
                )
            logging.info(f"Weapon '{weapon_name}' added to database")

            await message.answer(
                f"✅ Зброю '{weapon_name}' успішно додано!",
                reply_markup=build_admin_weapons_keyboard()
            )
            await state.clear()  # Очищаємо стан після завершення
        except Exception as e:
            logging.error(f"Error adding weapon to database: {e}")
            await message.answer(
                "⚠️ Виникла помилка під час додавання зброї. Спробуйте ще раз.",
                reply_markup=build_admin_weapons_keyboard()
            )
            await state.clear()
    else:
        logging.warning(f"User_id={message.from_user.id} is not admin")
        await message.answer(
            "У вас немає дозволу на виконання цієї дії.",
            reply_markup=build_main_keyboard()
        )
        await state.clear()


@admin_router.callback_query(F.data == "edit_weapon")
async def edit_weapon(callback: CallbackQuery, state: FSMContext):
    if is_admin(callback.from_user.id):
        weapons = await get_all_weapons()
        if weapons:
            await state.set_state(AdminStates.edit_weapon_select)
            await callback.message.edit_text(
                "✏️ Редагувати зброю\n\n"
                "Виберіть зброю для редагування:",
                reply_markup=build_select_weapon_keyboard(weapons, "edit_weapon")
            )
        else:
            await callback.message.edit_text(
                "У базі даних зброї не знайдено.",
                reply_markup=build_admin_weapons_keyboard()
            )
    else:
        await callback.message.edit_text(
            "У вас немає дозволу на доступ до цього розділу.",
            reply_markup=build_main_keyboard()
        )
    await callback.answer()


@admin_router.callback_query(F.data.startswith("edit_weapon_"))
async def edit_weapon_name(callback: CallbackQuery, state: FSMContext):
    weapon_id = int(callback.data.split("_")[2])
    weapon = await get_weapon(weapon_id)

    if weapon:
        await state.set_state(AdminStates.edit_weapon_name)
        await state.update_data(weapon_id=weapon_id)
        await callback.message.edit_text(
            f"✏️ Редагування зброї: {weapon['weapon_name']}\n\n"
            f"Будь ласка, введіть нову назву:",
            reply_markup=InlineKeyboardBuilder().button(
                text="⬅️ Скасувати", callback_data="admin_menu"
            ).as_markup()
        )
    else:
        await callback.message.edit_text(
            "Weapon not found.",
            reply_markup=build_admin_weapons_keyboard()
        )
    await callback.answer()

@main_router.message()
async def handle_all_messages(message: Message, state: FSMContext):
    current_state = await state.get_state()
    logging.info(f"Unhandled message: {message.text}, current_state: {current_state}")
    if current_state is None:  # Обробляємо лише, якщо немає активного стану
        await message.answer("Ця команда не підтримується.")
    else:
        logging.info("Message ignored due to active FSM state")


@admin_router.message(AdminStates.edit_weapon_name)
async def process_weapon_name_edit(message: Message, state: FSMContext):
    data = await state.get_data()
    weapon_id = data.get("weapon_id")
    new_name = message.text.strip()

    if not new_name:
        await message.answer(
            "⚠️ Назва зброї не може бути пустою. Повторіть спробу або скасуйте:"
        )
        return

    # Update weapon in database
    await update_weapon(weapon_id, new_name)

    # Clear state
    await state.clear()

    # Send confirmation message
    await message.answer(
        f"✅ Назву зброї оновлено на '{new_name}'!",
        reply_markup=build_admin_weapons_keyboard()
    )


@admin_router.callback_query(F.data == "delete_weapon")
async def delete_weapon_select(callback: CallbackQuery, state: FSMContext):
    if is_admin(callback.from_user.id):
        weapons = await get_all_weapons()
        if weapons:
            await state.set_state(AdminStates.delete_weapon_confirm)
            await callback.message.edit_text(
                "🗑️ Видалити зброю\n\n"
                "Виберіть зброю для видалення:",
                reply_markup=build_select_weapon_keyboard(weapons, "delete_weapon")
            )
        else:
            await callback.message.edit_text(
                "У базі даних зброї не знайдено.",
                reply_markup=build_admin_weapons_keyboard()
            )
    else:
        await callback.message.edit_text(
            "У вас немає дозволу на доступ до цього розділу.",
            reply_markup=build_main_keyboard()
        )
    await callback.answer()


@admin_router.callback_query(F.data.startswith("delete_weapon_"))
async def confirm_delete_weapon(callback: CallbackQuery, state: FSMContext):
    weapon_id = int(callback.data.split("_")[2])
    weapon = await get_weapon(weapon_id)

    if weapon:
        await callback.message.edit_text(
            f"🗑️ Ви впевнені, що хочете видалити зброю: {weapon['weapon_name']}?\n\n"
            f"Це також видалить усі скіни для цієї зброї.",
            reply_markup=build_confirm_keyboard("delete_weapon", weapon_id)
        )
    else:
        await callback.message.edit_text(
            "Зброю не знайдено.",
            reply_markup=build_admin_weapons_keyboard()
        )
    await callback.answer()


@admin_router.callback_query(F.data.startswith("confirm_delete_weapon_"))
async def process_delete_weapon(callback: CallbackQuery, state: FSMContext):
    weapon_id = int(callback.data.split("_")[3])
    weapon = await get_weapon(weapon_id)

    if weapon:
        weapon_name = weapon['weapon_name']

        # Delete weapon from database
        await delete_weapon(weapon_id)

        # Clear state
        await state.clear()

        await callback.message.edit_text(
            f"✅ Зброя '{weapon_name}' успішно видалена!",
            reply_markup=build_admin_weapons_keyboard()
        )
    else:
        await callback.message.edit_text(
            "Зброю не знайдено.",
            reply_markup=build_admin_weapons_keyboard()
        )
    await callback.answer()


# Skin management handlers
@admin_router.callback_query(F.data == "add_skin")
async def add_skin(callback: CallbackQuery, state: FSMContext):
    if is_admin(callback.from_user.id):
        weapons = await get_all_weapons()

        if weapons:
            await state.set_state(AdminStates.add_skin_weapon)

            await callback.message.edit_text(
                "🎨 Додавання нового скіна\n\n"
                "Спочатку виберіть зброю для цього скіна:",
                reply_markup=build_select_weapon_keyboard(weapons, "add_skin_weapon")
            )
        else:
            await callback.message.edit_text(
                "У базі даних зброї не знайдено. Спочатку додайте зброю.",
                reply_markup=build_admin_skins_keyboard()
            )
    else:
        await callback.message.edit_text(
            "У вас немає дозволу на доступ до цього розділу.",
            reply_markup=build_main_keyboard()
        )
    await callback.answer()


@admin_router.callback_query(F.data.startswith("add_skin_weapon_"))
async def add_skin_name(callback: CallbackQuery, state: FSMContext):
    weapon_id = int(callback.data.split("_")[3])
    weapon = await get_weapon(weapon_id)

    if weapon:
        await state.set_state(AdminStates.add_skin_name)
        await state.update_data(weapon_id=weapon_id, weapon_name=weapon['weapon_name'])

        await callback.message.edit_text(
            f"🎨 Додавання нового скіна для {weapon['weapon_name']}\n\n"
            f"Введіть назву скіна:",
            reply_markup=InlineKeyboardBuilder().button(
                text="⬅️ Скасувати", callback_data="admin_menu"
            ).as_markup()
        )
    else:
        await callback.message.edit_text(
            "Зброю не знайдено.",
            reply_markup=build_admin_skins_keyboard()
        )
    await callback.answer()


@admin_router.message(AdminStates.add_skin_name)
async def process_skin_name(message: Message, state: FSMContext):
    data = await state.get_data()
    skin_name = message.text.strip()

    if not skin_name:
        await message.answer(
            "⚠️ Назва скіна не може бути пустим. Повторіть спробу або скасуйте:"
        )
        return

    await state.update_data(skin_name=skin_name)
    await state.set_state(AdminStates.add_skin_rarity)

    # Create rarity keyboard
    kb = InlineKeyboardBuilder()
    rarities = ["Common", "Uncommon", "Mythical", "Ancient", "Covert", "Classified", "Restricted",
                "Mil-Spec Grade", "Industrial Grade", "Consumer Grade"]

    for rarity in rarities:
        kb.button(text=rarity, callback_data=f"skin_rarity_{rarity}")

    kb.button(text="Пропустити", callback_data="skin_rarity_skip")
    kb.button(text="⬅️ Скасувати", callback_data="admin_menu")
    kb.adjust(2)

    await message.answer(
        f"🎨 Додавання скіна: {data['weapon_name']} | {skin_name}\n\n"
        f"Будь ласка, виберіть рідкість скіна:",
        reply_markup=kb.as_markup()
    )


@admin_router.callback_query(F.data.startswith("skin_rarity_"))
async def process_skin_rarity(callback: CallbackQuery, state: FSMContext):
    rarity = callback.data.replace("skin_rarity_", "")

    if rarity == "skip":
        rarity = None

    await state.update_data(rarity=rarity)
    await state.set_state(AdminStates.add_skin_stattrak)

    kb = InlineKeyboardBuilder()
    kb.button(text="Так", callback_data="skin_stattrak_true")
    kb.button(text="Ні", callback_data="skin_stattrak_false")
    kb.button(text="⬅️ Скасувати", callback_data="admin_menu")
    kb.adjust(2, 1)

    data = await state.get_data()
    await callback.message.edit_text(
        f"🎨 Додавання скіна: {data['weapon_name']} | {data['skin_name']}\n"
        f" Рідкість: {rarity or 'Not specified'}\n\n"
        f"Чи доступний цей скін із StatTrak™?",
        reply_markup=kb.as_markup()
    )
    await callback.answer()


@admin_router.callback_query(F.data.startswith("skin_stattrak_"))
async def process_skin_stattrak(callback: CallbackQuery, state: FSMContext):
    stattrak = callback.data.replace("skin_stattrak_", "") == "true"

    await state.update_data(stattrak=stattrak)
    await state.set_state(AdminStates.add_skin_souvenir)

    kb = InlineKeyboardBuilder()
    kb.button(text="Так", callback_data="skin_souvenir_true")
    kb.button(text="Ні", callback_data="skin_souvenir_false")
    kb.button(text="⬅️ Скасувати", callback_data="admin_menu")
    kb.adjust(2, 1)

    data = await state.get_data()
    await callback.message.edit_text(
        f"🎨 Додавання скіна: {data['weapon_name']} | {data['skin_name']}\n"
        f"Рідкість: {data.get('rarity') or 'Not specified'}\n"
        f"StatTrak™: {'Yes' if stattrak else 'No'}\n\n"
        f"Чи доступний цей скін як сувенір?",
        reply_markup=kb.as_markup()
    )
    await callback.answer()


@admin_router.callback_query(F.data.startswith("skin_souvenir_"))
async def process_skin_souvenir(callback: CallbackQuery, state: FSMContext):
    souvenir = callback.data.replace("skin_souvenir_", "") == "true"

    await state.update_data(souvenir=souvenir)
    await state.set_state(AdminStates.add_skin_image)

    data = await state.get_data()
    await callback.message.edit_text(
        f"🎨 Додавання скіна: {data['weapon_name']} | {data['skin_name']}\n"
        f"Рідкість: {data.get('rarity') or 'Not specified'}\n"
        f"StatTrak™: {'Yes' if data.get('stattrak') else 'No'}\n"
        f"Souvenir: {'Yes' if souvenir else 'No'}\n\n"
        f"Введіть URL-адресу зображення скіна (або введіть «skip», щоб пропустити):",
        reply_markup=InlineKeyboardBuilder().button(
            text="⬅️ Скасувати", callback_data="admin_menu"
        ).as_markup()
    )
    await callback.answer()


@admin_router.message(AdminStates.add_skin_image)
async def process_skin_image(message: Message, state: FSMContext):
    image_url = message.text.strip()

    if image_url.lower() == "skip":
        image_url = None

    data = await state.get_data()
    weapon_id = data.get("weapon_id")
    skin_name = data.get("skin_name")
    rarity = data.get("rarity")
    stattrak = data.get("stattrak", False)
    souvenir = data.get("souvenir", False)

    # Add skin to database
    skin_id = await add_skin_to_db(
        skin_name, weapon_id, rarity, stattrak, souvenir, image_url
    )

    # Clear state
    await state.clear()

    # Ask if user wants to add wear types
    kb = InlineKeyboardBuilder()
    kb.button(text="Yes", callback_data=f"add_wear_{skin_id}")
    kb.button(text="No", callback_data="admin_skins")
    kb.adjust(2)

    await message.answer(
        f"✅ Скін '{data['weapon_name']} | {skin_name}' було успішно додано!\n\n"
        f"Do you want to add wear types for this skin?",
        reply_markup=kb.as_markup()
    )


@admin_router.callback_query(F.data == "add_skinwear")
async def add_skinwear_select_skin(callback: CallbackQuery, state: FSMContext):
    if is_admin(callback.from_user.id):
        skins = await get_all_skins()

        if skins:
            await state.set_state(AdminStates.add_skinwear_skin)
            await callback.message.edit_text(
                "➕ Додайте тип зносу\n\n"
                "Виберіть скін, щоб додати тип зносу:",
                reply_markup=build_select_skin_keyboard(skins, "add_wear")
            )
        else:
            await callback.message.edit_text(
                "У базі даних не знайдено скінів. Спочатку додайте скін.",
                reply_markup=build_admin_skins_keyboard()
            )
    else:
        await callback.message.edit_text(
            "У вас немає дозволу на доступ до цього розділу.",
            reply_markup=build_main_keyboard()
        )
    await callback.answer()


@admin_router.callback_query(F.data.startswith("add_wear_"))
async def add_skinwear_select_type(callback: CallbackQuery, state: FSMContext):
    skin_id = int(callback.data.split("_")[2])
    skin = await get_skin(skin_id)

    if skin:
        await state.set_state(AdminStates.add_skinwear_weartype)
        await state.update_data(skin_id=skin_id, skin_name=skin['skin_name'], weapon_name=skin['weapon_name'])

        await callback.message.edit_text(
            f"➕ Додавання типу зносу для: {skin['weapon_name']} | {skin['skin_name']}\n\n"
            f"Виберіть тип зносу:",
            reply_markup=build_wear_types_keyboard(skin_id)
        )
    else:
        await callback.message.edit_text(
            "Скін не знайдено",
            reply_markup=build_admin_skins_keyboard()
        )
    await callback.answer()


@admin_router.callback_query(F.data.startswith("wear_type_"))
async def add_skinwear_floatmin(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    skin_id = int(parts[2])
    wear_type = "_".join(parts[3:])

    await state.update_data(wear_type=wear_type)
    await state.set_state(AdminStates.add_skinwear_floatmin)

    data = await state.get_data()
    await callback.message.edit_text(
        f"➕ Додавання {wear_type} зносу для: {data['weapon_name']} | {data['skin_name']}\n\n"
        f"Введіть мінімальне значення з значеннями після коми (наприклад, 0,0):",
        reply_markup=InlineKeyboardBuilder().button(
            text="⬅️ Скасувати", callback_data="admin_menu"
        ).as_markup()
    )
    await callback.answer()


@admin_router.message(AdminStates.add_skinwear_floatmin)
async def process_skinwear_floatmin(message: Message, state: FSMContext):
    try:
        float_min = float(message.text.strip())

        if not (0 <= float_min <= 1):
            await message.answer(
                "⚠️ Значення Float має бути від 0 до 1. Повторіть спробу:"
            )
            return

        await state.update_data(float_min=float_min)
        await state.set_state(AdminStates.add_skinwear_floatmax)

        data = await state.get_data()
        await message.answer(
            f"➕ Додавання {data['wear_type']} зносу для: {data['weapon_name']} | {data['skin_name']}\n"
            f"Мінімальний float: {float_min}\n\n"
            f"Введіть максимальне значення з значеннями після коми (e.g., 0.07):",
            reply_markup=InlineKeyboardBuilder().button(
                text="⬅️ Скасувати", callback_data="admin_menu"
            ).as_markup()
        )
    except ValueError:
        await message.answer(
            "⚠️ Введіть дійсний номер. Спробуйте знову:"
        )


@admin_router.message(AdminStates.add_skinwear_floatmax)
async def process_skinwear_floatmax(message: Message, state: FSMContext):
    try:
        float_max = float(message.text.strip())

        if not (0 <= float_max <= 1):
            await message.answer(
                "⚠️ Значення Float має бути від 0 до 1. Повторіть спробу:"
            )
            return

        data = await state.get_data()
        float_min = data.get("float_min")

        if float_max <= float_min:
            await message.answer(
                "⚠️ Максимальний float має бути більшим за мінімальний float. Спробуйте ще раз:"
            )
            return

        skin_id = data.get("skin_id")
        wear_type = data.get("wear_type")

        # Add skinwear to database
        await add_skinwear_to_db(skin_id, wear_type, float_min, float_max)

        # Clear state
        await state.clear()

        # Send confirmation message
        await message.answer(
            f"✅ {wear_type} до скіна додано знос!\n"
            f"Мінімальний float: {float_min}, Максимальний float: {float_max}",
            reply_markup=build_admin_skins_keyboard()
        )
    except ValueError:
        await message.answer(
            "⚠️ Введіть дійсний номер. Спробуйте знову:"
        )


@admin_router.callback_query(F.data == "edit_skin")
async def edit_skin_select(callback: CallbackQuery, state: FSMContext):
    if is_admin(callback.from_user.id):
        skins = await get_all_skins()

        if skins:
            await state.set_state(AdminStates.edit_skin_select)
            await callback.message.edit_text(
                "✏️ Редагувати скін\n\n"
                "Виберіть скін для редагування:",
                reply_markup=build_select_skin_keyboard(skins, "edit_skin")
            )
        else:
            await callback.message.edit_text(
                "У базі даних не знайдено скінів.",
                reply_markup=build_admin_skins_keyboard()
            )
    else:
        await callback.message.edit_text(
            "У вас немає дозволу на доступ до цього розділу.",
            reply_markup=build_main_keyboard()
        )
    await callback.answer()


@admin_router.callback_query(F.data.startswith("edit_skin_"))
async def edit_skin_select_field(callback: CallbackQuery, state: FSMContext):
    if not callback.data.startswith("edit_skin_field_"):  # To avoid conflict with the next handler
        skin_id = int(callback.data.split("_")[2])
        skin = await get_skin(skin_id)

        if skin:
            await state.update_data(skin_id=skin_id)
            await callback.message.edit_text(
                f"✏️ Редагування скіна: {skin['weapon_name']} | {skin['skin_name']}\n\n"
                f"Виберіть поле для редагування:",
                reply_markup=build_edit_skin_fields_keyboard(skin_id)
            )
        else:
            await callback.message.edit_text(
                "Скін не знайдено",
                reply_markup=build_admin_skins_keyboard()
            )
    await callback.answer()


@admin_router.callback_query(F.data.startswith("edit_skin_field_"))
async def edit_skin_field(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    skin_id = int(parts[3])
    field = "_".join(parts[4:])

    skin = await get_skin(skin_id)

    if skin:
        await state.set_state(AdminStates.edit_skin_value)
        await state.update_data(skin_id=skin_id, field=field)

        field_name = field.replace("_", " ").title()
        current_value = str(skin[field])

        if field in ('stattrak', 'souvenir'):
            options_kb = InlineKeyboardBuilder()
            options_kb.button(text="Так", callback_data=f"set_skin_value_true")
            options_kb.button(text="Ні", callback_data=f"set_skin_value_false")
            options_kb.button(text="⬅️ Скасувати", callback_data="admin_menu")
            options_kb.adjust(2, 1)

            await callback.message.edit_text(
                f"✏️ Редагування {field_name} для: {skin['weapon_name']} | {skin['skin_name']}\n\n"
                f"Поточне значення: {current_value}\n\n"
                f"Виберіть нове значення:",
                reply_markup=options_kb.as_markup()
            )
        else:
            await callback.message.edit_text(
                f"✏️ Редагування {field_name} для: {skin['weapon_name']} | {skin['skin_name']}\n\n"
                f"Поточне значення: {current_value}\n\n"
                f"Виберіть нове значення:",
                reply_markup=InlineKeyboardBuilder().button(
                    text="⬅️ Скасувати", callback_data="admin_menu"
                ).as_markup()
            )
    else:
        await callback.message.edit_text(
            "Скін не знайдено.",
            reply_markup=build_admin_skins_keyboard()
        )
    await callback.answer()


@admin_router.callback_query(F.data.startswith("set_skin_value_"))
async def process_skin_value_selection(callback: CallbackQuery, state: FSMContext):
    value = callback.data.split("_")[3]

    data = await state.get_data()
    skin_id = data.get("skin_id")
    field = data.get("field")

    # Update skin in database
    await update_skin(skin_id, field, value)

    # Clear state
    await state.clear()

    # Send confirmation message
    await callback.message.edit_text(
        f"✅ Скін {field.replace('_', ' ')} було оновлено до '{value}'!",
        reply_markup=build_admin_skins_keyboard()
    )
    await callback.answer()


@admin_router.message(AdminStates.edit_skin_value)
async def process_skin_value_edit(message: Message, state: FSMContext):
    data = await state.get_data()
    skin_id = data.get("skin_id")
    field = data.get("field")
    new_value = message.text.strip()

    if not new_value and field != "image_skin":
        await message.answer(
            f"⚠️ Значення не може бути порожнім. Повторіть спробу або скасуйте:"
        )
        return

    # Update skin in database
    await update_skin(skin_id, field, new_value)

    # Clear state
    await state.clear()

    # Send confirmation message
    await message.answer(
        f"✅ Скін {field.replace('_', ' ')} було оновлено!",
        reply_markup=build_admin_skins_keyboard()
    )


@admin_router.callback_query(F.data == "delete_skin")
async def delete_skin_select(callback: CallbackQuery, state: FSMContext):
    if is_admin(callback.from_user.id):
        skins = await get_all_skins()

        if skins:
            await state.set_state(AdminStates.delete_skin_confirm)
            await callback.message.edit_text(
                "🗑️ Видалити скін\n\n"
                "Виберіть скін для видалення:",
                reply_markup=build_select_skin_keyboard(skins, "delete_skin")
            )
        else:
            await callback.message.edit_text(
                "У базі даних не знайдено скінів.",
                reply_markup=build_admin_skins_keyboard()
            )
    else:
        await callback.message.edit_text(
            "У вас немає дозволу на доступ до цього розділу.",
            reply_markup=build_main_keyboard()
        )
    await callback.answer()


@admin_router.callback_query(F.data.startswith("delete_skin_"))
async def confirm_delete_skin(callback: CallbackQuery, state: FSMContext):
    skin_id = int(callback.data.split("_")[2])
    skin = await get_skin(skin_id)

    if skin:
        await callback.message.edit_text(
            f"🗑️ Ви впевнені, що хочете видалити скін: {skin['weapon_name']} | {skin['skin_name']}?\n\n"
            f"Це також усуне всі асоціації з кейсами та типами зносу.",
            reply_markup=build_confirm_keyboard("delete_skin", skin_id)
        )
    else:
        await callback.message.edit_text(
            "Скін не знайдено.",
            reply_markup=build_admin_skins_keyboard()
        )
    await callback.answer()


@admin_router.callback_query(F.data.startswith("confirm_delete_skin_"))
async def process_delete_skin(callback: CallbackQuery, state: FSMContext):
    skin_id = int(callback.data.split("_")[3])
    skin = await get_skin(skin_id)

    if skin:
        skin_name = f"{skin['weapon_name']} | {skin['skin_name']}"

        # Delete skin from database
        await delete_skin(skin_id)

        # Clear state
        await state.clear()

        await callback.message.edit_text(
            f"✅ Скін '{skin_name}' було успішно видалено!",
            reply_markup=build_admin_skins_keyboard()
        )
    else:
        await callback.message.edit_text(
            "Скін не знайдено.",
            reply_markup=build_admin_skins_keyboard()
        )
    await callback.answer()


# Case-Skin relations handlers
@admin_router.callback_query(F.data == "admin_caseskins")
async def admin_caseskins(callback: CallbackQuery):
    if is_admin(callback.from_user.id):
        await callback.message.edit_text(
            "🔄 Управління зв'язками Case-Skin\n\n"
            "Виберіть дію:",
            reply_markup=build_admin_caseskins_keyboard()
        )
    else:
        await callback.message.edit_text(
            "У вас немає дозволу на доступ до цього розділу.",
            reply_markup=build_main_keyboard()
        )
    await callback.answer()


@admin_router.callback_query(F.data == "add_caseskin")
async def add_caseskin_select_case(callback: CallbackQuery, state: FSMContext):
    if is_admin(callback.from_user.id):
        cases = await get_all_cases()

        if cases:
            await state.set_state(AdminStates.add_caseskin_case)
            await callback.message.edit_text(
                "➕ Додати скін до кейсу\n\n"
                "Спочатку виберіть випадок:",
                reply_markup=build_select_case_keyboard(cases, "add_caseskin_case")
            )
        else:
            await callback.message.edit_text(
                "У базі даних випадків не знайдено. Спочатку додайте справу.",
                reply_markup=build_admin_caseskins_keyboard()
            )
    else:
        await callback.message.edit_text(
            "У вас немає дозволу на доступ до цього розділу.",
            reply_markup=build_main_keyboard()
        )
    await callback.answer()


@admin_router.callback_query(F.data.startswith("add_caseskin_case_"))
async def add_caseskin_select_skin(callback: CallbackQuery, state: FSMContext):
    case_id = int(callback.data.split("_")[3])
    case = await get_case(case_id)

    if case:
        # Get all skins that are not already in this case
        async with pool.acquire() as conn:
            skins = await conn.fetch("""
                    SELECT s.*, w.weapon_name FROM skins s
                    JOIN weapons w ON s.weapon_id = w.weapon_id
                    WHERE s.skin_id NOT IN (
                        SELECT skin_id FROM caseskins WHERE case_id = $1
                    )
                    ORDER BY w.weapon_name, s.skin_name
                """, case_id)

        if skins:
            await state.set_state(AdminStates.add_caseskin_skin)
            await state.update_data(case_id=case_id, case_name=case['case_name'])

            await callback.message.edit_text(
                f"➕ Додавання скіну до кейсу: {case['case_name']}\n\n"
                f"Тепер виберіть скін для додавання:",
                reply_markup=build_select_skin_keyboard(skins, "add_caseskin_skin")
            )
        else:
            await callback.message.edit_text(
                "Немає більше скінів, які можна додати до цього кейсу.",
                reply_markup=build_admin_caseskins_keyboard()
            )
    else:
        await callback.message.edit_text(
            "Кейс не знайдено.",
            reply_markup=build_admin_caseskins_keyboard()
        )
    await callback.answer()


@admin_router.callback_query(F.data.startswith("add_caseskin_skin_"))
async def process_add_caseskin(callback: CallbackQuery, state: FSMContext):
    skin_id = int(callback.data.split("_")[3])
    skin = await get_skin(skin_id)

    data = await state.get_data()
    case_id = data.get("case_id")
    case_name = data.get("case_name")

    if skin and case_id:
        # Add skin to case
        success = await add_skin_to_case(case_id, skin_id)

        if success:
            await callback.message.edit_text(
                f"✅ Скін '{skin['weapon_name']} | {skin['skin_name']}' "
                f"додано до кейса '{case_name}'!",
                reply_markup=build_admin_caseskins_keyboard()
            )
        else:
            await callback.message.edit_text(
                "⚠️ Помилка додавання скіна до кейса. Відношення може вже існувати.",
                reply_markup=build_admin_caseskins_keyboard()
            )
    else:
        await callback.message.edit_text(
            "Скін або кейс не знайдено.",
            reply_markup=build_admin_caseskins_keyboard()
        )

    # Clear state
    await state.clear()
    await callback.answer()


@admin_router.callback_query(F.data == "remove_caseskin")
async def remove_caseskin_select_case(callback: CallbackQuery, state: FSMContext):
    if is_admin(callback.from_user.id):
        cases = await get_all_cases()

        if cases:
            await state.set_state(AdminStates.remove_caseskin)
            await callback.message.edit_text(
                "➖ Видалити скін з кейсу\n\n"
                "Спочатку виберіть кейс:",
                reply_markup=build_select_case_keyboard(cases, "remove_caseskin_case")
            )
        else:
            await callback.message.edit_text(
                "У базі даних кейс не знайдено.",
                reply_markup=build_admin_caseskins_keyboard()
            )
    else:
        await callback.message.edit_text(
            "У вас немає дозволу на доступ до цього розділу.",
            reply_markup=build_main_keyboard()
        )
    await callback.answer()


@admin_router.callback_query(F.data.startswith("remove_caseskin_case_"))
async def remove_caseskin_select_skin(callback: CallbackQuery, state: FSMContext):
    case_id = int(callback.data.split("_")[3])
    case = await get_case(case_id)

    if case:
        # Get all skins currently in this case
        skins = await get_case_skins(case_id)

        if skins:
            await state.set_state(AdminStates.remove_caseskin_confirm)
            await state.update_data(case_id=case_id, case_name=case['case_name'])

            await callback.message.edit_text(
                f"➖ Видалення скіна з кейса: {case['case_name']}\n\n"
                f"Виберіть скін для видалення:",
                reply_markup=build_select_skin_keyboard(skins, "remove_caseskin_skin")
            )
        else:
            await callback.message.edit_text(
                "Не має скіна у кейсі для видалення",
                reply_markup=build_admin_caseskins_keyboard()
            )
    else:
        await callback.message.edit_text(
            "Кейс не знайдено.",
            reply_markup=build_admin_caseskins_keyboard()
        )
    await callback.answer()


@admin_router.callback_query(F.data.startswith("remove_caseskin_skin_"))
async def confirm_remove_caseskin(callback: CallbackQuery, state: FSMContext):
    skin_id = int(callback.data.split("_")[3])
    skin = await get_skin(skin_id)

    data = await state.get_data()
    case_id = data.get("case_id")
    case_name = data.get("case_name")

    if skin and case_id:
        await state.update_data(skin_id=skin_id, skin_name=f"{skin['weapon_name']} | {skin['skin_name']}")

        await callback.message.edit_text(
            f"➖ Ви впевнені, що хочете видалити скін? '{skin['weapon_name']} | {skin['skin_name']}' "
            f"з кейса '{case_name}'?",
            reply_markup=build_confirm_keyboard("remove_caseskin", f"{case_id}_{skin_id}")
        )
    else:
        await callback.message.edit_text(
            "Скін або кейс не знайдено.",
            reply_markup=build_admin_caseskins_keyboard()
        )
    await callback.answer()


@admin_router.callback_query(F.data.startswith("confirm_remove_caseskin_"))
async def process_remove_caseskin(callback: CallbackQuery, state: FSMContext):
    ids = callback.data.split("_")[3]
    case_id, skin_id = map(int, ids.split("_"))

    data = await state.get_data()
    case_name = data.get("case_name")
    skin_name = data.get("skin_name")

    # Remove skin from case
    await remove_skin_from_case(case_id, skin_id)

    # Clear state
    await state.clear()

    await callback.message.edit_text(
        f"✅ Скін '{skin_name}' видалено з кейса '{case_name}'!",
        reply_markup=build_admin_caseskins_keyboard()
    )
    await callback.answer()


# Common handlers
@main_router.callback_query(F.data == "cancel_action")
async def cancel_action(callback: CallbackQuery, state: FSMContext):
    current_state = await state.get_state()

    if current_state is not None:
        await state.clear()

    # Determine which menu to return to based on the current state
    if current_state and current_state.startswith('AdminStates.'):
        if current_state.startswith('AdminStates.add_case') or \
                current_state.startswith('AdminStates.edit_case') or \
                current_state.startswith('AdminStates.delete_case'):
            await callback.message.edit_text(
                "🎮 Керування кейсами\n\n"
                "Операцію скасовано. Виберіть дію:",
                reply_markup=build_admin_cases_keyboard()
            )
        elif current_state.startswith('AdminStates.add_weapon') or \
                current_state.startswith('AdminStates.edit_weapon') or \
                current_state.startswith('AdminStates.delete_weapon'):
            await callback.message.edit_text(
                "🔫 Керування зброєю\n\n"
                "Операцію скасовано. Виберіть дію:",
                reply_markup=build_admin_weapons_keyboard()
            )
        elif current_state.startswith('AdminStates.add_skin') or \
                current_state.startswith('AdminStates.edit_skin') or \
                current_state.startswith('AdminStates.delete_skin') or \
                current_state.startswith('AdminStates.add_skinwear'):
            await callback.message.edit_text(
                "🎨 Керування скінами\n\n"
                "Операцію скасовано. Виберіть дію:",
                reply_markup=build_admin_skins_keyboard()
            )
        elif current_state.startswith('AdminStates.add_caseskin') or \
                current_state.startswith('AdminStates.remove_caseskin'):
            await callback.message.edit_text(
                "🔄 Управління зв'язками Case-Skin\n\n"
                "Операцію скасовано. Виберіть дію:",
                reply_markup=build_admin_caseskins_keyboard()
            )
        else:
            # Default to admin menu
            await callback.message.edit_text(
                "Панель адміністратора\n\n"
                "Операцію скасовано. Виберіть дію:",
                reply_markup=build_admin_keyboard()
            )
    else:
        # Default to main menu
        await callback.message.edit_text(
            "Бот для керування елементами CS2\n\n"
            "Операцію скасовано. Виберіть дію:",
            reply_markup=build_main_keyboard()
        )

    await callback.answer()


# Main entry point
async def main():
    try:
        await init_db()
        dp.include_router(admin_router)
        dp.include_router(main_router)
        logging.info("Routers included: admin_router, main_router")

        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    except asyncio.CancelledError:
        logging.info("Polling was cancelled.")
    finally:
        await bot.session.close()
        logging.info("Bot session closed.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Bot stopped by user (KeyboardInterrupt).")

