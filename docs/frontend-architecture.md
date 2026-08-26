# Frontend Architecture

**Framework**: Next.js 14 (App Router) + TypeScript + Tailwind CSS v3 + Shadcn UI

**Directory Structure** (`client/`):
```
client/
├── app/                    # Next.js App Router pages & layouts
│   ├── layout.tsx          # Root layout with providers & metadata
│   ├── page.tsx            # Landing / welcome page
│   ├── auth/               # Auth flow routes
│   │   ├── login/page.tsx
│   │   ├── register/page.tsx
│   │   └── reset-password/page.tsx
│   ├── dashboard/          # Protected dashboard routes
│   │   ├── page.tsx        # Overview landing
│   │   ├── alerts/page.tsx
│   │   ├── incidents/page.tsx        # Cases / incident management
│   │   ├── soar/page.tsx              # SOAR playbooks & actions
│   │   ├── entities/page.tsx          # Entity graph & MITRE mapping
│   │   ├── analytics/page.tsx         # AI analytics & trends
│   │   ├── rules/page.tsx             # Detection rules management
│   │   ├── admin/page.tsx             # Org/tenant admin
│   │   └── settings/page.tsx          # User preferences
│   └── profile/page.tsx      # User profile & settings
├── components/             # UI components (shadcn + custom)
│   ├── ui/                 # shadcn-derived components (Button, Card, Input, etc.)
│   ├── layout/             # Sidebar, Navbar, TopBar, PageHeader
│   ├── dashboard/          # Dashboard-specific components (AlertCard, CaseCard, etc.)
│   └── shared/             # Generic reusable components (Modal, Toast, Skeleton, etc.)
├── lib/                    # Utility libraries
│   ├── api.ts              # Fetch wrapper with auth interceptor
│   ├── queryClient.ts      # TanStack Query config
│   ├── storage.ts          # localStorage helpers (density, preferences)
│   ├── utils.ts            # General helpers (cn, formatDate, etc.)
│   └── constants.ts        # Feature flags, API paths
├── hooks/                  # Custom React hooks
│   ├── use-auth.ts         # Auth state & token refresh
│   ├── use-alerts.ts       # Alerts polling/subscription
│   ├── use-debounce.ts
│   └── use-resize.ts
├── store/                  # Optional Redux Toolkit (if needed for complex global state)
│   └── slices/
├── contexts/               # React contexts (Theme, User, Org)
│   ├── ThemeProvider.tsx
│   └── UserProvider.tsx
├── types/                  # TypeScript type definitions (auto-generated from schemas)
│   ├── api.ts              # Auto-generated API response types
│   ├── auth.ts
│   └── dashboard.ts
├── styles/                 # Global styles & Tailwind config overrides
│   └── globals.css
├── hooks/                  # Custom React hooks
└── middleware.ts           # Auth middleware (token auto-refresh on route change)
```

---

## 1. Routing & Navigation (App Router)

- **Root**: `app/layout.tsx` — defines `<html/>`, `<head/>`, metadata, and wraps children in providers.
- **Landing**: `app/page.tsx` — public welcome page (no auth required).
- **Auth Routes**: `app/auth/login/page.tsx`, `app/auth/register/page.tsx`, `app/auth/reset-password/page.tsx` — all public.
- **Dashboard**: All protected routes under `app/dashboard/`. Sidebar navigation is persistent; page content changes on navigation.
- **Middleware** (`middleware.ts`): Intercepts route changes, refreshes access token if near expiry, redirects unauthenticated users away from `/dashboard/*`.

---

## 2. State Management

| State Type         | Library                    | Purpose                                          |
|--------------------|----------------------------|--------------------------------------------------|
| Server cache       | **TanStack React Query**   | Data fetching, caching, background refetching, optimistic updates |
| Client global      | **React Context** (lightweight) | User session, org context, theme preferences    |
| Form state         | **React Hook Form** + **Zod** | Login/register/profile forms with validation    |
| Modal dialog state | **React Dialog** or custom | Modal open/close state with focus trap          |

**TanStack Query configuration** (`lib/queryClient.ts`):
- Refetch intervals per feature (alerts: 30s, analytics: 1min, entities: 2min)
- Stale-while-revalidate strategy
- Retry failed requests (3x with exponential backoff)
- Persistence to `localStorage` for offline recovery (optional)

---

## 3. API Layer

**Base URL**: `import { API_BASE_URL } from "@/lib/constants";`

- `API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"` (points to FastAPI backend)
- All API calls go through `lib/api.ts` — a thin wrapper around `fetch` with automatic auth header injection.

