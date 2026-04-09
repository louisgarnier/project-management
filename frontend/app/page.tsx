"use client";

import { useEffect, useState } from "react";
import { projectsAPI } from "@/api/client";
import { logger } from "@/utils/logger";
import type { Project } from "@/types";
import ProjectList from "@/components/ProjectList";
import CreateProjectModal from "@/components/CreateProjectModal";

export default function HomePage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [showModal, setShowModal] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    logger.info("Fetching projects", { component: "HomePage" });
    projectsAPI
      .list()
      .then((data) => {
        logger.info(`Loaded ${data.length} projects`, { component: "HomePage" });
        setProjects(data);
      })
      .catch((err) => {
        logger.error("Failed to load projects", {
          component: "HomePage",
          data: err,
        });
      })
      .finally(() => setLoading(false));
  }, []);

  async function handleCreate(name: string, description: string) {
    logger.info(`Creating project: ${name}`, { component: "HomePage" });
    const project = await projectsAPI.create({ name, description });
    logger.info(`Created project: ${project.id}`, { component: "HomePage" });
    setProjects((prev) => [...prev, project]);
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <p className="text-gray-400 text-sm">Loading…</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <ProjectList projects={projects} onCreateClick={() => setShowModal(true)} />
      {showModal && (
        <CreateProjectModal
          onClose={() => setShowModal(false)}
          onCreate={handleCreate}
        />
      )}
    </div>
  );
}
