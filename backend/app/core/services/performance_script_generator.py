"""
性能测试脚本生成器
从已审批的API测试用例生成 JMeter JMX 和 Locust locustfile
"""
import json
from datetime import datetime
from typing import List, Optional
from xml.etree.ElementTree import Element, SubElement, ElementTree

from app.core.models.api_test import ApiTestCase
from app.core.models.performance import PerformanceScenario
from app.core.logger import logger


def generate_jmx_from_api_cases(
    cases: List[ApiTestCase],
    scenario: PerformanceScenario = None,
    host: str = None,
) -> str:
    """从API测试用例生成JMeter JMX文件

    JMX结构:
    - TestPlan
      - ThreadGroup (含步进线程组配置)
        - HTTPSamplerProxy (每个用例)
        - ResponseAssertion (每个断言规则)
    """
    ET = ElementTree
    jmeter_test_plan = Element("jmeterTestPlan", version="1.2", properties="5.0", jmeter="5.6.3")

    # HashTree root
    hash_tree = SubElement(jmeter_test_plan, "hashTree")

    # TestPlan
    test_plan = SubElement(hash_tree, "TestPlan", guiclass="TestPlanGui", testclass="TestPlan", testname="API Performance Test Plan", enabled="true")
    string_prop = SubElement(test_plan, "stringProp", name="TestPlan.comments")
    string_prop.text = f"Auto-generated from {len(cases)} approved API test cases\nGenerated at: {datetime.utcnow().isoformat()}"
    bool_prop = SubElement(test_plan, "boolProp", name="TestPlan.functional_mode")
    bool_prop.text = "false"
    bool_prop2 = SubElement(test_plan, "boolProp", name="TestPlan.tearDown_on_shutdown")
    bool_prop2.text = "true"
    bool_prop3 = SubElement(test_plan, "boolProp", name="TestPlan.serialize_threadgroups")
    bool_prop3.text = "false"

    SubElement(hash_tree, "hashTree")  # TestPlan hashTree

    # ThreadGroup
    num_threads = str(scenario.concurrent_users if scenario else 100)
    ramp_up = str(scenario.ramp_up_period if scenario else 60)
    duration = str(scenario.duration if scenario else 300)

    thread_group = SubElement(
        hash_tree,
        "ThreadGroup",
        guiclass="ThreadGroupGui",
        testclass="ThreadGroup",
        testname="API Test Thread Group",
        enabled="true",
    )
    string_prop = SubElement(thread_group, "stringProp", name="ThreadGroup.on_sample_error")
    string_prop.text = "continue"

    element_prop = SubElement(thread_group, "elementProp", name="ThreadGroup.main_controller",
                              elementType="LoopController", guiclass="LoopControlPanel", testclass="LoopController", testname="Loop Controller", enabled="true")
    bool_prop = SubElement(element_prop, "boolProp", name="LoopController.continue_forever")
    bool_prop.text = "false"
    string_prop = SubElement(element_prop, "stringProp", name="LoopController.loops")
    string_prop.text = "-1"  # forever until duration ends

    string_prop = SubElement(thread_group, "stringProp", name="ThreadGroup.num_threads")
    string_prop.text = num_threads
    string_prop = SubElement(thread_group, "stringProp", name="ThreadGroup.ramp_time")
    string_prop.text = ramp_up

    # Duration assertion for thread group
    if scenario and scenario.step_enabled:
        string_prop = SubElement(thread_group, "stringProp", name="ThreadGroup.duration")
        string_prop.text = str(scenario.step_count * scenario.step_duration)
        string_prop = SubElement(thread_group, "stringProp", name="ThreadGroup.delay")
        string_prop.text = "0"
    else:
        string_prop = SubElement(thread_group, "stringProp", name="ThreadGroup.duration")
        string_prop.text = duration
        string_prop = SubElement(thread_group, "stringProp", name="ThreadGroup.delay")
        string_prop.text = "0"

    bool_prop = SubElement(thread_group, "boolProp", name="ThreadGroup.scheduler")
    bool_prop.text = "true"

    tg_hash_tree = SubElement(hash_tree, "hashTree")

    # Add HTTP Samplers for each API case
    for case in cases:
        method = (case.method or "GET").upper()
        path = case.path or "/"
        domain = host or case.base_url or "localhost"
        port = ""
        protocol = "https" if "https://" in domain else "http"
        domain = domain.replace("https://", "").replace("http://", "")

        if ":" in domain:
            parts = domain.split(":")
            domain = parts[0]
            port = parts[1]

        sampler = SubElement(
            tg_hash_tree,
            "HTTPSamplerProxy",
            guiclass="HttpTestSampleGui",
            testclass="HTTPSamplerProxy",
            testname=f"{method} {case.name}",
            enabled="true",
        )
        string_prop = SubElement(sampler, "stringProp", name="HTTPSampler.domain")
        string_prop.text = domain
        if port:
            string_prop = SubElement(sampler, "stringProp", name="HTTPSampler.port")
            string_prop.text = port
        string_prop = SubElement(sampler, "stringProp", name="HTTPSampler.protocol")
        string_prop.text = protocol
        string_prop = SubElement(sampler, "stringProp", name="HTTPSampler.method")
        string_prop.text = method
        string_prop = SubElement(sampler, "stringProp", name="HTTPSampler.path")
        string_prop.text = path

        element_prop = SubElement(sampler, "elementProp", name="HTTPSampler.Arguments", elementType="Arguments",
                                   guiclass="HTTPArgumentsPanel", testclass="Arguments", testname="User Defined Variables", enabled="true")
        args_tree = SubElement(element_prop, "collectionProp", name="Arguments.arguments")

        # Query params
        if case.query_params:
            for k, v in case.query_params.items():
                arg = SubElement(args_tree, "elementProp", name=k, elementType="HTTPArgument")
                bool_prop = SubElement(arg, "boolProp", name="HTTPArgument.always_encode")
                bool_prop.text = "false"
                string_prop = SubElement(arg, "stringProp", name="Argument.name")
                string_prop.text = k
                string_prop = SubElement(arg, "stringProp", name="Argument.value")
                string_prop.text = str(v)
                string_prop = SubElement(arg, "stringProp", name="Argument.metadata")
                string_prop.text = "="

        # Body
        if case.request_body and method in ("POST", "PUT", "PATCH"):
            bool_prop = SubElement(sampler, "boolProp", name="HTTPSampler.postBodyRaw")
            bool_prop.text = "true"
            string_prop = SubElement(sampler, "stringProp", name="HTTPSampler.Arguments")
            string_prop.text = json.dumps(case.request_body, ensure_ascii=False)

        # Headers
        header_mgr = SubElement(sampler, "HeaderManager", guiclass="HeaderPanel", testclass="HeaderManager",
                                 testname="HTTP Header Manager", enabled="true")
        headers_tree = SubElement(header_mgr, "collectionProp", name="HeaderManager.headers")
        if case.headers:
            for k, v in case.headers.items():
                header = SubElement(headers_tree, "elementProp", name="", elementType="Header")
                string_prop = SubElement(header, "stringProp", name="Header.name")
                string_prop.text = k
                string_prop = SubElement(header, "stringProp", name="Header.value")
                string_prop.text = str(v)

        # Response Assertion
        if case.expected_status:
            assertion = SubElement(
                tg_hash_tree,
                "ResponseAssertion",
                guiclass="AssertionGui",
                testclass="ResponseAssertion",
                testname=f"Assert {case.expected_status}",
                enabled="true",
            )
            collection_prop = SubElement(assertion, "collectionProp", name="Asserion.test_strings")
            string_prop = SubElement(collection_prop, "stringProp", name="0")
            string_prop.text = str(case.expected_status)
            string_prop = SubElement(assertion, "stringProp", name="Assertion.custom_message")
            string_prop.text = f"Expected status {case.expected_status}"

        SubElement(tg_hash_tree, "hashTree")

    xml_str = ET.tostring(jmeter_test_plan, encoding="unicode", method="xml")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_str


