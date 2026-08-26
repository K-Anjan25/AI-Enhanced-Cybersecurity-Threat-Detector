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

export default function LoginPage() {
  const router = useRouter();
  const { login, register } = useAuth();
  const [isLoading, setIsLoading] = useState(false);

  const { register: formRegister, handleSubmit, reset } = useForm({
    resolver: zodResolver(
      z.object({
        identifier: z.string().min(1).trim(),
        password: z.string().min(1).trim(),
      })
    ),
    defaultValues: { identifier: "", password: "" },
  });

  const onSubmit = async (data: {
    identifier: string;
    password: string;
  }) => {
    setIsLoading(true);
    try {
      await login(data.identifier, data.password);
      router.push("/dashboard");
    } catch (err) {
      // Error handled by auth store toast
      reset();
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <Card className="w-full max-w-md p-8">
        <h2 className="text-2xl font-bold text-foreground mb-4">Sign in</h2>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <Input
            placeholder="Email or username"
            {...register("identifier")}
            disabled={isLoading}
            className="mb-3"
          />
          <Input
            type="password"
            placeholder="••••••••"
            {...register("password")}
            disabled={isLoading}
            className="mb-6"
          />
          <Button type="submit" disabled={isLoading} className="w-full">
            {isLoading ? "Signing in..." : "Sign In"}
          </Button>
          <p className="text-sm text-muted text-center">
            Don't have an account?{" "}
            <a href="/register" className="font-medium underline">
              Register here
            </a>
          </p>
        </form>
      </Card>
    </div>
  );
}