# app/handlers/deposit.py
import logging
import json
import random
import string
import re
from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from app.states.deposit import DepositStates
from app.keyboards.balance import back_kb, pay_methods_kb, pay_lolz_kb
from app.db import (
    create_payment,
    get_payment_by_comment,
    mark_payment_success,
    ensure_user,
    add_balance_rub,
)
from app.services import lolz  # build_pay_url / find_payment_by_comment / extract_success_operation

logger = logging.getLogger(__name__)
router = Router()

# ======== Константы ========
_EXPIRE_HOURS = 3           # срок действия платежа
_MIN_DEPOSIT_RUB = 100      # минимальная сумма пополнения


# ======== Вспомогательные функции таймера ========

def _coerce_dt(v):
    """Пытаемся привести created_at к datetime (UTC)."""
    if isinstance(v, datetime):
        return v
    if isinstance(v, str):
        try:
            if v.endswith("Z"):
                return datetime.strptime(v, "%Y-%m-%dT%H:%M:%SZ")
            if "+" in v:
                base = v.split("+", 1)[0].rstrip()
                return datetime.fromisoformat(base)
            return datetime.fromisoformat(v)
        except Exception:
            return None
    return None


def _expires_at(created_at: datetime | None) -> datetime:
    base = created_at or datetime.utcnow()
    return base + timedelta(hours=_EXPIRE_HOURS)


def _left_and_deadline(created_at: datetime | None) -> tuple[str, str]:
    exp = _expires_at(created_at)
    now = datetime.utcnow()
    left = exp - now
    if left.total_seconds() < 0:
        left = timedelta(0)
    hours = left.days * 24 + left.seconds // 3600
    minutes = (left.seconds % 3600) // 60
    seconds = left.seconds % 60
    left_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    deadline_str = exp.strftime("%d.%m %H:%M UTC")
    return left_str, deadline_str


def _is_expired(created_at: datetime | None) -> bool:
    return datetime.utcnow() >= _expires_at(created_at)


# ======== Генерация комментариев ========

def _gen_comment_local(length: int = 14) -> str:
    return "".join(random.choices(string.digits, k=length))


async def _gen_unique_comment() -> str:
    for _ in range(5):
        c = _gen_comment_local(14)
        if not await get_payment_by_comment(c):
            return c
    return _gen_comment_local(16)


# ======== Клавиатура для просроченного счёта ========

def expired_invoice_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔁 Создать новый платёж", callback_data="balance:deposit")]
    ])


# === старт пополнения через INLINE кнопку на экране баланса ===
@router.callback_query(F.data == "balance:deposit")
async def cb_balance_deposit(cq: CallbackQuery, state: FSMContext):
    try:
        await cq.answer()
        await cq.message.edit_text(
            "Введите сумму пополнения (в рублях):",
            reply_markup=back_kb("deposit:back"),
        )
        await state.set_state(DepositStates.waiting_amount)
    except Exception:
        logger.exception("balance:deposit handler failed")
        await cq.answer("Ошибка при открытии пополнения", show_alert=True)


# === fallback: если прилетает текст «пополнить» ===
@router.message(F.text.regexp(re.compile(r"(?i)^(\+?\s*)?пополнить$")))
async def msg_balance_deposit(message: Message, state: FSMContext):
    try:
        await message.answer(
            "Введите сумму пополнения (в рублях):",
            reply_markup=back_kb("deposit:back"),
        )
        await state.set_state(DepositStates.waiting_amount)
    except Exception:
        logger.exception("text deposit fallback failed")


# === ВАЖНО: сбрасываем стейт, если пользователь ушёл в другой раздел ===
_ALLOWED_PREFIXES = ("balance:deposit", "deposit:", "pay:")

@router.callback_query(DepositStates.waiting_amount)
async def clear_waiting_on_foreign_callback(cb: CallbackQuery, state: FSMContext):
    data = (cb.data or "")
    if data.startswith(_ALLOWED_PREFIXES):
        return  # наши кнопки — не трогаем
    await state.clear()
    return  # позволяем другим хендлерам обработать этот callback

@router.callback_query(DepositStates.choosing_method)
async def clear_choosing_on_foreign_callback(cb: CallbackQuery, state: FSMContext):
    data = (cb.data or "")
    if data.startswith(_ALLOWED_PREFIXES):
        return
    await state.clear()
    return


# === ввод суммы (целые рубли, минимум 100) ===
# Обрабатываем ТОЛЬКО то, что похоже на число (разрешаем "1 000", "1,000", "1_000")
@router.message(DepositStates.waiting_amount, F.text.regexp(r"^[\d\s,._]+$"))
async def deposit_amount_entered(message: Message, state: FSMContext):
    raw = (message.text or "").strip()
    numerish = re.sub(r"[ \t,._]", "", raw)

    try:
        amount = int(numerish)
        if amount <= 0:
            raise ValueError
    except Exception:
        return await message.reply("Укажи целое положительное число (в рублях).")

    if amount < _MIN_DEPOSIT_RUB:
        return await message.reply(
            f"Минимальная сумма пополнения — <b>{_MIN_DEPOSIT_RUB} ₽</b>.\n"
            f"Пожалуйста, введите сумму от {_MIN_DEPOSIT_RUB} ₽."
        )

    await state.update_data(amount=amount)
    await message.answer(
        f"Выберите метод оплаты на сумму {amount} ₽:",
        reply_markup=pay_methods_kb(),
    )
    await state.set_state(DepositStates.choosing_method)