def generate_locustfile_from_api_cases(
    cases: List[ApiTestCase],
    host: str = None,
    scenario: PerformanceScenario = None,
) -> str:
    """从API测试用例生成locustfile.py（委托给locust_service中的生成器）"""
    # 此函数作为独立工具也可使用
    from app.core.services.locust_service import LocustService
    # Actually build it inline for standalone use
    weight_map = {"P0": 15, "P1": 10, "P2": 5, "P3": 2}

    task_methods = []
    for i, case in enumerate(cases):
        method = case.method or "GET"
        path = case.path or "/"
        weight = weight_map.get(case.priority, 5)

        safe_name = f"task_{i}_{case.name.replace(' ', '_').replace('-', '_').replace('/', '_')[:50]}"
        headers_str = json.dumps(case.headers or {}, ensure_ascii=False)
        params_str = json.dumps(case.query_params or {}, ensure_ascii=False)
        body_str = json.dumps(case.request_body or {}, ensure_ascii=False)
        method_lower = method.lower()

        task_methods.append(f'''
    @task({weight})
    def {safe_name}(self):
        """{case.name}"""
        headers = {headers_str}
        params = {params_str}

        with self.client.request(
            "{method}",
            "{path}",
            headers=headers,
            params=params,
            json={body_str} if "{method_lower}" in ("post", "put", "patch") else None,
            catch_response=True,
            name="{case.name}"
        ) as response:
            expected_status = {case.expected_status or 200}
            if response.status_code != expected_status:
                response.failure(
                    f"Expected status {{expected_status}}, got {{response.status_code}}"
                )
            else:
                response.success()
''')

    # 梯度配置
    step_shape = ""
    if scenario and scenario.step_enabled:
        step_shape = f'''

class StepLoadShape:
    step_count = {scenario.step_count}
    step_duration = {scenario.step_duration}
    step_thread_increment = {scenario.step_thread_increment}
    max_users = {scenario.concurrent_users or 100}

    def tick(self):
        from locust import LoadTestShape
        run_time = self.get_run_time()
        step_number = int(run_time / self.step_duration) + 1
        if step_number > self.step_count:
            return None
        user_count = step_number * self.step_thread_increment
        return (min(user_count, self.max_users), self.step_thread_increment)
'''

    locustfile = f'''"""
Auto-generated locustfile from approved API test cases
Host: {host or "http://localhost:8000"}
Cases count: {len(cases)}
Generated at: {datetime.utcnow().isoformat()}
"""
from locust import HttpUser, task, between

class ApiTestUser(HttpUser):
    wait_time = between(1, 3)
    host = "{host or "http://localhost:8000"}"
{''.join(task_methods)}
{step_shape}
'''
    return locustfile
