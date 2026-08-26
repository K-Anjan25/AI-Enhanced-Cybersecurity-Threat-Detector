"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { auth } from "@/lib/api";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Card } from "@/components/ui/Card";
import { useAuth } from "@/store/userStore";

export default function RegisterPage() {
  const router = useRouter();
  const { register: doRegister } = useAuth();
  const [isLoading, setIsLoading] = useState(false);

  const { register: formRegister, handleSubmit, reset } = useForm({
    resolver: zodResolver(
      z.object({
        username: z.string().min(3).trim(),
        email: z.string().email().trim(),
        password: z.string().min(6).trim(),
      })
    ),
    defaultValues: { username: "", email: "", password: "" },
  });

  const onSubmit = async (data: {
    username: string;
    email: string;
    password: string;
  }) => {
    setIsLoading(true);
    try {
      await doRegister(data.username, data.email, data.password);
      router.push("/login");
    } catch (err) {
      // Error handled by auth store
      reset();
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <Card className="w-full max-w-md p-8">
        <h2 className="text-2xl font-bold text-foreground mb-4">Create account</h2>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <Input
            placeholder="Username"
            {...formRegister("username")}
            disabled={isLoading}
            className="mb-3"
          />
          <Input
            type="email"
            placeholder="you@example.com"
            {...formRegister("email")}
            disabled={isLoading}
            className="mb-3"
          />
          <Input
            type="password"
            placeholder="•••••••••••••"
            {...formRegister("password")}
            disabled={isLoading}
            className="mb-6"
          />
          <Button type="submit" disabled={isLoading} className="w-full">
            {isLoading ? "Creating..." : "Create Account"}
          </Button>
          <p className="text-sm text-muted text-center">
            Already have an account?{" "}
            <a href="/login" className="font-medium underline">
              Sign in
            </a>
          </p>
        </form>
      </Card>
    </div>
  );
}