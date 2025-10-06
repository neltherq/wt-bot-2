# app/handlers/deposit.py
import logging
import json
import random
import string
import re

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
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
from app.services import lolz  # build_pay_url / find_payment_by_comment / extract_success_operation / extract_any_success_amount

logger = logging.getLogger(__name__)
router = Router()


def _gen_comment_local(length: int = 14) -> str:
    return "".join(random.choices(string.digits, k=length))


async def _gen_unique_comment() -> str:
    # несколько попыток с 14 знаками; если внезапно коллизия — расширим
    for _ in range(5):
        c = _gen_comment_local(14)
        if not await get_payment_by_comment(c):
            return c
    return _gen_comment_local(16)


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


# === fallback: если вдруг прилетает ТЕКСТ «пополнить» (на случай сторонних панелей/ввода) ===
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


# === ввод суммы (целые рубли) ===
@router.message(DepositStates.waiting_amount)
async def deposit_amount_entered(message: Message, state: FSMContext):
    try:
        amount = int(message.text.strip())
        if amount <= 0:
            raise ValueError
    except Exception:
        return await message.reply("Укажи целое положительное число (в рублях).")

    try:
        await state.update_data(amount=amount)
        await message.answer(
            f"Выберите метод оплаты на сумму {amount} ₽:",
            reply_markup=pay_methods_kb(),
        )
        await state.set_state(DepositStates.choosing_method)
    except Exception:
        logger.exception("deposit_amount_entered failed")


# === назад из шага «введите сумму» ===
@router.callback_query(F.data == "deposit:back")
async def cb_deposit_back(cq: CallbackQuery, state: FSMContext):
    try:
        await cq.answer("Назад")
        await state.clear()
        try:
            await cq.message.delete()
        except Exception:
            await cq.message.edit_reply_markup(reply_markup=None)
    except Exception:
        logger.exception("deposit:back handler failed")


# === назад из выбора метода оплаты ===
@router.callback_query(F.data == "pay:back")
async def cb_pay_back(cq: CallbackQuery, state: FSMContext):
    try:
        await cq.answer("Назад")
        await state.clear()
        try:
            await cq.message.delete()
        except Exception:
            await cq.message.edit_reply_markup(reply_markup=None)
    except Exception:
        logger.exception("pay:back handler failed")


# === выбор метода: lolz (ссылка по username) ===
@router.callback_query(F.data == "pay:method:lolz")
async def cb_pay_method_lolz(cq: CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        amount = int(data.get("amount", 0))
        if amount <= 0:
            await cq.answer("Сумма не задана. Нажмите «Пополнить» снова.", show_alert=True)
            return

        await ensure_user(cq.from_user.id, cq.from_user.username)

        # Генерим уникальный comment и создаём локальную запись платежа
        comment = await _gen_unique_comment()
        await create_payment(
            user_id=cq.from_user.id,
            method="lolz",
            amount_rub=amount,
            comment=comment,
            status="pending",
            raw_json=None,
        )
        logger.info(
            "payment pending created: user=%s amount=%s comment=%s",
            cq.from_user.id, amount, comment
        )

        # Строим URL для ручной оплаты
        pay_url = lolz.build_pay_url(amount_rub=amount, comment=comment)
        if not pay_url:
            await cq.answer("Ник lolz не настроен. Обратитесь к администратору.", show_alert=True)
            return

        await cq.answer("Перейдите к оплате в lolz")
        await cq.message.edit_text(
            f"Метод оплаты: <b>lolz</b>\n"
            f"Сумма: <b>{amount} ₽</b>\n"
            f"Комментарий (код): <code>{comment}</code>\n\n"
            "1) Нажмите «Оплатить в lolz» и завершите перевод на сайте\n"
            "2) Вернитесь и нажмите «Проверить оплату»",
            reply_markup=pay_lolz_kb(pay_url, comment),
        )
        # остаёмся в DepositStates.choosing_method
    except Exception:
        logger.exception("pay:method:lolz handler failed")
        await cq.answer("Ошибка при выборе метода", show_alert=True)


# === повторная проверка оплаты по comment (с защитой по сумме) ===
@router.callback_query(F.data.startswith("pay:check:"))
async def cb_pay_check(cq: CallbackQuery, state: FSMContext):
    try:
        comment = cq.data.split("pay:check:", 1)[1]
        rec = await get_payment_by_comment(comment)
        if not rec:
            await cq.answer("Локальная запись платежа не найдена", show_alert=True)
            return

        amount = int(rec["amount_rub"])

        # Запрос в lolz API
        res = await lolz.find_payment_by_comment(comment)
        status = res.get("status_code", 0)

        # Нет токена / неверный токен / ошибка сети — информируем и выходим
        if status in (0, 401, 403):
            await cq.answer(
                "Проверка недоступна: нет/неверный API токен или ошибка сети.\n"
                "Админу: проверь LOLZ_API_TOKEN в .env и перезапусти бота.",
                show_alert=True
            )
            return

        # 1) Ищем платёж с ТОЧНО такой суммой
        op = lolz.extract_success_operation(res.get("json", {}), expected_amount_rub=amount)
        if op:
            await add_balance_rub(cq.from_user.id, amount)
            await mark_payment_success(
                comment,
                ext_operation_id=op["operation_id"],
                raw_json=json.dumps(res["json"]),
            )
            await state.clear()
            await cq.answer("Оплата подтверждена")
            return await cq.message.edit_text(
                f"✅ Пополнение успешно\n"
                f"Сумма: <b>{amount} ₽</b>\n"
                f"Код: <code>{comment}</code>\n"
                f"Операция: <code>{op['operation_id']}</code>"
            )

        # 2) Если платёж по коду есть, но сумма ДРУГАЯ — предупредим
        mismatch_sum = lolz.extract_any_success_amount(res.get("json", {}))
        if mismatch_sum is not None:
            await cq.answer("Оплата найдена, но сумма не совпадает", show_alert=True)
            return await cq.message.reply(
                "⚠️ Оплата по коду найдена, но сумма не совпадает.\n"
                f"Ожидали: <b>{amount} ₽</b>\n"
                f"Получено: <b>{mismatch_sum} ₽</b>\n\n"
                "Если это ваша оплата — свяжитесь с поддержкой или оплатите корректную сумму."
            )

        # 3) Иначе — по этому коду ещё ничего не пришло
        await cq.answer("Платёж пока не найден")
    except Exception:
        logger.exception("pay:check handler failed")
        await cq.answer("Ошибка при проверке", show_alert=True)
