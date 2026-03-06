import React, { useState } from "react";
import { registerUser } from "../services/api";
import axios from "axios";
function Register({ switchToLogin }) {
    const [form, setForm] = useState({
        username: "",
        password: "",
        email: "",
        role: "analyst",
        company_id: 1,
    });

    const handleChange = (e) => {
        setForm({
            ...form,
            [e.target.name]: e.target.value
        });
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        try {
            await axios.post("http://localhost:8000/register", form, {
                headers: {
                    "Content-Type": "application/json"
                }
            });

            alert("Registration successful! Please login.");
        } catch (err) {
            alert(err.response?.data?.detail || "Error registering user");
        }
    };

    return (
        <div className="flex justify-center items-center h-screen">
      <form onSubmit={handleSubmit} className="bg-white p-6 rounded shadow-md w-80">
        <h2 className="text-xl mb-4">Register</h2>

        <input
          type="text"
          name="username"
          placeholder="Username"
          className="w-full mb-3 p-2 border"
          onChange={handleChange}
          required
        />

        <input
          type="email"
          name="email"
          placeholder="Email"
          className="w-full mb-3 p-2 border"
          onChange={handleChange}
          required
        />

        <input
          type="password"
          name="password"
          placeholder="Password"
          className="w-full mb-3 p-2 border"
          onChange={handleChange}
          required
        />
                
        <input
          type="text"
          name="role"
          placeholder="Role"
          className="w-full mb-3 p-2 border"
          onChange={handleChange}
          required
        />

        <button
          type="submit"
          className="w-full bg-blue-600 text-white p-2 rounded"
        >
          Register
          </button>
          <p className="text-sm text-center mt-4">
            Already have an account?{" "}
            <button
              type="button"
              className="text-blue-600 hover:underline"
              onClick={switchToLogin}
            >
            Login
            </button>
          </p>
      </form>
    </div>
  );
}

export default Register;