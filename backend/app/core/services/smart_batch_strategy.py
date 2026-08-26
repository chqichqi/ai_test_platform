"""
智能批次策略 - 动态调整批次大小，自动修复截断问题
"""

import time
import math
from typing import Dict, List, Tuple
from app.core.simple_logger import logger


class SmartBatchStrategy:
    """智能批次策略管理器"""
    
    def __init__(self, max_tokens_limit: int = 30000):
        self.max_tokens_limit = max_tokens_limit
        self.success_history = []  # 记录每批成功率
        self.current_batch_size_multiplier = 1.0  # 当前批次大小系数
        self.min_multiplier = 0.25  # 最小系数（批次大小降到25%）
        self.max_multiplier = 1.5  # 最大系数（批次大小提升到150%）
        
    def calculate_initial_batch_params(self, modules: List[str]) -> Tuple[int, int, int]:
        """
        计算初始批次参数
        
        Args:
            modules: 模块列表
            
        Returns:
            (batch_count, modules_per_batch, estimated_cases_per_batch)
        """
        if len(modules) == 0:
            return (0, 0, 0)
        
        # 每模块平均生成4条用例，每条约1000 tokens
        # 使用安全策略：每批不超过max_tokens_limit的70%
        safe_max_tokens = int(self.max_tokens_limit * 0.7)
        theoretical_modules_per_batch = max(1, int(safe_max_tokens / (5 * 1000)))
        
        # 计算理论批次
        theoretical_batch_count = max(1, (len(modules) + theoretical_modules_per_batch - 1) // theoretical_modules_per_batch)
        
        # 稳定性优化：批次数乘以1.5，降低截断风险
        stable_batch_count = max(1, int(theoretical_batch_count * 1.5))
        modules_per_batch = max(1, (len(modules) + stable_batch_count - 1) // stable_batch_count)
        
        # 预估每批用例数
        estimated_cases_per_batch = modules_per_batch * 4
        
        logger.info(f"智能策略初始化: {len(modules)}模块 → {stable_batch_count}批（理论{theoretical_batch_count}批×1.5），每批{modules_per_batch}模块")
        
        return (stable_batch_count, modules_per_batch, estimated_cases_per_batch)
    
    def adjust_after_truncation(self, batch_idx: int, actual_cases: int, estimated_cases: int) -> Dict:
        """
        检测截断后动态调整策略
        
        Args:
            batch_idx: 当前批次索引
            actual_cases: 实际生成的用例数
            estimated_cases: 预估的用例数
            
        Returns:
            {
                "is_truncated": bool,
                "success_rate": float,
                "new_multiplier": float,
                "should_retry": bool,
                "retry_modules_count": int
            }
        """
        success_rate = actual_cases / estimated_cases if estimated_cases > 0 else 0
        
        # 判断是否截断（成功率<50%）
        is_truncated = success_rate < 0.5
        
        result = {
            "is_truncated": is_truncated,
            "success_rate": success_rate,
            "current_multiplier": self.current_batch_size_multiplier,
        }
        
        if is_truncated:
            # 截断：降低批次大小（减半）
            old_multiplier = self.current_batch_size_multiplier
            self.current_batch_size_multiplier = max(self.min_multiplier, self.current_batch_size_multiplier * 0.5)
            
            logger.warning(f"检测到截断（成功率{success_rate:.1%}）：批次大小系数从{old_multiplier:.2f}降低到{self.current_batch_size_multiplier:.2f}")
            
            # 记录失败历史
            self.success_history.append({
                "batch_idx": batch_idx,
                "success_rate": success_rate,
                "action": "decrease_multiplier"
            })
            
            result["new_multiplier"] = self.current_batch_size_multiplier
            result["should_retry"] = True
            result["retry_modules_count"] = max(1, int(3 * self.current_batch_size_multiplier))  # 重试时使用更小的批次
            
        elif success_rate > 0.9:
            # 成功率高：可以尝试提升批次大小（但保守一点，提升20%）
            if len(self.success_history) >= 3:
                # 连续3批成功率>90%，可以提升批次大小
                recent_success_rates = [h["success_rate"] for h in self.success_history[-3:]]
                if all(rate > 0.9 for rate in recent_success_rates):
                    old_multiplier = self.current_batch_size_multiplier
                    self.current_batch_size_multiplier = min(self.max_multiplier, self.current_batch_size_multiplier * 1.2)
                    
                    if self.current_batch_size_multiplier != old_multiplier:
                        logger.info(f"连续3批成功率>90%：批次大小系数从{old_multiplier:.2f}提升到{self.current_batch_size_multiplier:.2f}")
                    
                    result["new_multiplier"] = self.current_batch_size_multiplier
            
            self.success_history.append({
                "batch_idx": batch_idx,
                "success_rate": success_rate,
                "action": "stable"
            })
            
            result["should_retry"] = False
            
        else:
            # 成功率中等（50%-90%）：保持当前策略
            self.success_history.append({
                "batch_idx": batch_idx,
                "success_rate": success_rate,
                "action": "maintain"
            })
            
            result["new_multiplier"] = self.current_batch_size_multiplier
            result["should_retry"] = False
        
        return result
    
    def calculate_batch_max_tokens(self, modules_count: int) -> int:
        """
        根据当前批次大小系数计算max_tokens
        
        Args:
            modules_count: 当前批次的模块数
            
        Returns:
            max_tokens值
        """
        # 基础计算：每模块预估4条用例，每条1000 tokens
        base_tokens = modules_count * 4 * 1000
        
        # 应用当前批次大小系数（系数越小，max_tokens越小）
        adjusted_tokens = int(base_tokens * self.current_batch_size_multiplier)
        
        # 留20%余量
        safe_tokens = int(adjusted_tokens * 1.2)
        
        # 不超过max_tokens_limit的90%
        max_tokens = min(safe_tokens, int(self.max_tokens_limit * 0.9))
        
        return max_tokens
    
    def get_retry_strategy(self, failed_modules: List[str]) -> Dict:
        """
        为失败的批次制定重试策略
        
        Args:
            failed_modules: 失败批次的模块列表
            
        Returns:
            {
                "retry_count": int,
                "modules_per_retry": int,
                "max_tokens_per_retry": int
            }
        """
        # 将失败批次拆分成更小的批次重试
        retry_modules_count = max(1, int(len(failed_modules) * 0.5))  # 拆分成两半
        
        retry_count = max(1, (len(failed_modules) + retry_modules_count - 1) // retry_modules_count)
        
        max_tokens_per_retry = self.calculate_batch_max_tokens(retry_modules_count)
        
        logger.info(f"失败批次重试策略: {len(failed_modules)}模块 → {retry_count}批重试，每批{retry_modules_count}模块，max_tokens={max_tokens_per_retry}")
        
        return {
            "retry_count": retry_count,
            "modules_per_retry": retry_modules_count,
            "max_tokens_per_retry": max_tokens_per_retry
        }
    
    def get_statistics(self) -> Dict:
        """获取策略统计信息"""
        if len(self.success_history) == 0:
            return {
                "total_batches": 0,
                "avg_success_rate": 0,
                "truncated_count": 0,
                "current_multiplier": self.current_batch_size_multiplier
            }
        
        avg_success_rate = sum(h["success_rate"] for h in self.success_history) / len(self.success_history)
        truncated_count = sum(1 for h in self.success_history if h["success_rate"] < 0.5)
        
        return {
            "total_batches": len(self.success_history),
            "avg_success_rate": avg_success_rate,
            "truncated_count": truncated_count,
            "current_multiplier": self.current_batch_size_multiplier,
            "adjustments": len([h for h in self.success_history if h["action"] != "stable"])
        }


# 使用示例
if __name__ == "__main__":
    strategy = SmartBatchStrategy(max_tokens_limit=30000)
    
    # 初始化
    modules = ["模块A", "模块B", "模块C", "模块D", "模块E"]  # 示例模块名
    batch_count, modules_per_batch, estimated_cases = strategy.calculate_initial_batch_params(modules)
    
    print(f"初始策略: {batch_count}批, 每批{modules_per_batch}模块")
    
    # 模拟第一批截断
    result1 = strategy.adjust_after_truncation(0, 2, 20)  # 实际生成2条，预估20条
    print(f"批次1截断检测: {result1}")
    
    # 模拟第二批成功
    result2 = strategy.adjust_after_truncation(1, 18, 20)  # 实际生成18条，预估20条
    print(f"批次2成功: {result2}")
    
    # 获取统计
    stats = strategy.get_statistics()
    print(f"统计信息: {stats}")