import React from "react";
import { useState } from "react";
import Login from "./pages/Login";
import AlertList from "./components/AlertList";
import AlertChart from "./AlertChart";
import { handleLogout } from "./services/api";

function App() {
  const [authenticated, setAuthenticated] = useState(!!localStorage.getItem("access_token"));

  return authenticated ? (
    <div className="min-h-screen bg-gray-900 text-white">
    <div className="flex justify-between items-center p-5 bg-gray-800 shadow-lg">
        <h1 className="text-2xl font-bold text-cyan-400">AI Cybersecurity Threat Detector</h1>
      {/* ✅ LOGOUT BUTTON HERE */}
      <button
        onClick={handleLogout}
        style={{ marginBottom: "15px" }}
        className="bg-red-600 px-4 py-2 rounded hover:bg-red-700 transition"
      >
        Logout
      </button>
      </div>
      <div className="p-6">
        <AlertList />
      </div>
      <div className="p-6"><AlertChart /></div>
    </div>
  ) : (
    <Login setAuthenticated={setAuthenticated} />
  );
}

export default App;