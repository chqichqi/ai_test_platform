# SKILL 创建步骤规划

## 步骤1：基本信息（必填）
**必须填写：**
- SKILL名称（name）
- SKILL编码（code）
- SKILL类型（skill_type）

**可选填写：**
- 描述（description）
- 标签（tags）
- 是否全局SKILL（is_global）

## 步骤2：角色定义（必填）
**必须填写：**
- 角色名称（content.role.name）
- 角色描述（content.role.description）

**可选填写：**
- 专业知识（content.role.expertise）- 字符串数组
- 行为规则（content.role.behavior_rules）- 字符串数组

## 步骤3：测试方法（可选）
**完全可选：**
- 测试方法列表（content.methods）
  - 每个方法包含：名称、描述、适用场景
  - 可以为空，创建后再添加

## 步骤4：提示词模板（必填）
**必须填写：**
- 提示词模板（content.prompt_template）

**可选填写：**
- 输出格式（content.output.format）
- JSON Schema定义（content.output.schema）

---

## 验证逻辑

### 步骤1验证
```
if (!values.name) 报错：请输入SKILL名称
if (!values.code) 报错：请输入SKILL编码
if (!values.skill_type) 报错：请选择SKILL类型
```

### 步骤2验证
```
if (!values.content?.role?.name) 报错：请输入角色名称
if (!values.content?.role?.description) 报错：请输入角色描述
```

### 步骤3验证
```
无强制验证，可以为空
```

### 步骤4验证
```
if (!values.content?.prompt_template) 报错：请输入提示词模板
```

## 用户体验设计

1. **步骤指示器**：显示当前步骤和总步骤
2. **上一步/下一步按钮**：
   - 第1步：只有"下一步"
   - 第2-3步：有"上一步"和"下一步"
   - 第4步：有"上一步"和"完成"
3. **跳过可选步骤**：步骤3（测试方法）可以跳过
4. **自动保存**：如果用户关闭弹窗，提示是否保存草稿
