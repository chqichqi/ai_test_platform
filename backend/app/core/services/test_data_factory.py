"""业务测试数据 Factory 注册中心。不会默认执行任意 SQL；业务方可注册安全的领域工厂。"""
from typing import Any, Callable, Dict


class TestDataFactory:
    def __init__(self):
        self._factories: Dict[str, Callable] = {}

    def register(self, name: str, factory: Callable):
        if not callable(factory):
            raise TypeError("factory 必须是 callable")
        self._factories[str(name)] = factory

    def get(self, name: str):
        return self._factories.get(str(name or ""))

    def create(self, name: str, requirement, context, manager) -> Any:
        fn = self.get(name)
        if not fn:
            return None
        return fn(requirement, context, manager)

    @property
    def names(self):
        return list(self._factories.keys())
