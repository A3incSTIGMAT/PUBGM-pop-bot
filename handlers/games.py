import random
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import db
from utils.keyboards import back_button, game_buttons
from utils.rate_limiter import rate_limit

router = Router()

class SlotState(StatesGroup):
    waiting_bet = State()

@router.message(Command("slot"))
@rate_limit(limit=30, key="slot")
async def cmd_slot(message: Message, state: FSMContext):
    await message.answer("🎰 *Слот*\n💰 Введите ставку (10-10000):", parse_mode="Markdown")
    await state.set_state(SlotState.waiting_bet)

@router.message(SlotState.waiting_bet)
async def slot_bet(message: Message, state: FSMContext):
    try:
        bet = int(message.text)
        if bet < 10 or bet > 10000: raise ValueError
    except:
        await message.answer("❌ Число от 10 до 10000")
        return
    balance = await db.get_balance(message.from_user.id)
    if balance < bet:
        await message.answer(f"❌ Не хватает")
        await state.clear()
        return
    await db.subtract_balance(message.from_user.id, bet, f"Ставка в слотах")
    symbols = ["🍒","🍋","🍊","🍉","🔔","💎","7️⃣"]
    reels = [random.choice(symbols) for _ in range(3)]
    win = reels[0]==reels[1]==reels[2]
    mult = 10 if win and reels[0]=="7️⃣" else 5 if win and reels[0]=="💎" else 3 if win else 0
    if win:
        win_amount = bet * mult
        await db.add_balance(message.from_user.id, win_amount, f"Выигрыш в слотах")
        res_text = f"🎉 +{win_amount} NCoin (x{mult})"
    else:
        win_amount = 0
        res_text = f"😢 -{bet} NCoin"
    await db.add_game_history(message.from_user.id, "slot", bet, "win" if win else "loss", win_amount, {"reels":reels})
    new_balance = await db.get_balance(message.from_user.id)
    await message.answer(f"🎰 {' | '.join(reels)}\n\n{res_text}\n💰 Новый баланс: {new__balance} NCoin", parse_mode="Markdown")
    await state.clear()

@router.callback_query(F.data == "games")
async def games_menu(callback: CallbackQuery):
    await callback.message.edit_text("🎮 *Игры*\n/slot — слот\n/duel — дуэль\n/roulette — рулетка\n/rps — КНБ\n/history — история", parse_mode="Markdown", reply_markup=game_buttons())
    await callback.answer()
