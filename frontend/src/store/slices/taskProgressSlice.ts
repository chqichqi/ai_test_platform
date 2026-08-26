import { createSlice, PayloadAction } from '@reduxjs/toolkit';

export interface GenerationTask {
  id: number;
  display_id: string;
  task_type: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  project_id: number;
  version_id: number;
  progress: number;
  current_step: string | null;
  total_batches: number;
  current_batch: number;
  generated_count: number;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  duration_seconds: number | null;
  created_at: string;
  updated_at: string;
}

interface TaskProgressState {
  visible: boolean;
  taskId: number | null;
  forceOpen: boolean;
  runningTasks: GenerationTask[];
  currentTask: GenerationTask | null;
  backendHealthy: boolean;
  lastPollTime: number | null;
}

const initialState: TaskProgressState = {
  visible: false,
  taskId: null,
  forceOpen: false,
  runningTasks: [],
  currentTask: null,
  backendHealthy: true,
  lastPollTime: null,
};

const taskProgressSlice = createSlice({
  name: 'taskProgress',
  initialState,
  reducers: {
    openProgressModal: (state, action: PayloadAction<number>) => {
      state.visible = true;
      state.taskId = action.payload;
      state.forceOpen = true;
    },
    closeProgressModal: (state) => {
      state.visible = false;
      state.forceOpen = false;
    },
    resetForceOpen: (state) => {
      state.forceOpen = false;
    },
    setRunningTasks: (state, action: PayloadAction<GenerationTask[]>) => {
      state.runningTasks = action.payload;
      state.lastPollTime = Date.now();
    },
    setCurrentTask: (state, action: PayloadAction<GenerationTask | null>) => {
      state.currentTask = action.payload;
      // 不自动修改 visible，让组件自己控制
    },
    updateTaskProgress: (state, action: PayloadAction<{ taskId: number; task: GenerationTask }>) => {
      const { taskId, task } = action.payload;
      const index = state.runningTasks.findIndex(t => t.id === taskId);
      if (index !== -1) {
        state.runningTasks[index] = task;
      }
      if (state.currentTask?.id === taskId) {
        state.currentTask = task;
      }
    },
    removeRunningTask: (state, action: PayloadAction<number>) => {
      state.runningTasks = state.runningTasks.filter(t => t.id !== action.payload);
      if (state.currentTask?.id === action.payload) {
        state.currentTask = null;
      }
    },
    setBackendHealthy: (state, action: PayloadAction<boolean>) => {
      state.backendHealthy = action.payload;
    },
    trackTask: (state, action: PayloadAction<number>) => {
      state.taskId = action.payload;
      state.visible = true;
    },
    untrackTask: (state) => {
      state.taskId = null;
      state.visible = false;
      state.currentTask = null;
    },
    clearAllTaskState: (state, action: PayloadAction<number | undefined>) => {
      // 完全清理所有任务状态
      state.taskId = null;
      state.visible = false;
      state.currentTask = null;
      state.forceOpen = false;
      // 如果提供了 taskId，从 runningTasks 中移除
      if (action.payload) {
        state.runningTasks = state.runningTasks.filter(t => t.id !== action.payload);
      }
    },
  },
});

export const {
  openProgressModal,
  closeProgressModal,
  resetForceOpen,
  setRunningTasks,
  setCurrentTask,
  updateTaskProgress,
  removeRunningTask,
  setBackendHealthy,
  trackTask,
  untrackTask,
  clearAllTaskState,
} = taskProgressSlice.actions;

export default taskProgressSlice.reducer;