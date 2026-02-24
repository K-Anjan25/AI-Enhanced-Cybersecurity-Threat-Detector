import { PieChart, Pie, Cell, Tooltip } from "recharts";
import react, { useEffect, useState } from "react";
import { fetchAlerts } from "./services/api";

function AlertChart() {
  const [alerts, setAlerts] = useState([]);

  useEffect(() => {
    const loadAlerts = async () => {
      const data = await fetchAlerts();
      setAlerts(data);
    };

    loadAlerts();
  }, []);

    const data = [
    { name: "Critical", value: alerts.filter(a => a.severity === "CRITICAL").length },
    { name: "High", value: alerts.filter(a => a.severity === "HIGH").length },
    { name: "Medium", value: alerts.filter(a => a.severity === "MEDIUM").length },
    { name: "Low", value: alerts.filter(a => a.severity === "LOW").length },
  ];

  const COLORS = ["#dc2626", "#ef4444", "#facc15", "#22c55e"];

  return (
    <PieChart width={300} height={300}>
      <Pie data={data} dataKey="value" outerRadius={100}>
        {data.map((entry, index) => (
          <Cell key={index} fill={COLORS[index]} />
        ))}
      </Pie>
      <Tooltip />
    </PieChart>
  );
}

export default AlertChart;