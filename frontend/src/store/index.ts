import { configureStore } from '@reduxjs/toolkit';
import authReducer from './slices/authSlice';
import themeReducer from './slices/themeSlice';
import taskProgressReducer from './slices/taskProgressSlice';

export const store = configureStore({
  reducer: {
    auth: authReducer,
    theme: themeReducer,
    taskProgress: taskProgressReducer,
  },
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;