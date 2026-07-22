import asyncio
import logging
import re
import random
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.filters import Command, ChatMemberUpdatedFilter, KICKED, MEMBER, ADMINISTRATOR, CREATOR, LEFT
from aiogram.types import (
    Message, ChatMemberUpdated, InlineKeyboardMarkup, InlineKeyboardButton,
    FSInputFile, CallbackQuery
)
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
import os

# ============ CONFIG ============
BOT_TOKEN = os.environ.get("BOT_TOKEN", "7783618044:AAENUiQ1vfmY442RzdvgM7QB71j1NQH4yYg")
GROUP_ID = int(os.environ.get("GROUP_ID", "-1001787318055"))
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@societycivil")
FLOODIKA_THREAD = int(os.environ.get("FLOODIKA_THREAD", "438392"))
LINKS_THREAD = int(os.environ.get("LINKS_THREAD", "460367"))
CHECK_DELAY = int(os.environ.get("CHECK_DELAY", "300"))  # 5 minutes
SILENCE_TIMEOUT = int(os.environ.get("SILENCE_TIMEOUT", "3600"))  # 1 hour

# ============ LOGGING ============
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ============ STATE ============
pending_kicks = {}  # user_id -> datetime when check scheduled
last_message_time = datetime.now()

# ============ LAYOUT CORRECTION ============
LAT_TO_RUS = {
    'q':'й','w':'ц','e':'у','r':'к','t':'е','y':'н','u':'г','i':'ш','o':'щ','p':'з',
    '[':'х',']':'ъ','a':'ф','s':'ы','d':'в','f':'а','g':'п','h':'р','j':'о','k':'л',
    'l':'д',';':'ж',"'":'э','z':'я','x':'ч','c':'с','v':'м','b':'и','n':'т','m':'ь',
    ',':'б','.':'.','/':'ё',
    'Q':'Й','W':'Ц','E':'У','R':'К','T':'Е','Y':'Н','U':'Г','I':'Ш','O':'Щ','P':'З',
    '{':'Х','}':'Ъ','A':'Ф','S':'Ы','D':'В','F':'А','G':'П','H':'Р','J':'О','K':'Л',
    'L':'Д',':':'Ж','"':'Э','Z':'Я','X':'Ч','C':'С','V':'М','B':'И','N':'Т','M':'Ь',
    '<':'Б','>':'.','?':'Ё'
}

RUS_TO_LAT = {v: k for k, v in LAT_TO_RUS.items()}

def is_gibberish_latin(text):
    """Check if text is likely typed with wrong layout (Latin chars but Russian words)"""
    if not text or len(text) < 3:
        return False
    # Must have mostly Latin chars
    latin_count = sum(1 for c in text if c in LAT_TO_RUS)
    total_alpha = sum(1 for c in text if c.isalpha())
    if total_alpha == 0 or latin_count / total_alpha < 0.7:
        return False
    # Convert and check if result looks like Russian
    converted = convert_layout(text)
    # Check if converted has common Russian letter patterns
    rus_vowels = set('аеёиоуыэюяАЕЁИОУЫЭЮЯ')
    vowel_count = sum(1 for c in converted if c in rus_vowels)
    if vowel_count < 1:
        return False
    return True

def convert_layout(text):
    """Convert text from wrong layout"""
    result = []
    for c in text:
        if c in LAT_TO_RUS:
            result.append(LAT_TO_RUS[c])
        else:
            result.append(c)
    return ''.join(result)

def is_gibberish_russian(text):
    """Check if Russian text was typed with Latin layout in mind"""
    if not text or len(text) < 3:
        return False
    russian_count = sum(1 for c in text if c in RUS_TO_LAT)
    total_alpha = sum(1 for c in text if c.isalpha())
    if total_alpha == 0 or russian_count / total_alpha < 0.7:
        return False
    converted = convert_layout_rus_to_lat(text)
    # Check if converted looks like English
    eng_vowels = set('aeiouyAEIOUY')
    vowel_count = sum(1 for c in converted if c in eng_vowels)
    if vowel_count < 1:
        return False
    return True

def convert_layout_rus_to_lat(text):
    result = []
    for c in text:
        if c in RUS_TO_LAT:
            result.append(RUS_TO_LAT[c])
        else:
            result.append(c)
    return ''.join(result)

# ============ JOKES & NEWS ============
JOKES = [
    "— Какой самый короткий анекдот?\n— Бабушка пришла.\n— И?",
    "— Вы знаете, что если положить телефон в холодильник, зарядка держится дольше?\n— Это правда?\n— Нет, но вы попробуйте.",
    "Объявление: «Потерялась совесть. Нашедшему — не возвращать».",
    "— Что будет, если скрестить ежа и змею?\n— Полтора метра колючей проволоки.",
    "В России две беды — дураки и дороги. Но дураки зато какие асфальтоукладчики!",
    "— Почему вы сидите на работе в шортах?\n— У нас дресс-код: «одежда должна быть».",
    "Жена мужу:\n— Я ухожу к маме!\n— Я с тобой! Моя лучше готовит.",
    "— Как вы относитесь к повышению пенсий?\n— Как к рассвету: красиво, но до него ещё дожить надо.",
    "Смотрю новости: «В России выросли доходы». Пришлось выключить — комедия не мой жанр.",
    "— Что такое российская экономика?\n— Это когда все работают, никто не получает, но все довольны.",
    "В чат пришёл новый участник. Ему сказали: «Читайте правила». Он прочитал и вышел.",
    "— Какой главный закон российской бюрократии?\n— Если можно ничего не делать — делай это медленно.",
]

