"use client";
import { useParams, useRouter } from "next/navigation";
import { useEffect } from "react";

export default function TopicsPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  useEffect(() => {
    router.replace(`/projects/${params.id}/board?tab=topics`);
  }, [params.id, router]);
  return null;
}
