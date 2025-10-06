# app/states/accounts.py
from aiogram.fsm.state import StatesGroup, State

class AddAccountStates(StatesGroup):
    waiting_rank = State()         # выбор раздела (rank)
    waiting_creds = State()         # ждём "login:password"
    waiting_button_title = State()  # ждём название кнопки
    waiting_photo = State()         # ждём фото с подписью
    waiting_price = State()         # ждём цену (целое число ₽)
