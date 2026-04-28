import asyncio
import sys

from telethon import TelegramClient

from . import config as cfg
from .paths import SESSION_PATH, ensure_dirs


async def _run(c) -> None:
    client = TelegramClient(str(SESSION_PATH), c.api_id, c.api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        await client.start()
    me = await client.get_me()
    await client.disconnect()
    first = getattr(me, "first_name", "") or ""
    username = getattr(me, "username", None)
    print()
    print(f"登录成功: {first} (@{username or '无 username'}) id={me.id}")
    print("会话已保存。可以启动菜单栏程序了。")


def main() -> None:
    ensure_dirs()
    c = cfg.load()
    if not c.api_id or not c.api_hash:
        print(
            "错误: config.json 中缺少 api_id / api_hash。\n"
            "通常应由 install.sh 自动写入,请检查发布包的 _embedded_creds.py。",
            file=sys.stderr,
        )
        sys.exit(2)

    print("=== Telegram 登录 ===")
    print(f"会话文件: {SESSION_PATH}")
    print("接下来会让你输入手机号(带国家区号,例如 +8613800138000)、")
    print("Telegram 发到客户端的验证码,以及可选的 2FA 密码。")
    print()

    asyncio.run(_run(c))


if __name__ == "__main__":
    main()
