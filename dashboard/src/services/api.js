import axios from "axios";
const API_BASE_URL = "http://localhost:8000"; // Flask backend

export const loginUser = async (username, password) => {
  const response = await axios.post(`${API_BASE_URL}/login`, {
    username,
    password,
  });
  return response.data;
};


export const fetchAlerts = async () => {
  const token = localStorage.getItem("access_token");
  const response = await axios.get(`${API_BASE_URL}/alerts`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
  return response.data;
};

export const handleLogout = async () => {
  const token = localStorage.getItem("access_token");

  await axios.post(
    `${API_BASE_URL}/logout`,
    {},
    {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    }
  );


  localStorage.clear();
  window.location.reload();
};


export const refreshAccessToken = async () => {
  const refreshToken = localStorage.getItem("refresh_token");

  const response = await axios.post(
    `${API_BASE_URL}/refresh`,
    {},
    {
      headers: {
        Authorization: `Bearer ${refreshToken}`,
      },
    }
  );

  localStorage.setItem("access_token", response.data.access_token);
  return response.data.access_token;
};

// // 🔐 Attach access token automatically
// api.interceptors.request.use((config) => {
//   const token = localStorage.getItem("access_token");
//   if (token) {
//     config.headers.Authorization = `Bearer ${token}`;
//   }
//   return config;
// });

