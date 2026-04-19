"""
Умный парсер команд NEXUS Bot
Понимает: игры, экономику, тэги, РП команды, умные теги
Обрабатывает ТОЛЬКО текст, НЕ начинающийся с /
ПОЛНОСТЬЮ ИСПРАВЛЕН — ВСЕ БАЛАНСЫ ЧЕРЕЗ db.get_balance()
"""

import re
import random
import logging
import asyncio
from aiogram import Router, types, F
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import db
from config import SLOT_COST, ROULETTE_MIN, DUEL_MIN, START_BALANCE

logger = logging.getLogger(__name__)
router = Router()

# Хранилище запросов дуэлей
duel_requests = {}

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
    user = await db.get_user(user_id)
    if not user:
        await db.create_user(user_id, username, first_name, START_BALANCE)
        user = await db.get_user(user_id)
    return user


def extract_number(text: str) -> int:
    match = re.search(r'\b\d+\b', text)
    return int(match.group()) if match else 0


def extract_color(text: str) -> str:
    text = text.lower()
    if 'красн' in text or 'red' in text:
        return 'red'
    if 'черн' in text or 'black' in text:
        return 'black'
    return None


def extract_choice_rps(text: str) -> str:
    text = text.lower()
    if 'камень' in text or 'rock' in text:
        return 'rock'
    if 'ножницы' in text or 'scissors' in text:
        return 'scissors'
    if 'бумага' in text or 'paper' in text:
        return 'paper'
    return None


def extract_username(text: str) -> str:
    match = re.search(r'@([a-zA-Z0-9_]+)', text)
    return match.group(1) if match else None


# ==================== ОБРАБОТЧИК ТОЛЬКО ДЛЯ ТЕКСТА БЕЗ / ====================

