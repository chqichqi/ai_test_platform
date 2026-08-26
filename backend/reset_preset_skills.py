"""
重置预设SKILL脚本
删除现有预设SKILL，重新加载新格式模板
"""

import os
import json
import sys

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.core.models.test_skill import TestSkill, SkillStatus

def reset_preset_skills():
    """重置预设SKILL"""
    session = SessionLocal()
    
    try:
        # 1. 删除现有预设SKILL
        preset_codes = [
            "functional_test_template_master",
            "webui_automation_template_master",
            "api_test_template_master",
            "performance_test_template_master"
        ]
        
        deleted_count = 0
        for code in preset_codes:
            existing = session.query(TestSkill).filter(
                TestSkill.code == code
            ).first()
            if existing:
                session.delete(existing)
                deleted_count += 1
                print(f"Deleted: {code}")
        
        session.commit()
        print(f"\nDeleted {deleted_count} preset skills")
        
        # 2. 重新加载预设SKILL
        preset_skills_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "app", "core", "data", "preset_skills"
        )
        
        preset_files = [
            "functional_test_template.json",
            "webui_automation_template.json",
            "api_test_template.json",
            "performance_test_template.json"
        ]
        
        created_count = 0
        for filename in preset_files:
            filepath = os.path.join(preset_skills_dir, filename)
            if not os.path.exists(filepath):
                print(f"File not found: {filepath}")
                continue
            
            with open(filepath, 'r', encoding='utf-8') as f:
                skill_data = json.load(f)
            
            skill = TestSkill(
                name=skill_data["name"],
                code=skill_data["code"],
                description=skill_data["description"],
                skill_type=skill_data["skill_type"],
                tags=skill_data.get("tags", []),
                is_global=skill_data.get("is_global", True),
                is_default=skill_data.get("is_default", True),
                content=skill_data["content"],  # 新格式的content包含prompt_template对象
                status=SkillStatus.ACTIVE.value,
                created_by="system",
                version="1.0.0",
                is_latest=True,
                usage_count=0,
                generation_count=0
            )
            
            session.add(skill)
            created_count += 1
            print(f"Created: {skill_data['code']}")
            
            # 检查prompt_template格式
            prompt_template = skill_data["content"].get("prompt_template")
            if isinstance(prompt_template, dict):
                print(f"  - prompt_template format: object (NEW)")
                print(f"  - has system_prompt: {bool(prompt_template.get('system_prompt'))}")
                print(f"  - has user_prompt: {bool(prompt_template.get('user_prompt'))}")
            else:
                print(f"  - prompt_template format: string (OLD)")
        
        session.commit()
        print(f"\nCreated {created_count} preset skills")
        print("\nReset completed successfully!")
        
    except Exception as e:
        session.rollback()
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        session.close()

if __name__ == "__main__":
    reset_preset_skills()