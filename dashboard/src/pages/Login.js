import React, { useState } from "react";
import { loginUser } from "../services/api";

function Login({ setAuthenticated }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  const handleLogin = async (e) => {
    e.preventDefault();
    try {
        const data = await loginUser(username, password);
        
      localStorage.setItem("access_token", data.access_token);
      localStorage.setItem("refresh_token", data.refresh_token);
      setAuthenticated(true);
    } catch (err) {
      setError("Invalid credentials");
    }
    };

  return (
    // <div>
    //   <h2>Login</h2>
    //   <input
    //     placeholder="Username"
    //     onChange={(e) => setUsername(e.target.value)}
    //   />
    //   <input
    //     type="password"
    //     placeholder="Password"
    //     onChange={(e) => setPassword(e.target.value)}
    //   />
    //   <button onClick={handleLogin}>Login</button>
    // </div>

    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-gray-900 to-gray-800">
      <div className="bg-gray-900 p-10 rounded-2xl shadow-2xl w-96 border border-gray-700">
        <h2 className="text-3xl font-bold text-cyan-400 text-center mb-6">
          Threat Detector Login
        </h2>

        {error && (
          <div className="bg-red-600 text-white p-2 rounded mb-4 text-sm">
            {error}
          </div>
        )}

        <form onSubmit={handleLogin}>
          <input
            type="text"
            placeholder="Username"
            className="w-full p-3 mb-4 bg-gray-800 rounded text-white focus:outline-none focus:ring-2 focus:ring-cyan-500"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />

          <input
            type="password"
            placeholder="Password"
            className="w-full p-3 mb-6 bg-gray-800 rounded text-white focus:outline-none focus:ring-2 focus:ring-cyan-500"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />

          <button
            type="submit"
            className="w-full bg-cyan-500 hover:bg-cyan-600 p-3 rounded font-semibold transition"
          >
            Login
          </button>
        </form>
      </div>
    </div>
  );
}

export default Login;