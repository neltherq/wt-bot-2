# app/handlers/menu.py
import logging
from math import ceil
from pathlib import Path

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, FSInputFile

from app.keyboards.main_menu import main_menu_kb
from app.keyboards.accounts import accounts_list_kb, account_card_kb, MAX_ROWS
from app.db import (
    ensure_user, get_balance_rub, get_user,
    list_accounts, count_accounts, get_account_by_id, purchase_account
)

logger = logging.getLogger(__name__)
router = Router()

CATEGORY = "WarThunder"

# ---------- поиск локальной шапки ----------
def _find_header_image() -> str | None:
    """
    Ищем images/image.png в нескольких местах:
    - <корень>/images/image.png (рядом с main.py)
    - <cwd>/images/image.png
    - app/images/image.png
    - app/handlers/images/image.png
    """
    candidates: list[Path] = [
        Path(__file__).resolve().parents[2] / "images" / "image.png",
        Path.cwd() / "images" / "image.png",
        Path(__file__).resolve().parents[1] / "images" / "image.png",
        Path(__file__).resolve().parent / "images" / "image.png",
    ]
    for p in candidates:
        if p.exists():
            logger.info("Header image found: %s", p)
            return str(p)
    logger.warning("Header image NOT found. Tried: %s", " | ".join(map(str, candidates)))
    return None

def _header_caption(total: int) -> str:
    return (
        "🛍 <b>МАГАЗИН</b>\n\n"
        f"🛒 <b>Всего товаров:</b> {total}\n\n"
        "👉 <b>Выберите товар:</b>"
    )

# ---------------- /start ----------------
@router.message(CommandStart())
async def start(message: Message):
    await ensure_user(message.from_user.id, message.from_user.username)
    await message.answer(
        "👋 Добро пожаловать! Выберите действие на клавиатуре ниже.",
        reply_markup=main_menu_kb()
    )

# --------- Аккаунты: шапка(картинка) + КЛАВИАТУРА СПИСКА В ЭТОМ ЖЕ СООБЩЕНИИ ---------
@router.message(F.text == "🧾 Аккаунты")
async def open_accounts(message: Message):
    total = await count_accounts(CATEGORY)
    page = 1
    items = await list_accounts(CATEGORY, limit=MAX_ROWS, offset=0)
    kb = accounts_list_kb(CATEGORY, items, total, page, per_page=MAX_ROWS)

    caption = _header_caption(total)
    header_path = _find_header_image()
    if header_path:
        try:
            # ОДНО сообщение: фото + подпись + клавиатура списка
            await message.answer_photo(photo=FSInputFile(header_path), caption=caption, reply_markup=kb)
            return
        except Exception as e:
            logger.error("Failed to send header image %s: %s", header_path, e)

    # если картинки нет — отправим просто текст шапки с той же клавиатурой
    await message.answer(caption, reply_markup=kb)

# --------- Профиль / инфо ---------
@router.message(F.text == "👤 Профиль")
async def show_profile(message: Message):
    await ensure_user(message.from_user.id, message.from_user.username)
    u = await get_user(message.from_user.id)
    bal = await get_balance_rub(message.from_user.id)
    username = u.get("username") or "—"
    await message.answer(
        "👤 <b>Мой профиль</b>\n"
        f"ID: <code>{message.from_user.id}</code>\n"
        f"Username: @{username}\n"
        f"Баланс: <b>{bal} ₽</b>"
    )

@router.message(F.text == "❓ Помощь")
async def help_text(message: Message):
    await message.answer(
        "❓ <b>Помощь</b>\n"
        "— В «🧾 Аккаунты» шапка и список в одном сообщении.\n"
        "— Жмите на товар, чтобы открыть карточку и купить.\n"
        "— «💰 Баланс» — пополнение через lolz уже работает."
    )

@router.message(F.text == "📞 Поддержка")
async def support_text(message: Message):
    await message.answer("📞 Поддержка: @sainz")

# --------- «Главное меню» (из инлайн-кнопки) ---------
@router.callback_query(F.data == "main:menu")
async def cb_main_menu(cq: CallbackQuery):
    await cq.answer()
    try:
        await cq.message.delete()
    except Exception:
        pass
    await cq.message.answer("Главное меню:", reply_markup=main_menu_kb())

