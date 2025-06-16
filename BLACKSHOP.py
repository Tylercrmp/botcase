import os
os.environ['CRYPTOGRAPHY_OPENSSL_NO_LEGACY'] = '1'
import os
from datetime import datetime
from aiogram import Router, F, Bot, types
from aiogram.filters import Command
from aiogram.types import Message, PreCheckoutQuery, CallbackQuery
from aiogram import Dispatcher
import asyncio
import logging
from aiogram.utils.keyboard import InlineKeyboardBuilder
from firebase_admin import firestore, initialize_app
import firebase_admin
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

if not firebase_admin._apps:
    cred = firebase_admin.credentials.Certificate('black-shop-182af-firebase-adminsdk-fbsvc-d9074e3a5c.json')
    initialize_app(cred)
db = firestore.client()

BOT_TOKEN = "7997381513:AAGsGs8r3TQFXdhnWO8Ss_kxdIjGducHtEE"
PROVIDER_TOKEN = "YOUR_PROVIDER_TOKEN"

# Каналы, на которые нужно подписаться
REQUIRED_CHANNELS = [
    {"url": "https://t.me/blaacknews", "id": " "},
    {"url": "https://t.me/blackrussiavs", "id": " "}
]

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)

class PaymentState(StatesGroup):
    waiting_for_stars = State()

def main_menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(
            text="🛍️ Магазин",
            web_app=types.WebAppInfo(url="https://blackshop.rf.gd")
        )
    )
    builder.row(
        types.InlineKeyboardButton(
            text="💰 Пополнить",
            callback_data="replenish"
        ),
        types.InlineKeyboardButton(
            text="👤 Личный Кабинет",
            callback_data="personal_account"
        )
    )
    builder.row(
        types.InlineKeyboardButton(
            text="📖 Инструкция",
            callback_data="instructions"
        )
    )
    return builder.as_markup()

def get_subscription_check_keyboard():
    builder = InlineKeyboardBuilder()
    for channel in REQUIRED_CHANNELS:
        builder.row(
            types.InlineKeyboardButton(
                text=f"Подписаться {channel['id']}",
                url=channel['url']
            )
        )
    builder.row(
        types.InlineKeyboardButton(
            text="✅ Я подписался",
            callback_data="check_subscription"
        )
    )
    return builder.as_markup()

async def check_user_subscriptions(user_id: int) -> bool:
    try:
        for channel in REQUIRED_CHANNELS:
            chat_member = await bot.get_chat_member(chat_id=channel['id'], user_id=user_id)
            if chat_member.status not in ['member', 'administrator', 'creator']:
                return False
        return True
    except Exception as e:
        logging.error(f"Error checking subscription: {e}")
        # Если возникла ошибка
        return True

async def send_subscription_required_message(chat_id: int):
    channels_text = "\n".join([f"- {channel['id']}" for channel in REQUIRED_CHANNELS])
    await bot.send_message(
        chat_id=chat_id,
        text=f"⚠️ Для использования бота необходимо подписаться на следующие каналы:\n{channels_text}\n\n"
             "После подписки нажмите кнопку '✅ Я подписался'",
        reply_markup=get_subscription_check_keyboard()
    )

@dp.message(Command('start'))
async def start_command(msg: Message):
    await send_subscription_required_message(msg.chat.id)

@dp.callback_query(F.data == "check_subscription")
async def check_subscription_callback(callback: CallbackQuery):
    is_subscribed = await check_user_subscriptions(callback.from_user.id)
    if is_subscribed:
        await callback.message.delete()
        await callback.message.answer(
            f"Привет, {callback.from_user.first_name}\n"
            "🛒 Это CASE BLACK RUSSIA - Тут ты можешь купить кейсы и быстро вывести на свой аккаунт!\n"
            "⚠️ Боишься за аккаунт? - Не бойся! Мы не просим пароли, а выводим все Донатом!\n"
            "🍀 Быстрей испытай свою удачу!",
            reply_markup=main_menu_keyboard()
        )
    else:
        await callback.answer("Вы не подписаны на все каналы. Пожалуйста, подпишитесь и попробуйте снова.", show_alert=True)

@dp.callback_query(F.data == "replenish")
async def replenish_balance(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Пополнение баланса\n"
        "Введите количество желаемых звёзд (1 stars = 1.8 BC)\n"
        "Минимальная сумма: 1 stars"
    )
    await state.set_state(PaymentState.waiting_for_stars)
    await callback.answer()

@dp.message(PaymentState.waiting_for_stars)
async def process_stars_amount(msg: Message, state: FSMContext):
    try:
        stars = int(msg.text)
        if stars < 1:
            await msg.answer("Минимальная сумма - 1 stars")
            return
    except ValueError:
        await msg.answer("Пожалуйста, введите целое число (например: 1, 5, 10)")
        return
    
    total_bc = stars * 1.8
    
    await bot.send_invoice(
        chat_id=msg.chat.id,
        title=f"Пополнение баланса",
        description=f"Покупка {stars} stars ({total_bc} BC)",
        provider_token=PROVIDER_TOKEN,
        currency="XTR",
        prices=[types.LabeledPrice(label=f"{stars} stars", amount=stars)],
        payload=f"payment_{msg.from_user.id}_{stars}",
        start_parameter="stars_payment",
        need_name=False,
        need_phone_number=False,
        need_email=False,
        need_shipping_address=False,
        is_flexible=False
    )
    await state.clear()

@dp.pre_checkout_query()
async def pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@dp.message(F.successful_payment)
async def successful_payment(msg: Message):
    payment = msg.successful_payment
    stars = payment.total_amount
    total_bc = stars * 1.8
    
    user = msg.from_user
    payment_data = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "user_id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "stars": stars,
        "bc_amount": total_bc,
        "status": "completed"
    }
    
    db.collection("payments").document().set(payment_data)
    
    user_ref = db.collection("users").document(str(user.id))
    user_data = user_ref.get().to_dict() or {"balance": 0}
    user_ref.set({
        "balance": user_data["balance"] + total_bc,
        "last_update": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }, merge=True)
    
    await msg.answer(
        f"✅ Оплата {stars} stars прошла успешно!\n"
        f"Ваш баланс пополнен на {total_bc} BC",
        reply_markup=main_menu_keyboard()
    )

@dp.callback_query(F.data == "personal_account")
async def personal_account(callback: CallbackQuery):
    user_ref = db.collection("users").document(str(callback.from_user.id))
    user_data = user_ref.get().to_dict() or {"balance": 0}
    
    await callback.message.edit_text(
        f"📌 Личный кабинет\n\n"
        f"🆔 ID: {callback.from_user.id}\n"
        f"👤 Имя: {callback.from_user.full_name}\n"
        f"💰 Баланс: {user_data.get('balance', 0)} BC",
        reply_markup=main_menu_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "instructions")
async def show_instructions(callback: CallbackQuery):
    await callback.message.edit_text(
        "📖 Инструкция по пополнению баланса:\n\n"
        "1. Нажмите кнопку 'Пополнить'\n"
        "2. Введите количество звёзд (1 stars = 1.8 BC)\n"
        "3. Подтвердите платеж в открывшейся форме\n"
        "4. После успешной оплаты баланс пополнится автоматически\n\n"
        "⚠️ Внимание: минимальная сумма - 1 stars",
        reply_markup=main_menu_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery):
    await callback.message.edit_text(
        f"Главное меню\n"
        f"Выберите действие:",
        reply_markup=main_menu_keyboard()
    )
    await callback.answer()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())