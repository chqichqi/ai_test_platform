export interface Project {
  id: number;
  name: string;
  code: string;
  description: string | null;
  owner_id: string | null;
  owner: {
    id: string;
    username: string;
    full_name: string | null;
    email: string;
  } | null;
  status: string;
  project_type?: 'web' | 'app';
  app_platform?: 'android' | 'ios' | null;
  app_package_name?: string | null;
  app_launch_activity?: string | null;
  app_bundle_id?: string | null;
  app_device_type?: 'simulator' | 'real' | null;
  app_device_udid?: string | null;
  app_simulator_name?: string | null;
  app_automation_name?: string | null;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
}

export interface ProjectDetailResponse extends Project {
  versions_count: number;
  test_cases_count: number;
  latest_version: {
    id: number;
    version_number: string;
    version_name: string | null;
    status: string;
  } | null;
}

export interface ProjectListResponse {
  items: Project[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface ProjectCreate {
  name: string;
  code: string;
  description?: string;
  owner_id?: string;
  project_type?: 'web' | 'app';
  app_platform?: 'android' | 'ios';
  app_package_name?: string;
  app_launch_activity?: string;
  app_bundle_id?: string;
  app_device_type?: 'simulator' | 'real';
  app_device_udid?: string;
  app_simulator_name?: string;
  app_automation_name?: string;
}

export interface ProjectUpdate {
  name?: string;
  description?: string;
  owner_id?: string;
  status?: 'active' | 'archived';
  project_type?: 'web' | 'app';
  app_platform?: 'android' | 'ios';
  app_package_name?: string;
  app_launch_activity?: string;
  app_bundle_id?: string;
  app_device_type?: 'simulator' | 'real';
  app_device_udid?: string;
  app_simulator_name?: string;
  app_automation_name?: string;
}

export interface ProjectStats {
  total_versions: number;
  total_test_cases: number;
  passed_test_cases: number;
  failed_test_cases: number;
  pending_test_cases: number;
  total_executions: number;
  latest_execution_time: string | null;
}