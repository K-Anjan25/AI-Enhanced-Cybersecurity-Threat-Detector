import React, { useEffect, useState } from "react";
import { fetchAlerts } from "../services/api";

const AlertList = () => {
  const [alerts, setAlerts] = useState([]);
  const [search, setSearch] = useState("");
  const [riskFilter, setRiskFilter] = useState("All");


  useEffect(() => {
    const loadAlerts = () => {
      fetchAlerts()
      .then(data => setAlerts(data))
      .catch(err => console.error(err));
    };
    loadAlerts();

    const interval = setInterval(loadAlerts, 6000); // Refresh every 60 seconds
    return () => clearInterval(interval); // Cleanup on unmount
      
  }, []);
  
  const criticalAlerts = alerts.filter(a => a.severity === "CRITICAL").length;
  const highAlerts = alerts.filter(a => a.severity === "HIGH").length;
  const mediumAlerts = alerts.filter(a => a.severity === "MEDIUM").length;
  const lowAlerts = alerts.filter(a => a.severity === "LOW").length;

  const filteredAlerts = alerts.filter((alert) => {
  return (
    (riskFilter === "All" || alert.severity === riskFilter.toUpperCase()) &&
    alert.message.toLowerCase().includes(search.toLowerCase())
  );
  });

  return (
    <div>
      
      <h2>Security Alerts</h2>

      <div className="grid grid-cols-3 gap-6 mb-8">
        <div className="bg-gray-800 p-6 rounded-xl shadow-lg">
          <h3 className="text-gray-400">Total Alerts</h3>
          <p className="text-3xl font-bold">{alerts.length}</p>
        </div>

        <div className="bg-red-800 p-6 rounded-xl shadow-lg">
          <h3 className="text-red-300">Critical Alerts</h3>
          <p className="text-3xl font-bold">{criticalAlerts}</p>
        </div>

        <div className="bg-orange-800 p-6 rounded-xl shadow-lg">
          <h3 className="text-orange-300">High Risk</h3>
          <p className="text-3xl font-bold">{highAlerts}</p>
        </div>

        <div className="bg-yellow-800 p-6 rounded-xl shadow-lg">
          <h3 className="text-yellow-300">Medium Risk</h3>
          <p className="text-3xl font-bold">{mediumAlerts}</p>
        </div>

        <div className="bg-green-800 p-6 rounded-xl shadow-lg">
          <h3 className="text-green-300">Low Risk</h3>
          <p className="text-3xl font-bold">{lowAlerts}</p>
        </div>
      </div>

      <div className="flex gap-4 mb-4">
        <input
          type="text"
          placeholder="Search alerts..."
          className="p-2 rounded bg-gray-800 text-white"
          onChange={(e) => setSearch(e.target.value)}
        />

        <select
        className="p-2 rounded bg-gray-800 text-white"
        onChange={(e) => setRiskFilter(e.target.value)}
        >
        <option>All</option>
        <option>Critical</option>
        <option>High</option>
        <option>Medium</option>
        <option>Low</option>
      </select>
      </div>
      
      <div className="bg-gray-800 rounded-xl shadow-lg overflow-hidden">
      <table className="w-full text-left">
        <thead className="bg-gray-700 text-gray-300">
          <tr>
            <th className="p-4">Timestamp</th>
            <th className="p-4">Message</th>
            <th className="p-4">Risk</th>
          </tr>
        </thead>
        <tbody>
          {filteredAlerts.map((alert, index) => (
            <tr key={index} className="border-t border-gray-700 hover:bg-gray-700 transition">
              <td className="p-4">{alert.created_at}</td>
              <td className="p-4">{alert.message}</td>
              <td className="p-4"><span className={`px-3 py-1 rounded-full text-sm font-semibold ${alert.severity === "CRITICAL" ? "bg-red-800 text-white": alert.severity === "HIGH" ? "bg-red-600 text-white": alert.severity === "MEDIUM" ? "bg-yellow-600 text-white": "bg-green-600 text-white"}`}>
                {alert.severity}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </div>
  );
};

export default AlertList;