NEWS_FACTS = [
    "🌍 Факт дня: Конституция СССР 1936 года гарантировала право на труд, отдых, образование и бесплатную медицину — всё то, о чём сегодня приходится напоминать.",
    "📜 Знаете ли вы? Статья 125 Конституции СССР 1936 г. гарантировала свободу слова, печати, собраний — больше, чем во многих современных «демократиях».",
    "⚖️ Гражданин СССР имел высший юридический статус — Человек. Сегодня этот статус нужно восстанавливать заново.",
    "🏛 По Конституции 1936 года Верховный Совет был высшим органом власти. Депутаты могли быть отозваны в любой момент — настоящая демократия.",
    "💡 Интересно: в СССР не было безработицы — это было уголовное преступление государства перед гражданином. А сегодня?",
    "🌍 Факт: по международному праву, оккупированное государство не прекращает существование. СССР не был упразднён законно.",
    "📜 Знаете ли вы? Президент СССР Горбачёв нарушил присягу и Конституцию — это юридический факт, а не мнение.",
]

# ============ BOT SETUP ============
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
router = Router()
dp.include_router(router)


# ============ TASK 1: Welcome + Subscription Check ============

@router.chat_member(ChatMemberUpdatedFilter(member_status_changed=True))
async def on_chat_member_update(event: ChatMemberUpdated):
    """Handle new members joining the group"""
    user = event.new_chat_member.user
    old_status = event.old_chat_member.status
    new_status = event.new_chat_member.status

    # Only handle when someone joins (was not member, now is)
    if old_status in (LEFT, KICKED) and new_status in (MEMBER, ADMINISTRATOR, CREATOR):
        # TASK 3: Ban bots
        if user.is_bot and user.id != bot.id:
            try:
                await bot.ban_chat_member(GROUP_ID, user.id)
                logger.info(f"Banned bot: {user.first_name} (id:{user.id})")
                await bot.send_message(
                    GROUP_ID,
                    f"🚫 Бот <b>{user.first_name}</b> заблокирован — добавление ботов запрещено!",
                    message_thread_id=FLOODIKA_THREAD
                )
            except Exception as e:
                logger.error(f"Failed to ban bot {user.id}: {e}")
            return

        # Check channel subscription
        try:
            member = await bot.get_chat_member(CHANNEL_ID, user.id)
            is_subscribed = member.status in (MEMBER, ADMINISTRATOR, CREATOR)
        except Exception as e:
            logger.error(f"Failed to check subscription for {user.id}: {e}")
            is_subscribed = False

        if is_subscribed:
            await bot.send_message(
                GROUP_ID,
                f"👋 Добро пожаловать, <b>{user.first_name}</b>!\n"
                f"Подписка на канал подтверждена ✅\n"
                f"Приятного общения!",
                message_thread_id=FLOODIKA_THREAD
            )
        else:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📢 Подписаться на канал", url="https://t.me/societycivil")],
                [InlineKeyboardButton(text="✅ Я подписался", callback_data=f"check_sub_{user.id}")]
            ])
            await bot.send_message(
                GROUP_ID,
                f"👋 Привет, <b>{user.first_name}</b>!\n\n"
                f"⚠️ Для участия в чате нужно подписаться на канал:\n"
                f"👉 <a href=\"https://t.me/societycivil\">Гражданское Общество</a>\n\n"
                f"⏰ У тебя есть 5 минут. Если не подпишешься — придётся удалить из чата.",
                message_thread_id=FLOODIKA_THREAD,
                reply_markup=keyboard
            )
            # Schedule kick check
            pending_kicks[user.id] = datetime.now() + timedelta(seconds=CHECK_DELAY)
            asyncio.create_task(schedule_kick_check(user.id, user.first_name))


async def schedule_kick_check(user_id: int, first_name: str):
    """Check subscription after delay and kick if not subscribed"""
    await asyncio.sleep(CHECK_DELAY)
    if user_id not in pending_kicks:
        return  # Already handled

    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        is_subscribed = member.status in (MEMBER, ADMINISTRATOR, CREATOR)
    except:
        is_subscribed = False

    if not is_subscribed:
        try:
            await bot.ban_chat_member(GROUP_ID, user_id)
            await bot.send_message(
                GROUP_ID,
                f"❌ <b>{first_name}</b> удалён из чата — не подписался на канал.",
                message_thread_id=FLOODIKA_THREAD
            )
            logger.info(f"Kicked user {user_id} - not subscribed")
        except Exception as e:
            logger.error(f"Failed to kick {user_id}: {e}")
    else:
        await bot.send_message(
            GROUP_ID,
            f"✅ <b>{first_name}</b> подписался на канал! Добро пожаловать!",
            message_thread_id=FLOODIKA_THREAD
        )

    pending_kicks.pop(user_id, None)


