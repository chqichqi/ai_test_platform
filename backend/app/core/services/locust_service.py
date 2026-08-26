"""
Locust性能测试服务
支持从API测试用例生成locustfile、执行Locust压测、实时指标采集
"""
import os
import subprocess
import tempfile
import json
import signal
import csv
from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session

from app.core.models.performance_locust import (
    LocustScript, LocustExecution, LocustMetric, LocustScriptStatus, LocustExecutionStatus
)
from app.core.models.api_test import ApiTestCase
from app.core.logger import logger


class LocustService:
    """Locust压测服务"""

    def __init__(self, db: Session):
        self.db = db
        self.running_processes: Dict[int, subprocess.Popen] = {}

    def create_script_from_api_cases(
        self,
        project_id: int,
        name: str,
        case_ids: List[int],
        host: str,
        description: str = None,
        created_by: str = None
    ) -> LocustScript:
        """从API测试用例生成locustfile.py并创建脚本记录"""
        cases = self.db.query(ApiTestCase).filter(
            ApiTestCase.id.in_(case_ids),
            ApiTestCase.status.in_(["approved", "active"])
        ).all()

        if not cases:
            raise ValueError("没有找到已审批的API测试用例")

        file_content = self._generate_locustfile(cases, host)

        script = LocustScript(
            project_id=project_id,
            name=name,
            description=description,
            file_content=file_content,
            file_size=len(file_content),
            host=host,
            source_case_ids=case_ids,
            status=LocustScriptStatus.ACTIVE.value,
            created_by=created_by,
        )

        self.db.add(script)
        self.db.commit()
        self.db.refresh(script)

        logger.info(f"创建Locust脚本: {script.name}, 包含 {len(cases)} 个API用例")
        return script

    def _generate_locustfile(self, cases: List[ApiTestCase], host: str) -> str:
        """根据API测试用例生成locustfile.py"""
        # 权重映射
        weight_map = {"P0": 15, "P1": 10, "P2": 5, "P3": 2}

        task_methods = []
        for i, case in enumerate(cases):
            method = case.method or "GET"
            path = case.path or "/"
            weight = weight_map.get(case.priority, 5)

            # 转义字符串
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
        body = {body_str}

        with self.client.request(
            "{method}",
            "{path}",
            headers=headers,
            params=params,
            json=body if "{method_lower}" in ("post", "put", "patch") else None,
            catch_response=True,
            name="{case.name}"
        ) as response:
            expected_status = {case.expected_status or 200}
            if response.status_code != expected_status:
                response.failure(
                    f"Expected status {{expected_status}}, got {{response.status_code}}"
                )
            elif response.elapsed.total_seconds() > 5.0:
                response.failure(
                    f"Response too slow: {{response.elapsed.total_seconds():.2f}}s"
                )
            else:
                response.success()
''')

        locustfile = f'''"""
Auto-generated locustfile from API test cases
Host: {host}
Cases count: {len(cases)}
Generated at: {datetime.utcnow().isoformat()}
"""
from locust import HttpUser, task, between


