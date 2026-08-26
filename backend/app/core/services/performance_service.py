"""
性能测试服务
支持JMeter脚本管理、场景配置、执行监控
"""

import os
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import json
import asyncio
import re
from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session

from app.core.models.performance import (
    JMeterScript, ScriptVersion, PerformanceScenario,
    PerformanceTestExecution, PerformanceMetric, PerformanceReport,
    GrafanaDashboard, PerformanceTestStatus, ScriptStatus
)
from app.core.logger import logger


class JMeterScriptService:
    """JMeter脚本服务"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create_script(
        self,
        project_id: int,
        name: str,
        description: str = None,
        file_content: str = None,
        created_by: int = None
    ) -> JMeterScript:
        """创建JMeter脚本"""
        script = JMeterScript(
            project_id=project_id,
            name=name,
            description=description,
            file_content=file_content,
            file_size=len(file_content) if file_content else 0,
            status=ScriptStatus.DRAFT.value,
            created_by=created_by
        )
        
        if file_content:
            self._parse_jmx(script, file_content)
        
        self.db.add(script)
        self.db.commit()
        self.db.refresh(script)
        
        logger.info(f"创建JMeter脚本: {script.name}")
        return script
    
    def update_script(
        self,
        script_id: int,
        name: str = None,
        description: str = None,
        file_content: str = None,
        version_note: str = None
    ) -> JMeterScript:
        """更新JMeter脚本"""
        script = self.db.query(JMeterScript).filter(
            JMeterScript.id == script_id
        ).first()
        
        if not script:
            raise ValueError("脚本不存在")
        
        if file_content and file_content != script.file_content:
            version = ScriptVersion(
                script_id=script_id,
                version=script.version,
                file_content=script.file_content,
                version_note=version_note or f"版本 {script.version}",
                created_by=script.created_by
            )
            self.db.add(version)
            
            script.version += 1
            script.file_content = file_content
            script.file_size = len(file_content)
            script.version_note = version_note
            
            self._parse_jmx(script, file_content)
        
        if name:
            script.name = name
        if description:
            script.description = description
        
        self.db.commit()
        self.db.refresh(script)
        
        return script
    
    def _parse_jmx(self, script: JMeterScript, content: str) -> None:
        """解析JMX文件"""
        try:
            root = ET.fromstring(content)
            
            thread_groups = []
            samplers = []
            
            for tg in root.findall(".//ThreadGroup"):
                tg_info = {
                    "name": tg.get("name", ""),
                    "enabled": tg.get("enabled", "true"),
                    "num_threads": None,
                    "ramp_time": None,
                    "loops": None
                }
                
                string_prop = tg.findall("stringProp")
                int_prop = tg.findall("intProp")
                
                for prop in string_prop:
                    name = prop.get("name", "")
                    text = prop.text
                    if name == "ThreadGroup.num_threads" and text:
                        tg_info["num_threads"] = int(text)
                    elif name == "ThreadGroup.ramp_time" and text:
                        tg_info["ramp_time"] = int(text)
                    elif name == "LoopController.loops" and text:
                        tg_info["loops"] = int(text) if text != "-1" else -1
                
                thread_groups.append(tg_info)
            
            for sampler in root.findall(".//*[starts-with(name, 'Sampler') or @testclass]"):
                if sampler.tag.endswith("Sampler") or sampler.get("testclass") in [
                    "HTTPSampler", "HTTPSamplerProxy", "JavaSampler", "JSR223Sampler"
                ]:
                    sampler_info = {
                        "name": sampler.get("name", ""),
                        "type": sampler.get("testclass", sampler.tag),
                        "enabled": sampler.get("enabled", "true")
                    }
                    samplers.append(sampler_info)
            
            script.thread_groups = thread_groups
            script.samplers = samplers
            script.status = ScriptStatus.VALIDATED.value
            script.validation_message = "JMX解析成功"
            
            for tg in root.findall(".//TestPlan"):
                script.test_plan_name = tg.get("name", "")
                break
                
        except ET.ParseError as e:
            script.status = ScriptStatus.ERROR.value
            script.validation_message = f"JMX解析失败: {str(e)}"
        except Exception as e:
            script.status = ScriptStatus.ERROR.value
            script.validation_message = f"解析异常: {str(e)}"
    
    def validate_script(self, script_id: int) -> Dict[str, Any]:
        """验证脚本"""
        script = self.db.query(JMeterScript).filter(
            JMeterScript.id == script_id
        ).first()
        
        if not script:
            return {"valid": False, "message": "脚本不存在"}
        
        if script.file_content:
            self._parse_jmx(script, script.file_content)
            self.db.commit()
        
        return {
            "valid": script.status == ScriptStatus.VALIDATED.value,
            "message": script.validation_message,
            "thread_groups": script.thread_groups,
            "samplers": script.samplers
        }


class PerformanceScenarioService:
    """性能测试场景服务"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create_scenario(
        self,
        project_id: int,
        script_id: int,
        name: str,
        concurrent_users: int = 100,
        ramp_up_period: int = 60,
        duration: int = 300,
        target_tps: float = None,
        target_rt: float = None,
        description: str = None,
        created_by: int = None
    ) -> PerformanceScenario:
        """创建性能测试场景"""
        script = self.db.query(JMeterScript).filter(
            JMeterScript.id == script_id
        ).first()
        
        if not script:
            raise ValueError("脚本不存在")
        
        thread_group_config = []
        if script.thread_groups:
            for tg in script.thread_groups:
                tg_config = {
                    "name": tg.get("name", "Thread Group"),
                    "num_threads": concurrent_users,
                    "ramp_time": ramp_up_period,
                    "loops": -1 if duration > 0 else 1,
                    "duration": duration
                }
                thread_group_config.append(tg_config)
        else:
            thread_group_config = [{
                "name": "Thread Group",
                "num_threads": concurrent_users,
                "ramp_time": ramp_up_period,
                "loops": -1,
                "duration": duration
            }]
        
        scenario = PerformanceScenario(
            project_id=project_id,
            script_id=script_id,
            name=name,
            description=description,
            concurrent_users=concurrent_users,
            ramp_up_period=ramp_up_period,
            duration=duration,
            target_tps=target_tps,
            target_rt=target_rt,
            thread_group_config=thread_group_config,
            created_by=created_by
        )
        
        self.db.add(scenario)
        self.db.commit()
        self.db.refresh(scenario)
        
        logger.info(f"创建性能测试场景: {scenario.name}")
        return scenario
    
    def update_scenario(
        self,
        scenario_id: int,
        **kwargs
    ) -> PerformanceScenario:
        """更新场景"""
        scenario = self.db.query(PerformanceScenario).filter(
            PerformanceScenario.id == scenario_id
        ).first()
        
        if not scenario:
            raise ValueError("场景不存在")
        
        for key, value in kwargs.items():
            if hasattr(scenario, key) and value is not None:
                setattr(scenario, key, value)
        
        self.db.commit()
        self.db.refresh(scenario)
        
        return scenario