@router.callback_query(F.data.startswith("check_sub_"))
async def on_check_subscription(callback: CallbackQuery):
    """Handle 'I subscribed' button"""
    user_id = int(callback.data.split("_")[-1])
    if user_id != callback.from_user.id:
        await callback.answer("Это кнопка не для тебя!", show_alert=True)
        return

    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        is_subscribed = member.status in (MEMBER, ADMINISTRATOR, CREATOR)
    except:
        is_subscribed = False

    if is_subscribed:
        pending_kicks.pop(user_id, None)
        await callback.message.edit_text(
            f"✅ <b>{callback.from_user.first_name}</b> подписался на канал! Добро пожаловать!"
        )
        await callback.answer("Подписка подтверждена! 🎉", show_alert=True)
    else:
        await callback.answer("Подписка не найдена. Подпишись и нажми снова!", show_alert=True)


# ============ TASK 2: Move links/files from Флудилка to Ссылки ============

@router.message(F.chat.id == GROUP_ID, F.message_thread_id == FLOODIKA_THREAD)
async def on_floodika_message(message: Message):
    global last_message_time
    last_message_time = datetime.now()

    # Check if message has links, forwarded content, or files
    has_link = bool(message.entities and any(
        e.type in ("url", "text_link") for e in message.entities
    ))
    has_forward = bool(message.forward_date or message.forward_from or message.forward_from_chat)
    has_file = bool(message.document or message.photo or message.video or message.audio or message.voice or message.animation)
    has_caption_link = bool(message.caption_entities and any(
        e.type in ("url", "text_link") for e in message.caption_entities
    ))

    if has_link or has_forward or has_file or has_caption_link:
        # Forward to ССЫЛКИ topic
        try:
            # Copy the message to the links thread
            await message.copy_to(GROUP_ID, message_thread_id=LINKS_THREAD)
            # Delete original from Флудилка
            await message.delete()
            # Notify user
            await bot.send_message(
                GROUP_ID,
                f"↗️ Ссылка/файл от <b>{message.from_user.first_name}</b> перемещён в <b>ССЫЛКИ</b>",
                message_thread_id=FLOODIKA_THREAD
            )
            logger.info(f"Moved message {message.message_id} to links thread")
        except Exception as e:
            logger.error(f"Failed to move message: {e}")


# ============ TASK 4: Auto-correct keyboard layout ============

@router.message(F.chat.id == GROUP_ID, F.text)
async def on_text_message(message: Message):
    global last_message_time
    last_message_time = datetime.now()

    text = message.text or ""

    # Check if typed with wrong Latin layout
    if is_gibberish_latin(text):
        corrected = convert_layout(text)
        try:
            await message.reply(
                f"⌨️ <b>Исправленная раскладка:</b>\n{corrected}",
                message_thread_id=message.message_thread_id
            )
        except Exception as e:
            logger.error(f"Failed to correct layout: {e}")

    # Check if typed with wrong Russian layout (less common)
    elif is_gibberish_russian(text):
        corrected = convert_layout_rus_to_lat(text)
        try:
            await message.reply(
                f"⌨️ <b>Fixed layout:</b>\n{corrected}",
                message_thread_id=message.message_thread_id
            )
        except Exception as e:
            logger.error(f"Failed to correct layout: {e}")


# ============ TASK 5: Revive silent chat ============

async def silence_watcher():
    """Periodically check if chat is silent and send a joke/news"""
    while True:
        await asyncio.sleep(60)  # Check every minute
        silence = (datetime.now() - last_message_time).total_seconds()
        if silence >= SILENCE_TIMEOUT:
            content = random.choice(JOKES + NEWS_FACTS)
            try:
                await bot.send_message(
                    GROUP_ID,
                    f"💤 Чат уснул... Разбудим!\n\n{content}",
                    message_thread_id=FLOODIKA_THREAD
                )
                logger.info("Sent silence breaker message")
            except Exception as e:
                logger.error(f"Failed to send silence breaker: {e}")
            # Reset timer
            global last_message_time
            last_message_time = datetime.now()


# ============ COMMANDS ============

@router.message(Command("start"), F.chat.type == "private")
async def cmd_start(message: Message):
    await message.answer(
        "🤖 Бот модерации группы <b>Гражданское Общество</b>\n\n"
        "Функции:\n"
        "1. ✅ Проверка подписки на канал\n"
        "2. ↗️ Перемещение ссылок в ССЫЛКИ\n"
        "3. 🚫 Запрет добавления ботов\n"
        "4. ⌨️ Автоисправление раскладки\n"
        "5. 💬 Оживление чата при тишине"
    )


# ============ MAIN ============

async def main():
    logger.info("Starting moderation bot...")
    # Start silence watcher
    asyncio.create_task(silence_watcher())
    # Start polling (or webhook)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
