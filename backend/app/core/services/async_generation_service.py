# -*- coding: utf-8 -*-
"""
异步生成服务 - 后台执行测试用例生成
"""

import asyncio
import time
from datetime import datetime
from typing import Dict, Any, Optional

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.models.generation_task import GenerationTask, TaskStatus, TaskType
from app.core.services.version_generator import VersionGeneratorService as VersionGenerator
from app.core.simple_logger import logger  # 使用loguru确保日志写入文件


# 导入智能批次策略
from app.core.services.smart_batch_strategy import SmartBatchStrategy

async def run_generation_task(task_id: int):
    """后台执行生成任务
    
    Args:
        task_id: 任务ID
    """
    db = SessionLocal()
    
    try:
        task = db.query(GenerationTask).filter(GenerationTask.id == task_id).first()
        if not task:
            logger.error(f"任务不存在: {task_id}")
            return
        
        logger.info(f"开始执行任务 {task_id}, 类型: {task.task_type}")
        
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.utcnow()
        task.current_step = "正在准备生成环境..."
        db.commit()
        
        input_data = task.input_data or {}
        project_id = task.project_id
        version_id = task.version_id
        
        project_name = input_data.get("project_name", "")
        version_number = input_data.get("version_number", "")
        requirement_doc_content = input_data.get("requirement_doc_content", "")
        skill_id = input_data.get("skill_id")
        
        generator = VersionGenerator(db)
        
        task.current_step = "正在分析需求文档..."
        db.commit()
        
        modules = generator._extract_modules_from_requirement(requirement_doc_content)
        