**`lib/api.ts`**:
```ts
import { type AxiosInstance, type AxiosRequestConfig } from "axios";
import axios from "axios";

const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
  withCredentials: true, // cookies for session (access_token, refresh_token)
});

/** Request interceptor — inject access_token from cookies or localStorage */
api.interceptors.request.use((config) => {
  const token = config.headers["Authorization"] as string | undefined;
  if (!token) {
    // fall back to reading access_token cookie set by backend on login
    const cookies = document.cookie.split(";");
    for (const c of cookies) {
      if (c.trim().startsWith("access_token=")) {
        config.headers.Authorization = `Bearer ${c.trim().split("=")[1]}`;
        break;
      }
    }
  }
  return config;
});

/** Response interceptor — handle 401 → refresh token → retry */
api.interceptors.response.use(
  (resp) => resp,
  async (err) => {
    const originalConfig = err.config;
    if (err.response?.status === 401 && !originalConfig._retry) {
      originalConfig._retry = true;
      // TODO: call backend refresh endpoint (or use Next.js middleware)
      // const { data } = await api.post("/auth/refresh");
      // originalConfig.headers.Authorization = `Bearer ${data.access_token}`;
      // return api(originalConfig);
    }
    return Promise.reject(err);
  }
);

export const api = {
  get: <T>(url: string, config?: AxiosRequestConfig) => api.get(url, config),
  post: <T>(url: string, data: unknown, config?: AxiosRequestConfig) =>
    api.post(url, data, config),
  put: <T>(url: string, data: unknown, config?: AxiosRequestConfig) =>
    api.put(url, data, config),
  delete: <T>(url: string, config?: AxiosRequestConfig) => api.delete(url, config),
  patch: <T>(url: string, data: unknown, config?: AxiosRequestConfig) =>
    api.patch(url, data, config),
};

export type { AxiosRequestConfig };
```

---

## 4. Auth Flow (Cookie-Based JWT)

- **Login**: `POST /api/v1/auth/login` → backend sets `access_token` and `refresh_token` as HttpOnly cookies (sameSite=strict). Response also returns user payload for immediate UI update.
- **Register**: `POST /api/v1/auth/register` → same cookie pattern.
- **Me/Profile**: `GET /api/v1/auth/me` / `GET /api/v1/users/me` — returns current user info (username, email, role, permissions, org_id).
- **Refresh**: `POST /api/v1/auth/refresh` — if access_token expires, Next.js middleware auto-refreshes by calling this endpoint; new tokens set in cookies.
- **Logout**: `POST /api/v1/auth/logout` → backend clears cookies. Client also clears local state.
- **Token Storage**: HttpOnly cookies (secure, sameSite=strict). **Never** store JWT in localStorage (XSS risk).
- **Role/Permission Check**: `useAuth` hook provides `role`, `permissions`, `orgId`, `isBlocked`. ABAC checks use `subject_permissions()` from backend.

---

## 5. Error Handling & Loading UX

- **Loading skeletons**: use shadcn `Skeleton` or custom CSS-animated placeholders.
- **Error boundaries**: Next.js `error.tsx` per route + React `ErrorBoundary` component for critical crashes.
- **API errors**: Display inline error messages from backend detail strings; non-blocking toast notifications (using shadcn `Toast`).
- **Network errors**: Retry button for failed requests; offline detection via `navigator.onLine`.

---

## 6. Environment Variables

| Variable                | Description                          |
|-------------------------|--------------------------------------|
| `NEXT_PUBLIC_API_URL`   | Base URL for FastAPI backend (dev: `http://localhost:8000`, prod: backend URL) |
| `NEXT_PUBLIC_APP_URL`   | Base URL for the Next.js app (usually left auto) |
| `NEXT_PUBLIC_ENABLE_KAFKA` | Feature flag (bool)                 |
| `NEXT_PUBLIC_SMTP_HOST`  | Optional: for email-based password reset |

All env vars prefixed with `NEXT_PUBLIC_` are exposed to the browser; secret vars stay in `backend/.env`.

---

## 7. Type Generation from Schemas

- Use `fastapi-typescript-generators` or `openapi-generator` to auto-generate TypeScript types from the FastAPI route handlers.
- Alternatively, manually maintain `types/api.ts` mirroring the `backend/app/schemas/` definitions, keeping them in sync via CI check.

---

## 8. Deployment

- **Docker**: Next.js serves static + server-side in production (`next start -p 3000`).
- **Vercel**: Recommended for Next.js hosting — automatically picks up `github` repo, builds on each push, and handles edge middleware.
- **Kubernetes**: Helm chart can serve Next.js as a Deployment + Service on port 3000, behind an Ingress pointing to the FastAPI backend.

---

## 9. Development Workflow

- `pnpm create next-app@latest client --ts --tailwind --eslint --app --src-dir` (or equivalent with `shadcn/ui` init).
- `pnpm dlx shadcn-ui@latest init` in the client dir to configure Tailwind.
- Add `framer-motion` for micro-interactions.
- Feature branches → CI runs `pnpm build` + `pnpm lint` + typecheck; `pnpm test` runs Jest/React Testing Library on component files.
- PR must pass all gates before merge to `main`.

---