# --------- Пагинация / Назад: пересоздаём шапку+список одним сообщением ---------
@router.callback_query(F.data.startswith("acc:page:"))
async def cb_acc_page(cq: CallbackQuery):
    await cq.answer()
    try:
        page = int(cq.data.split("acc:page:", 1)[1])
    except Exception:
        page = 1

    # всегда удаляем текущее сообщение (это могла быть карточка)
    try:
        await cq.message.delete()
    except Exception:
        pass

    total = await count_accounts(CATEGORY)
    pages = max(1, ceil(total / MAX_ROWS)) if MAX_ROWS else 1
    page = max(1, min(page, pages))
    offset = (page - 1) * MAX_ROWS

    items = await list_accounts(CATEGORY, limit=MAX_ROWS, offset=offset)
    kb = accounts_list_kb(CATEGORY, items, total, page, per_page=MAX_ROWS)

    caption = _header_caption(total)
    header_path = _find_header_image()
    if header_path:
        try:
            await cq.message.answer_photo(photo=FSInputFile(header_path), caption=caption, reply_markup=kb)
            return
        except Exception as e:
            logger.error("Failed to send header image on page change %s: %s", header_path, e)

    await cq.message.answer(caption, reply_markup=kb)

# --------- Карточка товара ---------
@router.callback_query(F.data.startswith("acc:pick:"))
async def cb_acc_pick(cq: CallbackQuery):
    await cq.answer()
    # формат acc:pick:<id>:<page>
    parts = cq.data.split(":")
    acc_id = parts[2]
    page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 1

    acc = await get_account_by_id(acc_id)
    if not acc or acc.get("status") != "available":
        # перерисуем список
        return await cb_acc_page(CallbackQuery(
            id=cq.id, from_user=cq.from_user, chat_instance=cq.chat_instance, message=cq.message, data=f"acc:page:{page}"
        ))

    title = acc.get("button_title") or "Без названия"
    price = acc.get("price_rub") or 0
    caption = acc.get("caption") or "—"
    photo_id = acc.get("photo_file_id")

    text = (
        f"🧾 <b>{title}</b>\n"
        f"💵 Цена: <b>{price} ₽</b>\n\n"
        f"{caption}"
    )
    kb = account_card_kb(acc_id=int(acc_id), page=page)

    # удаляем сообщение со списком и показываем карточку
    try:
        await cq.message.delete()
    except Exception:
        pass

    if photo_id:
        try:
            await cq.message.answer_photo(photo=photo_id, caption=text, reply_markup=kb)
        except Exception:
            await cq.message.answer(text, reply_markup=kb)
    else:
        await cq.message.answer(text, reply_markup=kb)

# --------- Покупка (с сообщением о нехватке денег) ---------
@router.callback_query(F.data.startswith("acc:buy:"))
async def cb_acc_buy(cq: CallbackQuery):
    await cq.answer()
    acc_id = int(cq.data.split("acc:buy:", 1)[1])

    # 1) проверим цену и баланс
    acc = await get_account_by_id(acc_id)
    if not acc or acc.get("status") != "available":
        return await cq.answer("Товар уже недоступен.", show_alert=True)

    price = int(acc.get("price_rub", 0))
    title = acc.get("button_title") or "Товар"
    user_balance = await get_balance_rub(cq.from_user.id)

    if user_balance < price:
        need = price - user_balance
        text = (
            "💸 <b>Недостаточно средств</b>\n"
            f"Товар: <b>{title}</b>\n"
            f"Цена: <b>{price} ₽</b>\n"
            f"Ваш баланс: <b>{user_balance} ₽</b>\n"
            f"Не хватает: <b>{need} ₽</b>\n\n"
            "Чтобы пополнить, откройте «💰 Баланс» в меню и выберите «Пополнить»."
        )
        # Покажем отдельным сообщением, карточку не трогаем
        await cq.message.answer(text)
        return

    # 2) денег хватает — проводим покупку
    result = await purchase_account(user_id=cq.from_user.id, acc_id=acc_id)
    status = result["status"]

    if status == "ok":
        creds = result["creds"]
        title = result["title"]
        price = result["price_rub"]

        text = (
            "✅ <b>Покупка успешна!</b>\n"
            f"Товар: <b>{title}</b>\n"
            f"Списано: <b>{price} ₽</b>\n\n"
            f"Данные для входа:\n<code>{creds}</code>"
        )
        try:
            await cq.message.edit_caption(caption=text, reply_markup=None)
        except Exception:
            try:
                await cq.message.edit_text(text, reply_markup=None)
            except Exception:
                await cq.message.answer(text)
        return

    if status == "not_available":
        await cq.answer("Товар уже недоступен.", show_alert=True)
        return

    # что-то пошло не так
    logger.error("purchase_account failed: %r", result)
    await cq.answer("Ошибка при покупке. Попробуйте позже.", show_alert=True)