class ApiTestUser(HttpUser):
    """API测试用户 - 模拟真实API调用"""
    wait_time = between(1, 3)
    host = "{host}"
{''.join(task_methods)}
'''

        return locustfile

    def start_execution(
        self,
        execution_id: int = None,
        script_id: int = None,
        script_path: str = None,
        host: str = None,
        num_users: int = 100,
        spawn_rate: int = 10,
        run_time: int = 60,
        step_config: dict = None,
        project_id: int = None,
        name: str = None,
        created_by: str = None
    ) -> LocustExecution:
        """启动Locust执行"""
        # 获取脚本
        if script_id:
            script = self.db.query(LocustScript).filter(LocustScript.id == script_id).first()
            if not script:
                raise ValueError(f"脚本ID {script_id} 不存在")
            file_content = script.file_content
            host = host or script.host
        elif script_path:
            with open(script_path, 'r', encoding='utf-8') as f:
                file_content = f.read()
        else:
            raise ValueError("必须提供 script_id 或 script_path")

        if not file_content:
            raise ValueError("脚本内容为空")

        # 创建执行记录
        if not execution_id:
            execution = LocustExecution(
                project_id=project_id or 0,
                script_id=script_id,
                name=name or f"Locust执行 {datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
                status=LocustExecutionStatus.PENDING.value,
                host=host,
                num_users=num_users,
                spawn_rate=spawn_rate,
                run_time=run_time,
                created_by=created_by,
            )
            if step_config:
                execution.step_enabled = step_config.get("enabled", False)
                execution.step_count = step_config.get("step_count", 5)
                execution.step_duration = step_config.get("step_duration", 60)
                execution.step_thread_increment = step_config.get("step_thread_increment", 10)

            self.db.add(execution)
            self.db.commit()
            self.db.refresh(execution)
            execution_id = execution.id

        # 写入临时文件
        result_dir = tempfile.mkdtemp(prefix="locust_")
        locustfile_path = os.path.join(result_dir, "locustfile.py")

        # 如果启用了梯度，在locustfile末尾追加StepLoadShape
        if step_config and step_config.get("enabled"):
            file_content += self._generate_step_shape_class(step_config)

        with open(locustfile_path, 'w', encoding='utf-8') as f:
            f.write(file_content)

        logger.info(f"Locust脚本已写入: {locustfile_path}")

        # 构建locust命令
        cmd = [
            "locust",
            "-f", locustfile_path,
            "--host", host or "http://localhost:8000",
            "--headless",
            "-u", str(num_users),
            "-r", str(spawn_rate),
            "-t", f"{run_time}s",
            "--csv", os.path.join(result_dir, "stats"),
            "--html", os.path.join(result_dir, "report.html"),
            "--json",  # 输出JSON格式
        ]

        logger.info(f"启动Locust: {' '.join(cmd)}")

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=result_dir,
            )

            # 更新执行记录
            execution = self.db.query(LocustExecution).filter(LocustExecution.id == execution_id).first()
            execution.status = LocustExecutionStatus.RUNNING.value
            execution.locust_process_id = process.pid
            execution.result_dir = result_dir
            execution.start_time = datetime.utcnow()
            self.db.commit()

            self.running_processes[execution_id] = process

            logger.info(f"Locust已启动: PID={process.pid}, execution_id={execution_id}")
            return execution

        except FileNotFoundError:
            raise RuntimeError("locust 未安装，请执行: pip install locust")
        except Exception as e:
            logger.error(f"启动Locust失败: {e}")
            raise

    def stop_execution(self, execution_id: int):
        """停止Locust执行"""
        execution = self.db.query(LocustExecution).filter(LocustExecution.id == execution_id).first()
        if not execution:
            raise ValueError(f"执行记录 {execution_id} 不存在")

        process = self.running_processes.get(execution_id)
        if process:
            try:
                process.send_signal(signal.SIGTERM)
                process.wait(timeout=30)
            except Exception as e:
                logger.warning(f"终止Locust进程失败: {e}")
                try:
                    process.kill()
                except Exception:
                    pass
            finally:
                self.running_processes.pop(execution_id, None)

        execution.status = LocustExecutionStatus.STOPPED.value
        execution.end_time = datetime.utcnow()
        self.db.commit()

        # 解析结果
        self._parse_and_store_results(execution_id)

        logger.info(f"Locust执行已停止: execution_id={execution_id}")

    def get_metrics(self, execution_id: int) -> dict:
        """获取执行实时指标"""
        execution = self.db.query(LocustExecution).filter(LocustExecution.id == execution_id).first()
        if not execution:
            return {"error": "执行记录不存在"}

        if execution.status == LocustExecutionStatus.COMPLETED.value:
            return {
                "status": "completed",
                "metrics": self._get_stored_metrics(execution_id),
                "summary": {
                    "avg_tps": execution.avg_tps,
                    "max_tps": execution.max_tps,
                    "avg_rt": execution.avg_rt,
                    "p90_rt": execution.p90_rt,
                    "p95_rt": execution.p95_rt,
                    "p99_rt": execution.p99_rt,
                    "error_rate": execution.error_rate,
                    "total_samples": execution.total_samples,
                }
            }

        # 从CSV文件读取最新指标
        metrics = self._read_latest_csv_metrics(execution)
        return {
            "status": execution.status,
            "metrics": metrics,
            "progress": {
                "elapsed": (datetime.utcnow() - execution.start_time).total_seconds() if execution.start_time else 0,
                "total": execution.run_time,
            }
        }

    def _read_latest_csv_metrics(self, execution: LocustExecution) -> List[dict]:
        """从locust stats CSV读取最新指标"""
        stats_csv = os.path.join(execution.result_dir, "stats_stats_history.csv") if execution.result_dir else None

        if not stats_csv or not os.path.exists(stats_csv):
            # 尝试stats.csv
            if execution.result_dir:
                alt_csv = os.path.join(execution.result_dir, "stats_stats.csv")
                if os.path.exists(alt_csv):
                    stats_csv = alt_csv
                else:
                    return []
            else:
                return []

        try:
            metrics = []
            with open(stats_csv, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    metrics.append({
                        "timestamp": row.get("Timestamp", ""),
                        "user_count": int(float(row.get("User Count", 0))),
                        "tps": float(row.get("Total Requests/s", 0) or row.get("Requests/s", 0) or 0),
                        "avg_rt": float(row.get("Average Response Time", 0) or 0),
                        "min_rt": float(row.get("Min Response Time", 0) or 0),
                        "max_rt": float(row.get("Max Response Time", 0) or 0),
                        "fail_ratio": float(row.get("Failure Count", 0) or 0) / max(
                            float(row.get("Request Count", 0) or 0), 1
                        ),
                        "samples_count": int(float(row.get("Request Count", 0) or 0)),
                    })
            return metrics[-100:]  # 返回最近100条
        except Exception as e:
            logger.warning(f"解析Locust CSV失败: {e}")
            return []

    def _parse_and_store_results(self, execution_id: int):
        """解析locust结果文件并存储到数据库"""
        execution = self.db.query(LocustExecution).filter(LocustExecution.id == execution_id).first()
        if not execution or not execution.result_dir:
            return

        stats_path = os.path.join(execution.result_dir, "stats_stats.csv")
        if not os.path.exists(stats_path):
            logger.warning(f"Locust stats文件不存在: {stats_path}")
            return

        try:
            with open(stats_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            # 找Aggregated行
            aggregated = None
            for row in rows:
                if row.get("Type") == "Aggregated" or row.get("Name") == "Aggregated":
                    aggregated = row
                    break

            if aggregated:
                execution.total_samples = int(float(aggregated.get("Request Count", 0)))
                execution.success_samples = int(float(aggregated.get("Request Count", 0))) - int(float(aggregated.get("Failure Count", 0)))
                execution.error_samples = int(float(aggregated.get("Failure Count", 0)))
                execution.avg_rt = float(aggregated.get("Average Response Time", 0))
                execution.max_rt = float(aggregated.get("Max Response Time", 0))
                execution.p50_rt = float(aggregated.get("50%", 0) or 0)
                execution.p90_rt = float(aggregated.get("90%", 0) or 0)
                execution.p95_rt = float(aggregated.get("95%", 0) or 0)
                execution.p99_rt = float(aggregated.get("99%", 0) or 0)

                # 计算TPS
                if execution.run_time and execution.run_time > 0:
                    execution.avg_tps = execution.total_samples / execution.run_time

                # 计算错误率
                if execution.total_samples > 0:
                    execution.error_rate = round(execution.error_samples / execution.total_samples * 100, 2)

            # 从history计算最大TPS
            history_path = os.path.join(execution.result_dir, "stats_stats_history.csv")
            if os.path.exists(history_path):
                max_tps = 0
                with open(history_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        tps = float(row.get("Total Requests/s", 0) or row.get("Requests/s", 0) or 0)
                        if tps > max_tps:
                            max_tps = tps
                execution.max_tps = max_tps

            execution.status = LocustExecutionStatus.COMPLETED.value
            execution.end_time = datetime.utcnow()
            if execution.start_time:
                execution.actual_duration = int((execution.end_time - execution.start_time).total_seconds())

            execution.summary_metrics = {
                "total_samples": execution.total_samples,
                "success_samples": execution.success_samples,
                "error_samples": execution.error_samples,
                "avg_tps": execution.avg_tps,
                "max_tps": execution.max_tps,
                "avg_rt": execution.avg_rt,
                "p50_rt": execution.p50_rt,
                "p90_rt": execution.p90_rt,
                "p95_rt": execution.p95_rt,
                "p99_rt": execution.p99_rt,
                "error_rate": execution.error_rate,
            }

            self.db.commit()
            logger.info(f"Locust结果解析完成: execution_id={execution_id}, TPS={execution.avg_tps:.1f}, RT={execution.avg_rt:.1f}ms")

        except Exception as e:
            logger.error(f"解析Locust结果失败: {e}")

    def _get_stored_metrics(self, execution_id: int) -> List[dict]:
        """获取已存储的指标"""
        metrics = self.db.query(LocustMetric).filter(
            LocustMetric.execution_id == execution_id
        ).order_by(LocustMetric.elapsed_seconds).all()

        return [
            {
                "timestamp": m.timestamp.isoformat() if m.timestamp else "",
                "elapsed": m.elapsed_seconds,
                "user_count": m.user_count,
                "tps": m.tps,
                "avg_rt": m.avg_rt,
                "fail_ratio": m.fail_ratio,
            }
            for m in metrics
        ]

    def _generate_step_shape_class(self, step_config: dict) -> str:
        """生成Locust的StepLoadShape类"""
        return f'''

