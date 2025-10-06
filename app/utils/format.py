# app/utils/format.py
from aiogram.types import User

def fmt_username(u: User) -> str:
    parts = []
    if getattr(u, "first_name", None):
        parts.append(u.first_name)
    if getattr(u, "last_name", None):
        parts.append(u.last_name)
    name = " ".join(parts) if parts else (u.username or f"id{u.id}")
    if u.username:
        name = f"{name} (@{u.username})"
    return name
