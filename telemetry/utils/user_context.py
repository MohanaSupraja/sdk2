from contextvars import ContextVar

_user_id_ctx: ContextVar[str | None] = ContextVar("user_id", default=None)


def set_user_context(user_id: str):
    _user_id_ctx.set(user_id)


def get_user_context() -> str | None:
    return _user_id_ctx.get()