class PerformanceExecutionService:
    """性能测试执行服务"""
    
    JMETER_COMMAND = "jmeter"
    
    def __init__(self, db: Session):
        self.db = db
    
    def start_execution(
        self,
        scenario_id: int,
        name: str = None,
        triggered_by: str = "manual",
        created_by: int = None
    ) -> PerformanceTestExecution:
        """启动性能测试"""
        scenario = self.db.query(PerformanceScenario).filter(
            PerformanceScenario.id == scenario_id
        ).first()
        
        if not scenario:
            raise ValueError("场景不存在")
        
        script = self.db.query(JMeterScript).filter(
            JMeterScript.id == scenario.script_id
        ).first()
        
        if not script or not script.file_content:
            raise ValueError("脚本内容为空")
        
        execution = PerformanceTestExecution(
            project_id=scenario.project_id,
            scenario_id=scenario_id,
            script_id=scenario.script_id,
            name=name or f"{scenario.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            status=PerformanceTestStatus.RUNNING.value,
            start_time=datetime.utcnow(),
            triggered_by=triggered_by,
            created_by=created_by
        )
        
        self.db.add(execution)
        self.db.commit()
        self.db.refresh(execution)
        
        asyncio.create_task(self._run_jmeter(execution, scenario, script))
        
        logger.info(f"启动性能测试: {execution.name}")
        return execution
    
    async def _run_jmeter(
        self,
        execution: PerformanceTestExecution,
        scenario: PerformanceScenario,
        script: JMeterScript
    ) -> None:
        """执行JMeter测试"""
        try:
            work_dir = tempfile.mkdtemp(prefix="jmeter_")
            
            jmx_path = os.path.join(work_dir, f"script_{script.id}.jmx")
            with open(jmx_path, "w", encoding="utf-8") as f:
                modified_jmx = self._modify_jmx(script.file_content, scenario)
                f.write(modified_jmx)
            
            result_path = os.path.join(work_dir, f"result_{execution.id}.jtl")
            log_path = os.path.join(work_dir, f"jmeter_{execution.id}.log")
            
            cmd = [
                self.JMETER_COMMAND,
                "-n",
                "-t", jmx_path,
                "-l", result_path,
                "-j", log_path
            ]
            
            if scenario.jmeter_properties:
                for key, value in scenario.jmeter_properties.items():
                    cmd.extend(["-J", f"{key}={value}"])
            
            if scenario.jmeter_args:
                cmd.extend(scenario.jmeter_args.split())
            
            execution.jmeter_log_path = log_path
            self.db.commit()
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            execution.jmeter_process_id = str(process.pid)
            self.db.commit()
            
            stdout, stderr = await process.communicate()
            
            execution.end_time = datetime.utcnow()
            execution.actual_duration = int(
                (execution.end_time - execution.start_time).total_seconds()
            )
            execution.result_file_path = result_path
            
            if process.returncode == 0:
                self._parse_jtl_result(execution, result_path)
                execution.status = PerformanceTestStatus.COMPLETED.value
            else:
                execution.status = PerformanceTestStatus.FAILED.value
                logger.error(f"JMeter执行失败: {stderr.decode()}")
            
            self.db.commit()
            
            self._generate_report(execution, work_dir)
            
            self._evaluate_pass_criteria(execution, scenario)
            
        except Exception as e:
            execution.status = PerformanceTestStatus.FAILED.value
            execution.end_time = datetime.utcnow()
            self.db.commit()
            logger.error(f"性能测试执行异常: {str(e)}")
    
    def _modify_jmx(self, content: str, scenario: PerformanceScenario) -> str:
        """修改JMX配置"""
        try:
            root = ET.fromstring(content)
            
            thread_group_config = scenario.thread_group_config or []
            
            for tg in root.findall(".//ThreadGroup"):
                tg_name = tg.get("name", "")
                matched_config = None
                for config in thread_group_config:
                    if config.get("name") == tg_name:
                        matched_config = config
                        break
                
                if not matched_config and thread_group_config:
                    matched_config = thread_group_config[0]
                
                if matched_config:
                    for prop in tg.findall("stringProp"):
                        name = prop.get("name", "")
                        if name == "ThreadGroup.num_threads":
                            prop.text = str(matched_config.get("num_threads", scenario.concurrent_users))
                        elif name == "ThreadGroup.ramp_time":
                            prop.text = str(matched_config.get("ramp_time", scenario.ramp_up_period))
                        elif name == "LoopController.loops":
                            loops = matched_config.get("loops", -1)
                            prop.text = str(loops)
                    
                    for bool_prop in tg.findall("boolProp"):
                        name = bool_prop.get("name", "")
                        if name == "ThreadGroup.scheduler":
                            bool_prop.text = "true"
                    
                    for string_prop in tg.findall("stringProp"):
                        name = string_prop.get("name", "")
                        if name == "ThreadGroup.duration":
                            string_prop.text = str(matched_config.get("duration", scenario.duration))
            
            return ET.tostring(root, encoding="unicode")
            
        except Exception as e:
            logger.error(f"修改JMX失败: {str(e)}")
            return content
    
    def _parse_jtl_result(self, execution: PerformanceTestExecution, result_path: str) -> None:
        """解析JTL结果文件"""
        try:
            if not os.path.exists(result_path):
                return
            
            with open(result_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            lines = content.strip().split("\n")
            if not lines:
                return
            
            header = lines[0].split(",")
            data_lines = lines[1:]
            
            total_samples = len(data_lines)
            success_count = 0
            error_count = 0
            
            rt_values = []
            timestamps = []
            
            for line in data_lines:
                fields = line.split(",")
                if len(fields) < 10:
                    continue
                
                success = fields[len(fields) - 2] if len(fields) >= 2 else "true"
                if success.lower() == "true":
                    success_count += 1
                else:
                    error_count += 1
                
                elapsed = fields[1] if len(fields) > 1 else "0"
                try:
                    rt_values.append(float(elapsed))
                except ValueError:
                    pass
                
                timestamp = fields[0] if len(fields) > 0 else ""
                try:
                    timestamps.append(int(timestamp))
                except ValueError:
                    pass
            
            execution.total_samples = total_samples
            execution.success_samples = success_count
            execution.error_samples = error_count
            execution.error_rate = (error_count / total_samples * 100) if total_samples > 0 else 0
            
            if rt_values:
                execution.avg_rt = sum(rt_values) / len(rt_values)
                execution.max_rt = max(rt_values)
                execution.min_rt = min(rt_values)
                
                sorted_rt = sorted(rt_values)
                n = len(sorted_rt)
                execution.p90_rt = sorted_rt[int(n * 0.9)] if n > 0 else 0
                execution.p95_rt = sorted_rt[int(n * 0.95)] if n > 0 else 0
                execution.p99_rt = sorted_rt[int(n * 0.99)] if n > 0 else 0
            
            if timestamps:
                min_ts = min(timestamps)
                max_ts = max(timestamps)
                duration_ms = max_ts - min_ts
                if duration_ms > 0:
                    execution.avg_tps = (total_samples / (duration_ms / 1000)) if duration_ms > 0 else 0
                    execution.max_tps = execution.avg_tps
            
            logger.info(f"解析JTL完成: total={total_samples}, errors={error_count}")
            
        except Exception as e:
            logger.error(f"解析JTL失败: {str(e)}")
    
    def _generate_report(self, execution: PerformanceTestExecution, work_dir: str) -> None:
        """生成HTML报告"""
        try:
            if not execution.result_file_path or not os.path.exists(execution.result_file_path):
                return
            
            report_dir = os.path.join(work_dir, f"report_{execution.id}")
            
            cmd = [
                self.JMETER_COMMAND,
                "-g",
                execution.result_file_path,
                "-o",
                report_dir
            ]
            
            result = subprocess.run(cmd, capture_output=True, timeout=60)
            
            if result.returncode == 0:
                execution.report_path = report_dir
                self.db.commit()
                logger.info(f"生成HTML报告成功: {report_dir}")
            else:
                logger.error(f"生成报告失败: {result.stderr.decode()}")
            
        except Exception as e:
            logger.error(f"生成报告异常: {str(e)}")
    
    def _evaluate_pass_criteria(
        self,
        execution: PerformanceTestExecution,
        scenario: PerformanceScenario
    ) -> None:
        """评估是否达标"""
        pass_reasons = []
        fail_reasons = []
        
        if scenario.target_tps and execution.avg_tps:
            if execution.avg_tps >= scenario.target_tps:
                pass_reasons.append(f"TPS达标: {execution.avg_tps:.2f} >= {scenario.target_tps}")
            else:
                fail_reasons.append(f"TPS未达标: {execution.avg_tps:.2f} < {scenario.target_tps}")
        
        if scenario.target_rt and execution.avg_rt:
            if execution.avg_rt <= scenario.target_rt:
                pass_reasons.append(f"响应时间达标: {execution.avg_rt:.2f}ms <= {scenario.target_rt}ms")
            else:
                fail_reasons.append(f"响应时间未达标: {execution.avg_rt:.2f}ms > {scenario.target_rt}ms")
        
        if scenario.error_rate_threshold and execution.error_rate:
            if execution.error_rate <= scenario.error_rate_threshold:
                pass_reasons.append(f"错误率达标: {execution.error_rate:.2f}% <= {scenario.error_rate_threshold}%")
            else:
                fail_reasons.append(f"错误率未达标: {execution.error_rate:.2f}% > {scenario.error_rate_threshold}%")
        
        execution.passed = len(fail_reasons) == 0
        execution.pass_reason = "\n".join(pass_reasons + fail_reasons) if (pass_reasons or fail_reasons) else "未配置达标标准"
        
        self.db.commit()
    
    def stop_execution(self, execution_id: int) -> PerformanceTestExecution:
        """停止测试执行"""
        execution = self.db.query(PerformanceTestExecution).filter(
            PerformanceTestExecution.id == execution_id
        ).first()
        
        if not execution:
            raise ValueError("执行不存在")
        
        if execution.status != PerformanceTestStatus.RUNNING.value:
            raise ValueError("执行未在运行中")
        
        if execution.jmeter_process_id:
            try:
                subprocess.run(["kill", "-9", execution.jmeter_process_id], timeout=5)
            except Exception as e:
                logger.error(f"停止JMeter进程失败: {str(e)}")
        
        execution.status = PerformanceTestStatus.STOPPED.value
        execution.end_time = datetime.utcnow()
        
        self.db.commit()
        self.db.refresh(execution)
        
        return execution
    
    def get_execution_metrics(
        self,
        execution_id: int,
        limit: int = 100
    ) -> List[PerformanceMetric]:
        """获取执行指标"""
        metrics = self.db.query(PerformanceMetric).filter(
            PerformanceMetric.execution_id == execution_id
        ).order_by(PerformanceMetric.timestamp.desc()).limit(limit).all()
        
        return metrics


class GrafanaIntegrationService:
    """Grafana集成服务"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create_dashboard(
        self,
        project_id: int,
        name: str,
        grafana_host: str,
        api_key: str = None,
        dashboard_uid: str = None,
        created_by: int = None
    ) -> GrafanaDashboard:
        """创建Grafana仪表盘配置"""
        dashboard = GrafanaDashboard(
            project_id=project_id,
            name=name,
            grafana_host=grafana_host,
            api_key=api_key,
            dashboard_uid=dashboard_uid,
            created_by=created_by
        )
        
        if dashboard_uid:
            dashboard.dashboard_url = f"{grafana_host}/d/{dashboard_uid}"
        
        self.db.add(dashboard)
        self.db.commit()
        self.db.refresh(dashboard)
        
        return dashboard
    
    def get_embed_url(self, dashboard_id: int) -> str:
        """获取嵌入URL"""
        dashboard = self.db.query(GrafanaDashboard).filter(
            GrafanaDashboard.id == dashboard_id
        ).first()
        
        if not dashboard:
            return ""
        
        if dashboard.dashboard_url:
            return f"{dashboard.dashboard_url}?theme=light&kiosk"
        
        return ""
    
    def sync_dashboard_config(self, dashboard_id: int) -> Dict[str, Any]:
        """同步仪表盘配置"""
        dashboard = self.db.query(GrafanaDashboard).filter(
            GrafanaDashboard.id == dashboard_id
        ).first()
        
        if not dashboard:
            return {"success": False, "message": "仪表盘不存在"}
        
        import httpx
        
        try:
            headers = {}
            if dashboard.api_key:
                headers["Authorization"] = f"Bearer {dashboard.api_key}"
            
            url = f"{dashboard.grafana_host}/api/dashboards/uid/{dashboard.dashboard_uid}"
            
            async def fetch():
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(url, headers=headers)
                    return response.json()
            
            result = asyncio.run(fetch())
            
            if "dashboard" in result:
                dashboard.panels_config = result["dashboard"].get("panels", [])
                self.db.commit()
                
                return {"success": True, "message": "同步成功"}
            
            return {"success": False, "message": "获取配置失败"}
            
        except Exception as e:
            return {"success": False, "message": str(e)}


class PerformanceReportService:
    """性能报告服务"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def generate_report(
        self,
        execution_id: int,
        title: str = None,
        created_by: int = None
    ) -> PerformanceReport:
        """生成性能报告"""
        execution = self.db.query(PerformanceTestExecution).filter(
            PerformanceTestExecution.id == execution_id
        ).first()
        
        if not execution:
            raise ValueError("执行记录不存在")
        
        metrics_summary = {
            "avg_tps": execution.avg_tps,
            "max_tps": execution.max_tps,
            "avg_rt": execution.avg_rt,
            "min_rt": execution.min_rt,
            "max_rt": execution.max_rt,
            "p90_rt": execution.p90_rt,
            "p95_rt": execution.p95_rt,
            "p99_rt": execution.p99_rt,
            "error_rate": execution.error_rate,
            "total_samples": execution.total_samples,
            "success_samples": execution.success_samples,
            "error_samples": execution.error_samples
        }
        
        charts_data = self._generate_charts_data(execution)
        
        conclusion = self._generate_conclusion(execution)
        recommendations = self._generate_recommendations(execution)
        
        report = PerformanceReport(
            project_id=execution.project_id,
            execution_id=execution_id,
            title=title or f"性能测试报告 - {execution.name}",
            metrics_summary=metrics_summary,
            charts_data=charts_data,
            conclusion=conclusion,
            recommendations=recommendations,
            created_by=created_by
        )
        
        self.db.add(report)
        self.db.commit()
        self.db.refresh(report)
        
        return report
    
    def _generate_charts_data(self, execution: PerformanceTestExecution) -> Dict[str, Any]:
        """生成图表数据"""
        metrics = self.db.query(PerformanceMetric).filter(
            PerformanceMetric.execution_id == execution.id
        ).order_by(PerformanceMetric.timestamp).all()
        
        tps_series = []
        rt_series = []
        error_series = []
        
        for m in metrics:
            timestamp = m.timestamp.isoformat() if m.timestamp else ""
            if m.tps:
                tps_series.append({"time": timestamp, "value": m.tps})
            if m.avg_rt:
                rt_series.append({"time": timestamp, "value": m.avg_rt})
            if m.error_rate:
                error_series.append({"time": timestamp, "value": m.error_rate})
        
        return {
            "tps": {"name": "TPS趋势", "data": tps_series},
            "rt": {"name": "响应时间趋势", "data": rt_series},
            "error": {"name": "错误率趋势", "data": error_series}
        }
    
    def _generate_conclusion(self, execution: PerformanceTestExecution) -> str:
        """生成测试结论"""
        if execution.passed:
            conclusion = f"""
## 测试结论

本次性能测试**通过**。

### 指标概览
- 平均TPS: {execution.avg_tps:.2f} req/s
- 平均响应时间: {execution.avg_rt:.2f} ms
- P95响应时间: {execution.p95_rt:.2f} ms
- 错误率: {execution.error_rate:.2f}%

### 达标情况
{execution.pass_reason or '所有指标均达标'}
"""
        else:
            conclusion = f"""
## 测试结论

本次性能测试**未通过**。

### 指标概览
- 平均TPS: {execution.avg_tps:.2f} req/s
- 平均响应时间: {execution.avg_rt:.2f} ms
- P95响应时间: {execution.p95_rt:.2f} ms
- 错误率: {execution.error_rate:.2f}%

### 未达标原因
{execution.pass_reason or '请检查未达标指标'}
"""
        
        return conclusion
    
    def _generate_recommendations(self, execution: PerformanceTestExecution) -> List[str]:
        """生成优化建议"""
        recommendations = []
        
        if execution.avg_rt and execution.avg_rt > 1000:
            recommendations.append({
                "category": "响应时间",
                "priority": "high",
                "description": "平均响应时间超过1秒，建议优化数据库查询、接口性能或增加缓存"
            })
        
        if execution.error_rate and execution.error_rate > 1:
            recommendations.append({
                "category": "稳定性",
                "priority": "high",
                "description": f"错误率为{execution.error_rate:.2f}%，建议检查服务稳定性、超时配置或异常处理"
            })
        
        if execution.p99_rt and execution.p99_rt > execution.avg_rt * 3:
            recommendations.append({
                "category": "长尾响应",
                "priority": "medium",
                "description": "P99响应时间明显高于平均值，存在长尾延迟问题，建议分析慢请求日志"
            })
        
        if not recommendations:
            recommendations.append({
                "category": "整体",
                "priority": "info",
                "description": "系统性能良好，建议持续监控并建立性能基线"
            })
        
        return recommendations


SCENARIO_STATUS_OPTIONS = [
    {"value": "draft", "label": "草稿"},
    {"value": "ready", "label": "就绪"},
    {"value": "running", "label": "运行中"},
    {"value": "completed", "label": "已完成"},
    {"value": "failed", "label": "失败"},
    {"value": "stopped", "label": "已停止"}
]

SCRIPT_STATUS_OPTIONS = [
    {"value": "draft", "label": "草稿"},
    {"value": "validated", "label": "已验证"},
    {"value": "error", "label": "错误"}
]