# === назад из шага «введите сумму» ===
@router.callback_query(F.data == "deposit:back")
async def cb_deposit_back(cq: CallbackQuery, state: FSMContext):
    await cq.answer("Назад")
    await state.clear()
    try:
        await cq.message.delete()
    except Exception:
        await cq.message.edit_reply_markup(reply_markup=None)


# === назад из выбора метода оплаты ===
@router.callback_query(F.data == "pay:back")
async def cb_pay_back(cq: CallbackQuery, state: FSMContext):
    await cq.answer("Назад")
    await state.clear()
    try:
        await cq.message.delete()
    except Exception:
        await cq.message.edit_reply_markup(reply_markup=None)


# === выбор метода: lolz ===
@router.callback_query(F.data == "pay:method:lolz")
async def cb_pay_method_lolz(cq: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    amount = int(data.get("amount", 0))
    if amount <= 0:
        await cq.answer("Сумма не задана. Нажмите «Пополнить» снова.", show_alert=True)
        return
    if amount < _MIN_DEPOSIT_RUB:
        await cq.answer(
            f"Минимальная сумма — {_MIN_DEPOSIT_RUB} ₽. "
            "Введите новую сумму и попробуйте снова.",
            show_alert=True
        )
        return

    await ensure_user(cq.from_user.id, cq.from_user.username)

    # Создаём платёж
    comment = await _gen_unique_comment()
    await create_payment(
        user_id=cq.from_user.id,
        method="lolz",
        amount_rub=amount,
        comment=comment,
        status="pending",
        raw_json=None,
    )
    logger.info("payment pending created: user=%s amount=%s comment=%s", cq.from_user.id, amount, comment)

    pay_url = lolz.build_pay_url(amount_rub=amount, comment=comment)
    if not pay_url:
        await cq.answer("Ник lolz не настроен. Обратитесь к администратору.", show_alert=True)
        return

    left_str, deadline_str = _left_and_deadline(created_at=None)
    await cq.answer("Перейдите к оплате в lolz")
    await cq.message.edit_text(
        f"Метод оплаты: <b>lolz</b>\n"
        f"Сумма: <b>{amount} ₽</b>\n"
        f"Комментарий (код): <code>{comment}</code>\n\n"
        "1) Нажмите «Оплатить в lolz» и завершите перевод на сайте\n"
        "2) Вернитесь и нажмите «Проверить оплату»\n\n"
        f"⏳ <b>Осталось времени:</b> {left_str}\n"
        f"🕒 <b>Счёт действителен до:</b> {deadline_str}\n"
        "⚠️ После истечения срока кнопки оплаты будут отключены.",
        reply_markup=pay_lolz_kb(pay_url, comment),
    )


# === проверка оплаты ===
@router.callback_query(F.data.startswith("pay:check:"))
async def cb_pay_check(cq: CallbackQuery, state: FSMContext):
    try:
        comment = cq.data.split("pay:check:", 1)[1]
        rec = await get_payment_by_comment(comment)
        if not rec:
            await cq.answer("Локальная запись платежа не найдена", show_alert=True)
            return

        amount = int(rec["amount_rub"])
        created_at = _coerce_dt(rec.get("created_at")) if isinstance(rec, dict) else None
        expired = _is_expired(created_at)

        # Проверка в API Lolz
        res = await lolz.find_payment_by_comment(comment)
        status = res.get("status_code", 0)
        if status in (0, 401, 403):
            await cq.answer(
                "Проверка недоступна: нет/неверный API токен или ошибка сети.\n"
                "Админу: проверь LOLZ_API_TOKEN в .env и перезапусти бота.",
                show_alert=True
            )
            return

        op = lolz.extract_success_operation(res.get("json", {}), expected_amount_rub=amount)

        # если платёж найден — зачисляем
        if op:
            await add_balance_rub(cq.from_user.id, amount)
            await mark_payment_success(
                comment,
                ext_operation_id=op["operation_id"],
                raw_json=json.dumps(res["json"]),
            )
            await state.clear()
            await cq.answer("Оплата подтверждена")
            # Можно оставить edit_text; если хочешь — замени на новое сообщение
            await cq.message.edit_text(
                f"✅ Пополнение успешно\n"
                f"Сумма: <b>{amount} ₽</b>\n"
                f"Код: <code>{comment}</code>\n"
                f"Операция: <code>{op['operation_id']}</code>",
                reply_markup=None
            )
            return

        # если не оплачено и время истекло — НЕ редактируем старое сообщение,
        # снимаем с него клавиатуру и шлём НОВОЕ сообщение.
        if expired:
            try:
                await cq.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass
            await cq.message.answer(
                "⛔️ <b>Время сессии истекло.</b>\n"
                "Создайте новый платёж, нажав «Пополнить», и повторите попытку.",
                reply_markup=expired_invoice_kb()
            )
            await cq.answer()
            return

        # если не оплачено и срок ещё действует — только уведомление
        await cq.answer("Платёж пока не найден")

    except Exception:
        logger.exception("pay:check handler failed")
        await cq.answer("Ошибка при проверке", show_alert=True)
