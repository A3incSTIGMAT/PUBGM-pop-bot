"""
Умный парсер команд NEXUS Bot
Обрабатывает ТОЛЬКО текст, НЕ начинающийся с /
Умные теги, общий сбор, РП команды, крестики-нолики
"""

import re
import logging
from aiogram import Router, types, F
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import db
from config import START_BALANCE

logger = logging.getLogger(__name__)
router = Router()

# Хранилище состояний анкеты (из profile.py)
profile_states = {}

# Словарь соответствия фраз -> slug категорий для умных тегов
TAG_KEYWORDS = {
    'pubg': ['пубг', 'pubg', 'пабг', 'королевская битва', 'сквад', 'ранкед', 'игроков в пубг'],
    'cs2': ['кс2', 'cs2', 'counter-strike', 'катка', 'матчмейкинг', 'игроков в кс'],
    'dota': ['дота', 'dota', 'дота 2', 'пати', 'катка', 'игроков в доту'],
    'mafia': ['мафия', 'mafia', 'партия', 'сбор', 'игроков в мафию'],
    'video_call': ['звонок', 'созвон', 'видеозвонок', 'скайп', 'discord', 'позвонить'],
    'important': ['важный вопрос', 'помогите', 'нужна помощь', 'вопрос', 'совет', 'подскажите'],
    'giveaway': ['розыгрыш', 'giveaway', 'конкурс', 'ивент', 'приз'],
    'offtopic': ['флуд', 'оффтоп', 'offtopic', 'болталка', 'поболтать'],
    'tech': ['техническое', 'баг', 'ошибка', 'bug', 'сломалась', 'не работает'],
    'urgent': ['срочно', 'urgent', 'помощь админам', 'внимание админы', 'срочная помощь'],
}


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

async def get_or_create_user(user_id: int, username: str = None, first_name: str = None) -> dict:
    """Получить пользователя или создать если не существует"""
    user = await db.get_user(user_id)
    if not user:
        await db.create_user(user_id, username, first_name, START_BALANCE)
        user = await db.get_user(user_id)
        logger.info(f"Auto-registered user {user_id} in smart_commands")
    return user


def extract_username(text: str) -> str:
    """Извлечь username из текста"""
    match = re.search(r'@([a-zA-Z0-9_]+)', text)
    return match.group(1) if match else None


# ==================== ОБРАБОТЧИК ТОЛЬКО ДЛЯ ТЕКСТА БЕЗ / ====================

