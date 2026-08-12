import { createSlice, PayloadAction } from "@reduxjs/toolkit";

export interface UserState {
  user: any | null;
  isLogedIn: boolean;
  loading: boolean;
  error: string | null;
}

const initialState: UserState = {
  user: null,
  isLogedIn: false,
  loading: false,
  error: null,
};

const userSlice = createSlice({
  name: "user",
  initialState,
  reducers: {},
  extraReducers: (builder) => {
    builder
      .addCase("LOGIN_START" as any, (state: UserState) => {
        state.loading = true;
        state.error = null;
      })
      .addCase("LOGIN_SUCCESS" as any, (state: UserState) => {
        state.loading = false;
        state.isLogedIn = true;
      })
      .addCase("LOGIN_ERROR" as any, (state: UserState, action: PayloadAction<any>) => {
        state.loading = false;
        state.error = action.payload;
      })
      .addCase("USER_START" as any, (state: UserState) => {
        state.loading = true;
      })
      .addCase("USER_SUCCESS" as any, (state: UserState, action: PayloadAction<any>) => {
        state.loading = false;
        state.user = action.payload;
        state.isLogedIn = true;
      })
      .addCase("USER_ERROR" as any, (state: UserState) => {
        state.loading = false;
        state.isLogedIn = false;
      })
      .addCase("LOGOUT" as any, (state: UserState) => {
        state.user = null;
        state.isLogedIn = false;
        state.loading = false;
        state.error = null;
      })
      .addCase("REFRESH_TOKEN_ERROR" as any, (state: UserState) => {
        state.user = null;
        state.isLogedIn = false;
      });
  },
});

export default userSlice.reducer;