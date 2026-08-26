# 设备管理-疾病统计
from playwright.sync_api import Page


class WorkPanelPage:
    def __init__(self, page: Page):
        self.page = page

    def navigate_to_workbench(self):
        self.page.locator("text=工作台").click()

    def navigate_to_patient_profile(self):
        self.page.locator("text=患者档案").click()

    def navigate_to_device_management(self):
        self.page.locator("text=设备管理").click()

    def navigate_to_device_list(self):
        self.page.locator("text=设备列表").click()

    def navigate_to_device_transceiver(self):
        self.page.locator("text=设备收发").click()

    def navigate_to_questionnaire_management(self):
        self.page.locator("text=问卷管理").click()

    def navigate_to_account_management(self):
        self.page.locator("text=账号管理").click()

    def navigate_to_data_management(self):
        self.page.locator("text=数据管理").click()

    def navigate_to_operation_configuration(self):
        self.page.locator("text=运营配置").click()

    def navigate_to_operation_log(self):
        self.page.locator("text=操作日志").click()

    def navigate_to_follow_up_management(self):
        self.page.locator("text=随访管理").click()