@router.message(F.text, lambda message: not message.text.startswith('/'))
async def smart_parser(message: types.Message):
    """Умный парсер — обрабатывает ТОЛЬКО текст, не начинающийся с /"""
    
    if message.from_user.is_bot:
        return
    
    user_id = message.from_user.id
    text = message.text.strip().lower() if message.text else ""
    
    if not text:
        return
    
    if user_id in profile_states:
        return
    
    # 🔥 СВЕЖИЙ БАЛАНС
    user = await get_or_create_user(user_id, message.from_user.username, message.from_user.first_name)
    balance = await db.get_balance(user_id)
    
    # ==================== УМНЫЕ ТЕГИ ====================
    bot_called = any(word in text for word in ['нексус', 'нэксус', 'nexus', 'некс', 'нэкс', 'бот'])
    
    if bot_called:
        for slug, keywords in TAG_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text:
                    try:
                        from handlers.tag_categories import get_chat_enabled_slugs
                        chat_id = message.chat.id
                        enabled_slugs = await get_chat_enabled_slugs(chat_id)
                        
                        if slug in enabled_slugs:
                            msg_parts = text.split(keyword, 1)
                            msg_text = msg_parts[1].strip() if len(msg_parts) > 1 else "Внимание!"
                            
                            from handlers.tag_trigger import trigger_tag
                            await trigger_tag(message, slug, msg_text)
                            return
                    except ImportError:
                        pass
                    except Exception as e:
                        logger.error(f"Tag trigger error: {e}")
    
    # ==================== СЛОТ ====================
    if 'слот' in text or 'slot' in text:
        bet = extract_number(message.text)
        
        if bet == 0:
            await message.answer(
                "🎰 *СЛОТ-МАШИНА*\n\n"
                "Напишите: *слот 100*\n"
                f"Минимальная ставка: {SLOT_COST} NCoins",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        if bet < SLOT_COST:
            await message.answer(f"❌ Минимальная ставка: {SLOT_COST} NCoins")
            return
        
        # 🔥 СВЕЖИЙ БАЛАНС
        balance = await db.get_balance(user_id)
        if balance < bet:
            await message.answer(f"❌ Недостаточно средств! Баланс: {balance} NCoins")
            return
        
        symbols = ["🍒", "🍋", "🍊", "🍉", "⭐", "💎"]
        result = [random.choice(symbols) for _ in range(3)]
        
        if result[0] == result[1] == result[2]:
            if result[0] == "💎":
                win = bet * 10
                msg = "✨ ДЖЕКПОТ! x10! ✨"
            elif result[0] == "⭐":
                win = bet * 5
                msg = "✨ СУПЕР ВЫИГРЫШ! x5! ✨"
            else:
                win = bet * 3
                msg = "🎉 ВЫИГРЫШ! x3! 🎉"
            
            await db.update_balance(user_id, win, "Выигрыш в слоте")
            response = f"🎰 {result[0]} | {result[1]} | {result[2]} 🎰\n\n{msg}\n💰 +{win} NCoins!"
            
        elif result[0] == result[1] or result[1] == result[2] or result[0] == result[2]:
            win = bet // 2
            await db.update_balance(user_id, win, "Выигрыш в слоте")
            response = f"🎰 {result[0]} | {result[1]} | {result[2]} 🎰\n\n🎉 Выигрыш! +{win} NCoins!"
        else:
            await db.update_balance(user_id, -bet, "Проигрыш в слоте")
            response = f"🎰 {result[0]} | {result[1]} | {result[2]} 🎰\n\n😔 Проигрыш! -{bet} NCoins"
        
        await message.answer(response, parse_mode=ParseMode.MARKDOWN)
        return
    
    # ==================== РУЛЕТКА ====================
    if 'рулетк' in text or 'roulette' in text:
        bet = extract_number(message.text)
        color = extract_color(message.text)
        
        if bet == 0 or not color:
            await message.answer(
                "🎡 *РУЛЕТКА*\n\n"
                "Напишите: *рулетка 100 красный*\n"
                f"Минимальная ставка: {ROULETTE_MIN} NCoins",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        if bet < ROULETTE_MIN:
            await message.answer(f"❌ Минимальная ставка: {ROULETTE_MIN} NCoins")
            return
        
        # 🔥 СВЕЖИЙ БАЛАНС
        balance = await db.get_balance(user_id)
        if balance < bet:
            await message.answer(f"❌ Недостаточно средств! Баланс: {balance} NCoins")
            return
        
        result_color = random.choice(["red", "black"])
        color_names = {"red": "🔴 КРАСНОЕ", "black": "⚫ ЧЁРНОЕ"}
        
        if color == result_color:
            win = bet * 2
            await db.update_balance(user_id, win, "Выигрыш в рулетке")
            response = f"🎡 *Рулетка*\n\nВыпало: {color_names[result_color]}\n\n🎉 ВЫ ВЫИГРАЛИ! +{win} NCoins!"
        else:
            await db.update_balance(user_id, -bet, "Проигрыш в рулетке")
            response = f"🎡 *Рулетка*\n\nВыпало: {color_names[result_color]}\n\n😔 Вы проиграли {bet} NCoins"
        
        await message.answer(response, parse_mode=ParseMode.MARKDOWN)
        return
    
    # ==================== КНБ ====================
    rps_choice = extract_choice_rps(text)
    if rps_choice:
        bet = 50
        
        # 🔥 СВЕЖИЙ БАЛАНС
        balance = await db.get_balance(user_id)
        if balance < bet:
            await message.answer(f"❌ Недостаточно средств! Нужно {bet} NCoins")
            return
        
        choice_names = {"rock": "🗿 КАМЕНЬ", "scissors": "✂️ НОЖНИЦЫ", "paper": "📄 БУМАГА"}
        bot_choice = random.choice(["rock", "scissors", "paper"])
        
        if rps_choice == bot_choice:
            result = 0
            msg = "🤝 НИЧЬЯ!"
        elif (rps_choice == "rock" and bot_choice == "scissors") or \
             (rps_choice == "scissors" and bot_choice == "paper") or \
             (rps_choice == "paper" and bot_choice == "rock"):
            result = bet
            msg = f"✅ ПОБЕДА! +{bet} NCoins!"
        else:
            result = -bet
            msg = f"❌ ПОРАЖЕНИЕ! -{bet} NCoins"
        
        await db.update_balance(user_id, result, "Игра КНБ")
        
        await message.answer(
            f"✂️ *КАМЕНЬ-НОЖНИЦЫ-БУМАГА*\n\n"
            f"Вы: {choice_names[rps_choice]}\n"
            f"Бот: {choice_names[bot_choice]}\n\n"
            f"{msg}",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # ==================== ДУЭЛЬ ====================
    if ('дуэль' in text or 'duel' in text) and '@' in text:
        username = extract_username(message.text)
        bet = extract_number(message.text)
        
        if not username or bet == 0:
            await message.answer(
                "⚔️ *ДУЭЛЬ*\n\n"
                "Напишите: *дуэль @user 100*\n"
                f"Минимальная ставка: {DUEL_MIN} NCoins",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        if bet < DUEL_MIN:
            await message.answer(f"❌ Минимальная ставка: {DUEL_MIN} NCoins")
            return
        
        # 🔥 СВЕЖИЙ БАЛАНС
        balance = await db.get_balance(user_id)
        if balance < bet:
            await message.answer(f"❌ Недостаточно средств! Баланс: {balance} NCoins")
            return
        
        target_user = await db.get_user_by_username(username)
        
        if not target_user:
            await message.answer(f"❌ Пользователь @{username} не найден")
            return
        
        target_id = target_user["user_id"]
        target_name = target_user.get("first_name", username)
        
        if target_id == user_id:
            await message.answer("❌ Нельзя вызвать на дуэль самого себя!")
            return
        
        # 🔥 СВЕЖИЙ БАЛАНС ПРОТИВНИКА
        target_balance = await db.get_balance(target_id)
        if target_balance < bet:
            await message.answer(f"❌ У @{username} недостаточно средств для дуэли!")
            return
        
        duel_requests[target_id] = {
            "from_id": user_id,
            "from_name": message.from_user.first_name,
            "bet": bet,
            "chat_id": message.chat.id
        }
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ ПРИНЯТЬ", callback_data=f"accept_duel_{target_id}"),
             InlineKeyboardButton(text="❌ ОТКЛОНИТЬ", callback_data=f"reject_duel_{target_id}")]
        ])
        
        await message.answer(
            f"⚔️ *ДУЭЛЬ!*\n\n"
            f"@{username}, вас вызвал на дуэль {message.from_user.first_name}\n"
            f"💰 Ставка: {bet} NCoins",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )
        return
    
    # ==================== ТЭГ ВСЕХ ====================
    if bot_called and ('оповести всех' in text or 'общий сбор' in text or 'собери всех' in text):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ НАЧАТЬ", callback_data="start_all"),
             InlineKeyboardButton(text="❌ ОТМЕНА", callback_data="cancel_all")]
        ])
        
        await message.answer(
            "📢 *ОБЩИЙ СБОР*\n\n"
            "Будет отправлено несколько сообщений с упоминаниями.\n\n"
            "Начать?",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )
        return
    
    # ==================== РП КОМАНДЫ ====================
    rp_responses = {
        'привет': 'Привет! 👋',
        'пока': 'Пока! 👋',
        'спасибо': 'Пожалуйста! 🤗',
        'молодец': 'Спасибо! 😊',
        'красава': 'Благодарю! 🤝',
    }
    
    for key, response in rp_responses.items():
        if key in text:
            await message.answer(response)
            return