# 智能自适应分批策略
        # 获取LLM配置的max_tokens
        from app.core.models.llm_config import LLMConfig
        llm_config = db.query(LLMConfig).filter(LLMConfig.is_active == True).first()
        config_max_tokens = llm_config.max_tokens if llm_config else 30000
        max_tokens_limit = min(config_max_tokens, 50000)
        
        # 使用智能批次策略（动态调整）
        smart_strategy = SmartBatchStrategy(max_tokens_limit=max_tokens_limit)
        batch_count, modules_per_batch, estimated_cases_per_batch = smart_strategy.calculate_initial_batch_params(modules)
        
        batch_size = modules_per_batch
        task.total_batches = batch_count
        task.current_step = f"文档分析完成，识别到{len(modules)}个模块，智能自适应策略：分{batch_count}批（动态调整）"
        logger.info(f"任务{task_id}: 智能自适应策略启动，{len(modules)}模块 → {batch_count}批，每批{modules_per_batch}模块，max_tokens={max_tokens_limit}")
        
        db.commit()
        
        if len(modules) > 0:
            
            all_test_cases = []
            failed_batches = []  # 记录失败批次，用于重试
            
            batch_count = task.total_batches
            logger.info(f"任务{task_id}: 执行智能批次生成，初始{batch_count}批（可动态调整）")
        
            for batch_idx in range(batch_count):
                # === 取消检查：每批次开始前检查任务状态 ===
                task = db.query(GenerationTask).filter(GenerationTask.id == task_id).first()
                if task and task.status == TaskStatus.CANCELLED:
                    logger.info(f"任务{task_id}已被用户取消，停止后续批次生成")
                    break
                
                start_idx = batch_idx * batch_size
                end_idx = min(start_idx + batch_size, len(modules))
                current_modules = modules[start_idx:end_idx]
                
                task.current_batch = batch_idx + 1
                # 使用更高的初始进度，减少进度更新通信开销
                task.progress = int((batch_idx / batch_count) * 60)  # 批次处理占60%
                task.current_step = f"正在生成第{batch_idx+1}/{batch_count}批测试用例（模块: {', '.join(current_modules[:3])}...）"
                db.commit()
                
                logger.info(f"任务{task_id}: 生成第{batch_idx+1}/{batch_count}批，模块数: {len(current_modules)}")
                
                batch_modules_list = generator._format_modules_list(current_modules)
                # 预估用例数量
                batch_estimated_cases = len(current_modules) * 4
                
                # 使用智能策略计算max_tokens（动态调整）
                batch_max_tokens = smart_strategy.calculate_batch_max_tokens(len(current_modules))
                
                logger.info(f"任务{task_id}: 第{batch_idx+1}批 {len(current_modules)}模块，预估{batch_estimated_cases}条用例，max_tokens={batch_max_tokens}（策略系数={smart_strategy.current_batch_size_multiplier:.2f}）")
                
                batch_content = generator._extract_batch_content(requirement_doc_content, current_modules, 20000)
                
                skill_content = None
                if skill_id:
                    from app.core.models.skill import TestSkill
                    skill = db.query(TestSkill).filter(TestSkill.id == skill_id).first()
                    if skill:
                        skill_content = skill.content
                
                # 使用统一的提示词构建方法提升效率
                batch_system_prompt, batch_user_prompt = generator._build_prompts_from_skill(
                    skill_content, project_name, version_number, batch_content, current_modules
                )
                
                logger.info(f"任务{task_id}: 开始第{batch_idx+1}/{batch_count}批LLM调用...")
                
                # 更新状态：显示LLM调用进度
                task.current_step = f"第{batch_idx+1}/{batch_count}批：正在调用LLM API..."
                db.commit()
                
                llm_start_time = time.time()
                
                try:
                    batch_response = await generator.llm_service.async_call_llm(
                        prompt=batch_user_prompt,
                        system_prompt=batch_system_prompt,
                        temperature=0.3,
                        max_tokens=batch_max_tokens  # 使用优化后的max_tokens
                    )
                    
                    llm_elapsed = time.time() - llm_start_time
                    logger.info(f"任务{task_id}: 第{batch_idx+1}批LLM响应耗时{llm_elapsed:.1f}秒")
                    
                    # 更新状态：LLM响应已接收
                    task.current_step = f"第{batch_idx+1}/{batch_count}批：LLM响应已接收（耗时{llm_elapsed:.1f}s），正在解析JSON..."
                    db.commit()
                    
                    if batch_response:
                        # 先尝试解析完整JSON
                        batch_result = generator._parse_llm_response(batch_response)
                        
                        if batch_result and batch_result.get("test_cases"):
                            generated_count = len(batch_result.get("test_cases"))
                            all_test_cases.extend(batch_result.get("test_cases"))
                            task.generated_count = len(all_test_cases)
                            
                            # 智能截断检测：动态调整策略
                            adjustment_result = smart_strategy.adjust_after_truncation(
                                batch_idx=batch_idx,
                                actual_cases=generated_count,
                                estimated_cases=batch_estimated_cases
                            )
                            
                            # 更新进度
                            task.progress = 60 + int((len(all_test_cases) / (batch_estimated_cases * batch_count)) * 25)
                            
                            if adjustment_result["is_truncated"]:
                                # 检测到截断：记录失败批次，后续重试
                                logger.warning(f"任务{task_id}: 第{batch_idx+1}批截断检测！生成{generated_count}条（预估{batch_estimated_cases}条），成功率{adjustment_result['success_rate']:.1%}")
                                logger.warning(f"任务{task_id}: 策略自动调整：批次系数{adjustment_result['current_multiplier']:.2f} → {adjustment_result['new_multiplier']:.2f}")
                                task.current_step = f"第{batch_idx+1}批截断，自动调整策略（系数降至{adjustment_result['new_multiplier']:.2f}），继续..."
                                failed_batches.append({
                                    "batch_idx": batch_idx,
                                    "modules": current_modules,
                                    "generated_count": generated_count
                                })
                            else:
                                # 成功：继续下一批
                                task.current_step = f"第{batch_idx+1}/{batch_count}批：已生成{len(all_test_cases)}条用例，继续..."
                                logger.info(f"任务{task_id}: 第{batch_idx+1}批生成{generated_count}条用例（成功率{adjustment_result['success_rate']:.1%}），策略系数={smart_strategy.current_batch_size_multiplier:.2f}")
                            
                            db.commit()
                        else:
                            # JSON解析失败：记录失败批次
                            logger.warning(f"任务{task_id}: 第{batch_idx+1}批JSON解析失败，尝试提取部分用例...")
                            partial_cases = generator._extract_partial_cases_from_response(batch_response)
                            if partial_cases:
                                all_test_cases.extend(partial_cases)
                                task.generated_count = len(all_test_cases)
                                logger.info(f"任务{task_id}: 第{batch_idx+1}批提取到{len(partial_cases)}条部分用例")
                                failed_batches.append({
                                    "batch_idx": batch_idx,
                                    "modules": current_modules,
                                    "generated_count": len(partial_cases)
                                })
                            else:
                                logger.error(f"任务{task_id}: 第{batch_idx+1}批无法提取任何用例")
                                failed_batches.append({
                                    "batch_idx": batch_idx,
                                    "modules": current_modules,
                                    "generated_count": 0
                                })
                    else:
                        logger.error(f"任务{task_id}: 第{batch_idx+1}批LLM调用返回为空")
                        
                except Exception as e:
                    logger.error(f"任务{task_id}: 第{batch_idx+1}批生成异常: {e}")
                    failed_batches.append({
                        "batch_idx": batch_idx,
                        "modules": current_modules,
                        "generated_count": 0,
                        "error": str(e)
                    })
                    continue
            
            # === 智能重试：处理截断/失败的批次 ===
            if failed_batches and len(failed_batches) < batch_count * 0.5:  # 失败批次<50%才重试
                logger.info(f"任务{task_id}: 检测到{len(failed_batches)}个失败批次，启动智能重试...")
                
                for failed_batch in failed_batches[:3]:  #最多重试3个批次
                    retry_modules = failed_batch["modules"]
                    retry_strategy = smart_strategy.get_retry_strategy(retry_modules)
                    
                    logger.info(f"任务{task_id}: 重试批次{failed_batch['batch_idx']+1}（{len(retry_modules)}模块 → {retry_strategy['retry_count']}批重试）")
                    
                    # 使用更小的批次重试
                    for retry_idx in range(retry_strategy["retry_count"]):
                        retry_start = retry_idx * retry_strategy["modules_per_retry"]
                        retry_end = min(retry_start + retry_strategy["modules_per_retry"], len(retry_modules))
                        retry_current_modules = retry_modules[retry_start:retry_end]
                        
                        logger.info(f"任务{task_id}: 重试第{retry_idx+1}/{retry_strategy['retry_count']}批，模块: {retry_current_modules}")
                        
                        try:
                            retry_batch_modules_list = generator._format_modules_list(retry_current_modules)
                            retry_batch_content = generator._extract_batch_content(requirement_doc_content, retry_current_modules, 20000)
                            
                            retry_system_prompt, retry_user_prompt = generator._build_prompts_from_skill(
                                skill_content, project_name, version_number, retry_batch_content, retry_current_modules
                            )
                            
                            retry_response = await generator.llm_service.async_call_llm(
                                prompt=retry_user_prompt,
                                system_prompt=retry_system_prompt,
                                temperature=0.3,
                                max_tokens=retry_strategy["max_tokens_per_retry"]
                            )
                            
                            if retry_response:
                                retry_result = generator._parse_llm_response(retry_response)
                                if retry_result and retry_result.get("test_cases"):
                                    retry_count = len(retry_result.get("test_cases"))
                                    all_test_cases.extend(retry_result.get("test_cases"))
                                    task.generated_count = len(all_test_cases)
                                    logger.info(f"任务{task_id}: 重试成功！额外生成{retry_count}条用例")
                        except Exception as retry_error:
                            logger.warning(f"任务{task_id}: 重试失败: {retry_error}")
                            continue
            
            # 输出智能策略统计
            strategy_stats = smart_strategy.get_statistics()
            logger.info(f"任务{task_id}: 智能策略统计 - 总批次{strategy_stats['total_batches']}, 平均成功率{strategy_stats['avg_success_rate']:.1%}, 截断批次{strategy_stats['truncated_count']}, 最终系数{strategy_stats['current_multiplier']:.2f}")
            
            task.progress = 85
            task.current_step = f"LLM生成完成（智能调整{strategy_stats['adjustments']}次），正在保存{len(all_test_cases)}条测试用例..."
            db.commit()
            logger.info(f"任务{task_id}: LLM生成完成，开始保存测试用例")
            
            if all_test_cases:
                parsed_result = {
                    "test_cases": all_test_cases,
                    "analysis_summary": {
                        "total_count": len(all_test_cases),
                        "p0_count": sum(1 for tc in all_test_cases if tc.get("priority") == "P0"),
                        "p1_count": sum(1 for tc in all_test_cases if tc.get("priority") == "P1"),
                        "p2_count": sum(1 for tc in all_test_cases if tc.get("priority") == "P2"),
                        "p3_count": sum(1 for tc in all_test_cases if tc.get("priority") == "P3"),
                    }
                }
                
                # 保存测试用例
                task.progress = 87
                task.current_step = f"正在保存{len(all_test_cases)}条测试用例..."
                db.commit()
                
                await generator._save_test_cases(
                    version_id, parsed_result.get("test_cases", [])
                )
                
                task.progress = 89
                task.current_step = "测试用例保存完成..."
                db.commit()

                task.result_data = parsed_result
                task.generated_count = len(all_test_cases)
                db.commit()
                logger.info(f"任务{task_id}: 分批生成完成，共{len(all_test_cases)}条用例")
            else:
                task.status = TaskStatus.FAILED
                task.error_message = "分批生成失败，未能生成任何测试用例"
                task.completed_at = datetime.utcnow()
                db.commit()
                return
        else:
            task.progress = 20
            task.current_step = "正在调用LLM生成测试用例..."
            db.commit()
            
            result = await generator.generate_test_assets(
                version_id=version_id,
                requirement_doc_content=requirement_doc_content,
                project_name=project_name,
                version_number=version_number
            )
            
            if result.get("success"):
                task.result_data = result
                task.generated_count = result.get("test_cases_count", 0)
                db.commit()
                logger.info(f"任务{task_id}: 单次生成完成，共{task.generated_count}条用例")
            else:
                task.status = TaskStatus.FAILED
                task.error_message = result.get("error", "生成失败")
                task.completed_at = datetime.utcnow()
                db.commit()
                return
        
        task.status = TaskStatus.COMPLETED
        task.progress = 100
        task.current_step = "生成完成"
        task.completed_at = datetime.utcnow()
        task.duration_seconds = (task.completed_at - task.started_at).total_seconds()
        db.commit()
        
        logger.info(f"任务{task_id}完成，用时{task.duration_seconds}秒，生成{task.generated_count}条用例")
        
    except asyncio.CancelledError:
        logger.warning(f"任务{task_id}被取消（进程关闭）")
        try:
            task = db.query(GenerationTask).filter(GenerationTask.id == task_id).first()
            if task:
                task.status = TaskStatus.FAILED
                task.error_message = "后台进程被取消，任务中断"
                task.completed_at = datetime.utcnow()
                if task.started_at:
                    task.duration_seconds = (task.completed_at - task.started_at).total_seconds()
                db.commit()
        except Exception as e2:
            logger.error(f"更新取消任务状态失败: {e2}")
        raise
        
    except Exception as e:
        logger.error(f"任务{task_id}执行异常: {e}")
        import traceback
        traceback.print_exc()
        
        try:
            task = db.query(GenerationTask).filter(GenerationTask.id == task_id).first()
            if task:
                task.status = TaskStatus.FAILED
                task.error_message = str(e)
                task.completed_at = datetime.utcnow()
                if task.started_at:
                    task.duration_seconds = (task.completed_at - task.started_at).total_seconds()
                db.commit()
        except Exception as e2:
            logger.error(f"更新任务状态失败: {e2}")
            
    finally:
        db.close()


