"""规则型测试数据生成器。随机只是生成策略之一，所有值都可追踪到 provider/generator。"""
import random
import secrets
import string
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional


class TestDataGenerator:
    def __init__(self):
        self._custom = {}
        self.register("uuid", lambda req, ctx: str(uuid.uuid4()))
        self.register("token", lambda req, ctx: secrets.token_hex(16))
        self.register("string", self._string)
        self.register("integer", self._integer)
        self.register("phone", self._phone)
        self.register("email", self._email)
        self.register("name", self._name)
        self.register("chinese_name", self._name)
        self.register("date", self._date)
        self.register("datetime", self._datetime)
        self.register("timestamp", lambda req, ctx: int(datetime.utcnow().timestamp() * 1000))
        self.register("boolean", lambda req, ctx: bool(random.getrandbits(1)))

    def register(self, name: str, func):
        self._custom[str(name).lower()] = func

    def generate(self, requirement, context: Optional[Dict[str, Any]] = None) -> Any:
        context = context or {}
        gen = (getattr(requirement, "generator", "auto") or "auto").lower()
        if gen == "auto":
            key = getattr(requirement, "key", "").lower()
            if any(x in key for x in ("phone", "mobile", "手机号", "手机")):
                gen = "phone"
            elif any(x in key for x in ("email", "邮箱", "邮件")):
                gen = "email"
            elif any(x in key for x in ("name", "姓名", "名称", "患者")):
                gen = "name"
            elif any(x in key for x in ("date", "日期", "生日")):
                gen = "date"
            elif any(x in key for x in ("id", "编号", "编码")):
                gen = "uuid"
            else:
                gen = "string"
        func = self._custom.get(gen, self._custom["string"])
        return func(requirement, context)

    @staticmethod
    def _suffix(context):
        return str(context.get("run_id", "")).replace("-", "")[-8:] or secrets.token_hex(4)

    def _string(self, req, ctx):
        length = int(getattr(req, "max_value", None) or 10)
        prefix = getattr(req, "format", "") or getattr(req, "key", "data")
        chars = "".join(random.choice(string.ascii_letters) for _ in range(max(1, min(length, 40))))
        return f"{prefix}_{self._suffix(ctx)}_{chars}"

    def _integer(self, req, ctx):
        lo = int(getattr(req, "min_value", None) if getattr(req, "min_value", None) is not None else 1)
        hi = int(getattr(req, "max_value", None) if getattr(req, "max_value", None) is not None else 999999)
        return random.randint(lo, max(lo, hi))

    def _phone(self, req, ctx):
        return "1" + random.choice("3,4,5,6,7,8,9".split(",")) + "".join(random.choice(string.digits) for _ in range(9))

    def _email(self, req, ctx):
        return f"test_{self._suffix(ctx)}_{secrets.token_hex(3)}@example.test"

    def _name(self, req, ctx):
        surnames = "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华"
        given = "伟芳娜秀英敏静强磊军洋勇艳杰娟涛明超秀兰霞平刚桂琴玉梅莉鹏丹鑫宇浩欣"
        return random.choice(surnames) + random.choice(given) + random.choice(given)

    def _date(self, req, ctx):
        days = random.randint(1, 365)
        return (date.today() + timedelta(days=days)).isoformat()

    def _datetime(self, req, ctx):
        days = random.randint(1, 30)
        return (datetime.utcnow() + timedelta(days=days)).isoformat(timespec="seconds")
