"""测试数据 Provider：统一决定数据从哪里来，不让 LLM/Playwright 直接编数据。"""
from abc import ABC, abstractmethod
from typing import Any, Dict


class TestDataProvider(ABC):
    name = "base"

    @abstractmethod
    def provide(self, requirement, context: Dict[str, Any], manager) -> Any:
        raise NotImplementedError

    def acquire(self, requirement, context, manager):
        value = self.provide(requirement, context, manager)
        return value, {"provider": self.name, "resource": value}


class StaticDataProvider(TestDataProvider):
    name = "static"
    def provide(self, requirement, context, manager):
        return requirement.value


class SharedDataProvider(TestDataProvider):
    name = "shared"
    def provide(self, requirement, context, manager):
        cache_key = f"shared:{requirement.key}:{requirement.value}"
        if cache_key in manager.shared_cache:
            return manager.shared_cache[cache_key]
        value = requirement.value
        manager.shared_cache[cache_key] = value
        return value


class GeneratedDataProvider(TestDataProvider):
    name = "generator"
    def provide(self, requirement, context, manager):
        return manager.generator.generate(requirement, context)


class MutationDataProvider(TestDataProvider):
    name = "mutation"

    def provide(self, requirement, context, manager):
        return manager.mutate_value(requirement, requirement.source_value)


class ConsumableDataProvider(GeneratedDataProvider):
    name = "consumable"
    def acquire(self, requirement, context, manager):
        # 默认创建“独立实例”，不删除、不复用。业务系统若有真正 Factory 可注册同名 provider。
        value = self.provide(requirement, context, manager)
        return value, {"provider": self.name, "resource": value, "state": "allocated", "consumed": False}


class SeededDataProvider(TestDataProvider):
    name = "seeded"
    def provide(self, requirement, context, manager):
        factory = manager.factories.get(requirement.factory or requirement.key)
        if factory:
            return factory(requirement, context, manager)
        # 没有业务 Seeder 时，至少提供一个可追踪的 seed marker；不会伪称数据库已有数据。
        return manager.generator.generate(requirement, context)


class FactoryDataProvider(SeededDataProvider):
    name = "factory"


class DependentDataProvider(TestDataProvider):
    name = "dependent"
    def provide(self, requirement, context, manager):
        return manager.generator.generate(requirement, context)


class TestDataProviderRegistry:
    def __init__(self):
        self.providers = {}
        for p in (StaticDataProvider(), SharedDataProvider(), GeneratedDataProvider(),
                  MutationDataProvider(), ConsumableDataProvider(), SeededDataProvider(), FactoryDataProvider(),
                  DependentDataProvider()):
            self.register(p)

    def register(self, provider: TestDataProvider):
        self.providers[provider.name] = provider

    def get(self, name: str):
        return self.providers.get((name or "generator").lower(), self.providers["generator"])