@router.message(F.text, lambda message: not message.text.startswith('/'))
async def smart_parser(message: types.Message):
    """Умный парсер — обрабатывает ТОЛЬКО текст, не начинающийся с /"""
    
    # Игнорируем сообщения от ботов
    if message.from_user.is_bot:
        return
    
    user_id = message.from_user.id
    text = message.text.strip().lower() if message.text else ""
    
    if not text:
        return
    
    # Проверка: если пользователь заполняет анкету — НЕ обрабатываем другие команды
    if user_id in profile_states:
        return
    
    # Проверяем регистрацию
    user = await get_or_create_user(user_id, message.from_user.username, message.from_user.first_name)
    if not user:
        await message.answer("👋 Используйте /start для регистрации")
        return
    
    # ==================== ПРОВЕРКА ОБРАЩЕНИЯ К БОТУ ====================
    bot_called = any(word in text for word in ['нексус', 'нэксус', 'nexus', 'некс', 'нэкс', 'бот'])
    
    # ==================== УМНЫЕ ТЕГИ (КАТЕГОРИИ) ====================
    if bot_called:
        for slug, keywords in TAG_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text:
                    # Проверяем, включена ли категория в чате
                    try:
                        from handlers.tag_categories import get_chat_enabled_slugs
                        chat_id = message.chat.id
                        enabled_slugs = await get_chat_enabled_slugs(chat_id)
                        
                        if slug in enabled_slugs:
                            # Извлекаем текст сообщения
                            msg_parts = text.split(keyword, 1)
                            msg_text = msg_parts[1].strip() if len(msg_parts) > 1 else "Внимание!"
                            
                            # Вызываем тег
                            from handlers.tag_trigger import trigger_tag
                            await trigger_tag(message, slug, msg_text)
                            return
                    except ImportError:
                        pass
                    except Exception as e:
                        logger.error(f"Tag trigger error: {e}")
    
    # ==================== ТЭГ ВСЕХ (ОБЩИЙ СБОР) ====================
    if bot_called and ('оповести всех' in text or 'общий сбор' in text or 'собери всех' in text):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ НАЧАТЬ", callback_data="start_all"),
             InlineKeyboardButton(text="❌ ОТМЕНА", callback_data="cancel_all")]
        ])
        
        await message.answer(
            "📢 <b>ОБЩИЙ СБОР</b>\n\n"
            "Будет отправлено сообщение с упоминанием всех участников.\n\n"
            "Начать?",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )
        return
    
    # ==================== КРЕСТИКИ-НОЛИКИ ====================
    if bot_called and ('крестики' in text or 'нолики' in text or 'крестики-нолики' in text or 'xo' in text):
        from handlers.tictactoe import cmd_xo
        await cmd_xo(message)
        return
    
    # ==================== ВЫЗОВ ИГРОКА В КРЕСТИКИ-НОЛИКИ ====================
    if bot_called and ('вызвать' in text or 'дуэль' in text or 'игра' in text) and '@' in text:
        if 'крестики' in text or 'нолики' in text or 'xo' in text:
            username = extract_username(message.text)
            if username:
                from handlers.tictactoe import active_games
                import time
                import hashlib
                
                # Создаём вызов
                target_user = await db.get_user_by_username(username)
                if not target_user:
                    await message.answer(f"❌ Пользователь @{username} не найден!")
                    return
                
                target_id = target_user["user_id"]
                if target_id == user_id:
                    await message.answer("❌ Нельзя вызвать самого себя!")
                    return
                
                game_id = f"xo_{hashlib.md5(str(time.time()).encode()).hexdigest()[:8]}"
                
                from handlers.tictactoe import active_games as xo_games
                xo_games[game_id] = {
                    "type": "pvp",
                    "board": [[" ", " ", " "], [" ", " ", " "], [" ", " ", " "]],
                    "player_x": user_id,
                    "player_o": target_id,
                    "current_turn": "X",
                    "bet": 0,
                    "chat_id": message.chat.id,
                    "created_at": time.time(),
                    "last_move": time.time(),
                    "pending": True,
                }
                
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="✅ ПРИНЯТЬ", callback_data=f"xo_accept_{game_id}"),
                     InlineKeyboardButton(text="❌ ОТКЛОНИТЬ", callback_data=f"xo_reject_{game_id}")]
                ])
                
                await message.answer(
                    f"⚔️ <b>ВЫЗОВ НА КРЕСТИКИ-НОЛИКИ!</b>\n\n"
                    f"👤 {message.from_user.first_name} вызывает @{username}!\n"
                    f"💰 Ставка: <b>без ставки</b>\n\n"
                    f"@{username}, примите вызов!",
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard
                )
                return
    
    # ==================== ПОМОЩЬ ====================
    if bot_called and ('помоги' in text or 'помощь' in text or 'help' in text or 'что ты умеешь' in text):
        help_text = (
            "🤖 <b>ЧТО Я УМЕЮ:</b>\n\n"
            "<b>🗣️ Умные команды:</b>\n"
            "• <code>Нексус, оповести всех</code> — общий сбор\n"
            "• <code>Нексус, найди сквад в PUBG</code> — тег по категории\n"
            "• <code>Нексус, крестики-нолики</code> — играть в XO\n"
            "• <code>Нексус, вызови @user в крестики</code> — дуэль\n\n"
            "<b>🎮 Игры:</b>\n"
            "• Крестики-нолики против бота и игроков\n\n"
            "<b>📌 Основные команды:</b>\n"
            "• /start — главное меню\n"
            "• /daily — ежедневный бонус\n"
            "• /balance — проверить баланс\n"
            "• /help — полная помощь"
        )
        await message.answer(help_text, parse_mode=ParseMode.HTML)
        return
    
    # ==================== РП КОМАНДЫ ====================
    rp_responses = {
        'привет': 'Привет! 👋',
        'пока': 'Пока! 👋',
        'спасибо': 'Пожалуйста! 🤗',
        'молодец': 'Спасибо! 😊',
        'красава': 'Благодарю! 🤝',
        'доброе утро': 'Доброе утро! ☀️',
        'добрый вечер': 'Добрый вечер! 🌙',
        'спокойной ночи': 'Сладких снов! 😴',
    }
    
    for key, response in rp_responses.items():
        if key in text:
            await message.answer(response)
            return


# ==================== ОБРАБОТЧИКИ КНОПОК ====================

@router.callback_query(lambda c: c.data == "start_all")
async def start_all_callback(callback: types.CallbackQuery):
    """Запуск общего сбора"""
    from handlers.tag import cmd_all
    await cmd_all(callback.message)
    await callback.answer()


@router.callback_query(lambda c: c.data == "cancel_all")
async def cancel_all_callback(callback: types.CallbackQuery):
    """Отмена общего сбора"""
    await callback.message.edit_text("❌ Общий сбор отменён.")
    await callback.answer()
