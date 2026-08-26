"""
随访管理 Page Object
根据探索结果生成
"""
from typing import Optional, Dict
from playwright.sync_api import Page, expect


class FollowupPage:
    """随访管理页面对象"""
    
    # 根据探索发现的 URL 路径
    PATH_PATIENT = "/#/visitpatientmanage"  # 随访患者管理
    PATH_PROJECT = "/#/visitproject"        # 随访项目
    
    def __init__(self, page: Page):
        self.page = page
    
    def is_at_patient_manage(self) -> bool:
        """是否在随访患者管理页（已入组等）"""
        return "visitpatient" in self.page.url.lower() or "joinStatus" in self.page.url
    
    def is_at_project_manage(self) -> bool:
        """是否在随访项目页"""
        return "visitproject" in self.page.url.lower() or "followupproject" in self.page.url
    
    def is_at_patient_archive_with_join(self) -> bool:
        """是否在带joinStatus的患者档案页（入组人数跳转目标）"""
        return "patientarchieve" in self.page.url.lower() and "joinStatus" in self.page.url
    
    def get_table_total(self) -> Optional[int]:
        """获取表格总记录数"""
        # 方式1: 找"共 N 条"
        import re
        try:
            loc = self.page.get_by_text(re.compile(r"共\s*\d+\s*条")).first
            if loc.is_visible(timeout=2000):
                text = loc.inner_text(timeout=1500)
                m = re.search(r"共\s*(\d+)\s*条", text)
                if m:
                    return int(m.group(1))
        except:
            pass
        # 方式2: 数 tbody 行数
        try:
            rows = self.page.locator("tbody tr").count()
            return rows
        except:
            return None
    
    def get_page_summary(self) -> Dict:
        """获取页面摘要信息用于断言"""
        return {
            "url": self.page.url,
            "has_patient_archive": "patientarchieve" in self.page.url.lower(),
            "has_join_status": "joinStatus" in self.page.url,
            "has_visitpatient": "visitpatient" in self.page.url.lower(),
            "has_visitproject": "visitproject" in self.page.url.lower(),
        }