class StepLoadShape:
    """梯度加压形状"""
    step_count = {step_config.get('step_count', 5)}
    step_duration = {step_config.get('step_duration', 60)}
    step_thread_increment = {step_config.get('step_thread_increment', 10)}
    max_users = {step_config.get('max_users', step_config.get('step_count', 5) * step_config.get('step_thread_increment', 10))}

    def tick(self):
        from locust import LoadTestShape
        run_time = self.get_run_time()
        step_number = int(run_time / self.step_duration) + 1
        if step_number > self.step_count:
            return None
        user_count = step_number * self.step_thread_increment
        if user_count > self.max_users:
            user_count = self.max_users
        return (min(user_count, self.max_users), self.step_thread_increment)
'''

    def list_scripts(self, project_id: int) -> List[LocustScript]:
        """列出项目的Locust脚本"""
        return self.db.query(LocustScript).filter(
            LocustScript.project_id == project_id
        ).order_by(LocustScript.created_at.desc()).all()

    def list_executions(self, project_id: int = None, script_id: int = None) -> List[LocustExecution]:
        """列出执行记录"""
        query = self.db.query(LocustExecution)
        if project_id:
            query = query.filter(LocustExecution.project_id == project_id)
        if script_id:
            query = query.filter(LocustExecution.script_id == script_id)
        return query.order_by(LocustExecution.created_at.desc()).all()

    def get_approved_api_cases(
        self, project_id: int, page: int = 1, page_size: int = 50,
        search: str = None, method: str = None, priority: str = None
    ) -> tuple:
        """获取已审批的API测试用例（用于性能测试选择）"""
        # 兼容新旧状态系统: approved(新审批系统), active(旧系统)
        query = self.db.query(ApiTestCase).filter(
            ApiTestCase.project_id == project_id,
            ApiTestCase.status.in_(["approved", "active"])
        )
        if search:
            query = query.filter(
                ApiTestCase.name.ilike(f"%{search}%") |
                ApiTestCase.path.ilike(f"%{search}%")
            )
        if method:
            query = query.filter(ApiTestCase.method == method.upper())
        if priority:
            query = query.filter(ApiTestCase.priority == priority)

        total = query.count()
        cases = query.order_by(ApiTestCase.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
        return cases, total
