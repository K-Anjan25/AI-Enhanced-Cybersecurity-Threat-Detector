import { ThunkDispatch } from "redux-thunk";
import { State } from "./state";
import { UPDATE_PROFILE, UPDATE_PROFILE_IMAGE } from "./profile";

export interface User {
  userId: string;
  email: string;
  roles: string[];
  profileImageURL?: string;
  // optional aliases used across the dashboard
  id?: string | number;
  username?: string;
  role?: string;
  permissions?: string[];
  clearanceLevel?: number | string | null;
  department?: string | null;
}

export interface UserCredentials {
  id: string;
  email: string;
}

export interface LoginForm {
  identifier?: string; 
  email?: string;      
  password: string;
}

export interface UserProfile {
  username?: string;
  email?: string;
  profileImageURL?: string;
}

export interface PasswordResetRequest {
  email: string;
}

export interface PasswordResetPayload {
  token: string;
  new_password: string;
}

export interface UpdatePasswordPayload {
  current_password: string;
  new_password: string;
}

export interface RegisterForm {
  email: string;
  password: string;
  passwordConfirm?: string;
}

export interface Token {
  accessToken: string;
  refreshToken: string;
}

export interface Login extends Token {
  role: string;
}

export type RefreshToken = Token;

interface LOGIN_START {
  type: "LOGIN_START";
}

interface LOGIN_SUCCESS {
  type: "LOGIN_SUCCESS";
}

interface LOGIN_ERROR {
  type: "LOGIN_ERROR";
  payload: string;
}

interface USER_START {
  type: "USER_START";
}

interface USER_SUCCESS {
  type: "USER_SUCCESS";
  payload: User;
}

interface USER_ERROR {
  type: "USER_ERROR";
}

interface REFRESHTOKEN_ERROR {
  type: "REFRESH_TOKEN_ERROR";
}

interface LOGOUT {
  type: "LOGOUT";
}

export interface UserReducer extends User {
  isLogedIn: boolean;
}

export type UserAction =
  | LOGIN_START
  | LOGIN_SUCCESS
  | LOGIN_ERROR
  | LOGOUT
  | USER_START
  | USER_SUCCESS
  | USER_ERROR
  | REFRESHTOKEN_ERROR
  | UPDATE_PROFILE
  | UPDATE_PROFILE_IMAGE;

export type UserState = State<UserReducer>;

export type UserRole = "ADMIN" | "USER" | string;

export type UserDispatch = ThunkDispatch<UserState, void, UserAction>;