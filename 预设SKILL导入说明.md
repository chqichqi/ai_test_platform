# 预设SKILL导入说明

## 系统启动时自动初始化

系统已配置在启动时自动检查并插入3个预设SKILL：

1. **功能测试用例生成专家** - functional_test_template_master
2. **WebUI自动化测试专家** - webui_automation_template_master  
3. **API接口测试专家** - api_test_template_master

## 手动导入（如需要）

如果系统启动后预设SKILL没有自动创建，可以手动导入：

### 方法1：通过API导入

```bash
# 1. 登录获取token
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}'

# 2. 导入功能测试SKILL
curl -X POST http://localhost:8000/api/v1/skills/import \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d @backend/app/core/data/preset_skills/functional_test_template.json

# 3. 导入WebUI测试SKILL
curl -X POST http://localhost:8000/api/v1/skills/import \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d @backend/app/core/data/preset_skills/webui_automation_template.json

# 4. 导入API测试SKILL
curl -X POST http://localhost:8000/api/v1/skills/import \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d @backend/app/core/data/preset_skills/api_test_template.json
```

### 方法2：通过前端界面导入

1. 打开SKILL管理页面
2. 点击【导入】按钮
3. 选择JSON文件：
   - `functional_test_template.json`
   - `webui_automation_template.json`
   - `api_test_template.json`
4. 点击确认导入

---

## 文件位置

预设SKILL文件位于：

```
backend/app/core/data/preset_skills/
├── functional_test_template.json
├── webui_automation_template.json
└── api_test_template.json
```

---

## 重启系统

重启后端服务后，预设SKILL会自动初始化：

```bash
cd backend
python -c "from app.core.database import init_db; init_db()"
```

或

```bash
cd backend
uvicorn app.main:app --reload
```

---

## 验证

重启后验证预设SKILL是否已创建：

```bash
curl http://localhost:8000/api/v1/skills/ \
  -H "Authorization: Bearer YOUR_TOKEN"
```

应该能看到3个预设SKILL（code以`_master`结尾）。

---

## 注意事项

1. **编码唯一性**：预设SKILL使用特定编码，确保不会重复创建
2. **全局可用**：预设SKILL标记为`is_global=true`，所有用户可见
3. **默认标记**：预设SKILL标记为`is_default=true`，显示"默认"标签
4. **不可编辑**：建议不要直接编辑预设SKILL，而是使用【快速复制】功能

---

## 使用流程

```
1. 系统启动
   ↓
2. 自动检查预设SKILL
   ↓
3. 如不存在，自动创建
   ↓
4. 用户登录系统
   ↓
5. 进入SKILL管理页面
   ↓
6. 查看预设SKILL（带"默认"标签）
   ↓
7. 点击【快速复制】
   ↓
8. 修改名称和编码
   ↓
9. 创建个人SKILL
   ↓
10. 用于生成测试用例
```
