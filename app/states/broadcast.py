# app/states/broadcast.py
from aiogram.fsm.state import StatesGroup, State

class BroadcastStates(StatesGroup):
    waiting_content = State()
    confirm = State()