def create_generation_task(
    db: Session,
    project_id: int,
    version_id: int,
    task_type: TaskType,
    input_data: Dict[str, Any],
    user_id: Optional[str] = None
) -> GenerationTask:
    """创建生成任务
    
    Args:
        db: 数据库会话
        project_id: 项目ID
        version_id: 版本ID
        task_type: 任务类型
        input_data: 输入参数
        user_id: 用户ID
        
    Returns:
        GenerationTask: 任务对象
    """
    task = GenerationTask(
        task_type=task_type,
        status=TaskStatus.PENDING,
        project_id=project_id,
        version_id=version_id,
        input_data=input_data,
        created_by=user_id,
        current_step="任务已创建，等待执行..."
    )
    
    db.add(task)
    db.commit()
    db.refresh(task)
    
    logger.info(f"创建任务 {task.id}, 项目: {project_id}, 版本: {version_id}")
    
    return task


def get_task_status(db: Session, task_id: int) -> Optional[Dict[str, Any]]:
    """获取任务状态
    
    Args:
        db: 数据库会话
        task_id: 任务ID
        
    Returns:
        Dict: 任务状态信息
    """
    task = db.query(GenerationTask).filter(GenerationTask.id == task_id).first()
    if not task:
        return None
    
    return task.to_dict()