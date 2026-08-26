"""version_generator 工具函数"""
import re


def clean_module_name(raw: str) -> str:
    """清洗模块名——去掉逗号分隔的标签/BIZ编号"""
    if not raw:
        return "通用模块"
    # 去掉逗号、中文逗号后的内容（这些是标签不是模块名）
    cleaned = raw.replace("，", ",").split(",")[0].strip()
    # 去掉 BIZ编号、GEN编号
    cleaned = re.sub(r'\b(BIZ|GEN)\d+\b', '', cleaned).strip()
    # 去掉纯标签词
    for tag in ("自定义", "移除", "返回规范", "正常流程", "异常场景", "边界"):
        if cleaned == tag:
            return "通用模块"
    return cleaned[:30] if cleaned else "通用模块"
