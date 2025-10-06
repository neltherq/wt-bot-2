# app/states/deposit.py
from aiogram.fsm.state import State, StatesGroup

class DepositStates(StatesGroup):
    waiting_amount = State()
    choosing_method = State()
