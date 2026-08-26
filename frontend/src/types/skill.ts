// SKILL类型定义
export type SkillType = 'functional' | 'api' | 'ui' | 'performance' | 'security';
export type SkillStatus = 'active' | 'draft' | 'deprecated';

export interface SkillRole {
  name: string;
  description: string;
  expertise: string[];
  behavior_rules: string[];
}

export interface SkillInput {
  required_fields: string[];
  optional_fields: string[];
}

export interface SkillOutput {
  format: string;
  schema: Record<string, any>;
}

export interface SkillMethod {
  name: string;
  description: string;
  applicable_scenarios: string[];
}

export interface SkillDomainRule {
  domain: string;
  must_test: string[];
  security_focus: string[];
}

export interface SkillPromptVariable {
  name: string;
  required: boolean;
  description: string;
}

export interface SkillPromptTemplate {
  system_prompt: string;
  user_prompt: string;
  variables?: SkillPromptVariable[];
}

export interface SkillContent {
  role: SkillRole;
  input: SkillInput;
  output: SkillOutput;
  methods: SkillMethod[];
  domain_rules: SkillDomainRule[];
  quality_checks: string[];
  prompt_template: string | SkillPromptTemplate;
}

export interface Skill {
  id: number;
  name: string;
  code: string;
  description: string | null;
  skill_type: SkillType;
  tags: string[];
  version: string;
  is_latest: boolean;
  is_global: boolean;
  is_default: boolean;
  project_id: number | null;
  status: SkillStatus;
  usage_count: number;
  generation_count: number;
  avg_quality_score: number | null;
  created_by: number | null;
  created_at: string;
  updated_at: string;
}

export interface SkillDetailResponse extends Skill {
  content: SkillContent;
  examples: SkillExample[];
}

export interface SkillListResponse {
  items: Skill[];
  total: number;
  page: number;
  page_size: number;
}

export interface SkillCreate {
  name: string;
  code: string;
  description?: string;
  skill_type: SkillType;
  tags?: string[];
  is_global?: boolean;
  is_default?: boolean;
  project_id?: number;
  content: SkillContent;
}

export interface SkillUpdate {
  name?: string;
  description?: string;
  tags?: string[];
  content?: SkillContent;
  status?: SkillStatus;
  is_default?: boolean;
}

export interface SkillExample {
  id: number;
  skill_id: number;
  name: string | null;
  description: string | null;
  input_example: string;
  output_example: Record<string, any>;
  is_active: boolean;
  sort_order: number;
  created_by: number | null;
  created_at: string;
}

export interface SkillExampleCreate {
  name?: string;
  description?: string;
  input_example: string;
  output_example: Record<string, any>;
  sort_order?: number;
}

export interface SkillQueryParams {
  page?: number;
  page_size?: number;
  skill_type?: SkillType;
  status?: SkillStatus;
  project_id?: number;
  is_global?: boolean;
  search?: string;
}

export interface SkillTestRequest {
  input_text: string;
  requirement_images_ocr?: string[];
}

export interface SkillTestResponse {
  success: boolean;
  generated_count: number;
  test_cases: any[];
  analysis_summary: Record<string, any>;
  generation_time_ms: number;
  token_usage: Record<string, number>;
}
