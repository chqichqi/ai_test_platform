"""
患者档案 Page Object
"""
from typing import Optional
import re
from playwright.sync_api import Page, expect


class PatientPage:
    """患者档案页面对象"""
    
    PATH = "/#/patientarchieve"
    
    def __init__(self, page: Page):
        self.page = page
    
    def is_loaded(self) -> bool:
        """是否在患者档案页"""
        return "patientarchieve" in self.page.url.lower()
    
    def has_join_status_filter(self) -> bool:
        """是否有入组状态筛选（从随访入组人数跳转）"""
        return "joinStatus" in self.page.url
    
    def get_total_count(self) -> Optional[int]:
        """获取列表总记录数"""
        # 方式1: "共 N 条"
        try:
            loc = self.page.get_by_text(re.compile(r"共\s*\d+\s*条")).first
            if loc.is_visible(timeout=2000):
                text = loc.inner_text(timeout=1500)
                m = re.search(r"共\s*(\d+)\s*条", text)
                if m:
                    return int(m.group(1))
        except:
            pass
        # 方式2: tbody 行数
        try:
            rows = self.page.locator("tbody tr").count()
            return rows
        except:
            return None
    
    def has_no_data(self) -> bool:
        """是否显示暂无数据"""
        try:
            return self.page.get_by_text("暂无数据").is_visible(timeout=1500)
        except:
            return False