# ==================== ОБРАБОТЧИКИ КНОПОК ====================

@router.callback_query(lambda c: c.data and c.data.startswith("accept_duel_"))
async def accept_duel(callback: types.CallbackQuery):
    target_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    
    if user_id != target_id:
        await callback.answer("❌ Это не вам!", show_alert=True)
        return
    
    if target_id not in duel_requests:
        await callback.answer("❌ Вызов устарел!", show_alert=True)
        return
    
    request = duel_requests[target_id]
    from_id = request["from_id"]
    from_name = request["from_name"]
    bet = request["bet"]
    
    # 🔥 СВЕЖИЕ БАЛАНСЫ
    user_balance = await db.get_balance(user_id)
    from_balance = await db.get_balance(from_id)
    
    if user_balance < bet:
        await callback.answer(f"❌ У вас недостаточно средств! Нужно {bet}", show_alert=True)
        return
    
    if from_balance < bet:
        await callback.answer(f"❌ У {from_name} недостаточно средств!", show_alert=True)
        return
    
    await db.update_balance(user_id, -bet, f"Дуэль с {from_name}")
    await db.update_balance(from_id, -bet, f"Дуэль с {callback.from_user.first_name}")
    
    winner_id = random.choice([user_id, from_id])
    
    if winner_id == user_id:
        win_amount = bet * 2
        await db.update_balance(user_id, win_amount, f"Выигрыш в дуэли")
        result_text = f"🎉 ПОБЕДИЛ {callback.from_user.first_name}! +{win_amount} NCoins!"
    else:
        win_amount = bet * 2
        await db.update_balance(from_id, win_amount, f"Выигрыш в дуэли")
        result_text = f"🎉 ПОБЕДИЛ {from_name}! +{win_amount} NCoins!"
    
    del duel_requests[target_id]
    
    await callback.message.edit_text(f"⚔️ *РЕЗУЛЬТАТ ДУЭЛИ*\n\n{result_text}", parse_mode=ParseMode.MARKDOWN)
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("reject_duel_"))
async def reject_duel(callback: types.CallbackQuery):
    target_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    
    if user_id != target_id:
        await callback.answer("❌ Это не вам!", show_alert=True)
        return
    
    if target_id in duel_requests:
        request = duel_requests[target_id]
        del duel_requests[target_id]
        await callback.message.edit_text(f"❌ {callback.from_user.first_name} отклонил вызов!")
        
        try:
            await callback.bot.send_message(request["from_id"], f"❌ {callback.from_user.first_name} отклонил вызов!")
        except:
            pass
    
    await callback.answer()


@router.callback_query(lambda c: c.data == "start_all")
async def start_all_callback(callback: types.CallbackQuery):
    from handlers.tag import cmd_all
    await cmd_all(callback.message)
    await callback.answer()


@router.callback_query(lambda c: c.data == "cancel_all")
async def cancel_all(callback: types.CallbackQuery):
    await callback.message.edit_text("❌ Отменено")
    await callback.answer()
