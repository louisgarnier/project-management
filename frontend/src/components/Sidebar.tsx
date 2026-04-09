"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import Link from "next/link";
import { projectsAPI } from "@/api/client";
import { logger } from "@/utils/logger";
import type { Project } from "@/types";
import CreateProjectModal from "@/components/CreateProjectModal";

const PROJECT_COLORS = [
  "#36b37e",
  "#0052cc",
  "#ff5630",
  "#6554c0",
  "#ff8b00",
  "#00b8d9",
];
const getColor = (id: string) => {
  let hash = 0;
  for (let i = 0; i < id.length; i++) hash = id.charCodeAt(i) + ((hash << 5) - hash);
  return PROJECT_COLORS[Math.abs(hash) % PROJECT_COLORS.length];
};

const NAV_ITEMS = [
  { key: "board", label: "Board", icon: "📋" },
  { key: "topics", label: "Topics", icon: "🗺️" },
  { key: "history", label: "File History", icon: "📁" },
] as const;

export default function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const [projects, setProjects] = useState<Project[]>([]);
  const [showModal, setShowModal] = useState(false);

  // Extract active project ID and section from URL
  // Matches: /projects/<id>/<section>
  const urlMatch = pathname.match(/^\/projects\/([^/]+)(?:\/([^/]+))?/);
  const activeProjectId = urlMatch?.[1] ?? null;
  const activeSection = urlMatch?.[2] ?? "board";

  useEffect(() => {
    logger.info("Fetching projects", { component: "Sidebar" });
    projectsAPI
      .list()
      .then((data) => {
        logger.info(`Loaded ${data.length} projects`, { component: "Sidebar" });
        setProjects(data);
      })
      .catch((err) => {
        logger.error("Failed to load projects", { component: "Sidebar", data: err });
      });
  }, []);

  async function handleCreate(name: string, description: string) {
    try {
      const project = await projectsAPI.create({ name, description });
      logger.info(`Created project: ${project.id}`, { component: "Sidebar" });
      setProjects((prev) => [...prev, project]);
      router.push(`/projects/${project.id}/board`);
    } catch (err) {
      logger.error("Failed to create project", { component: "Sidebar", data: err });
      throw err;
    }
  }

  const activeProject = projects.find((p) => p.id === activeProjectId) ?? null;

  return (
    <>
      <aside className="w-[220px] bg-[#f4f5f7] border-r border-[#dfe1e6] flex flex-col flex-shrink-0 overflow-y-auto">
        {/* Projects section */}
        <div className="px-3 pt-3 pb-1">
          <p className="text-[10px] font-semibold text-[#5e6c84] uppercase tracking-wider mb-2">
            Projects
          </p>

          {projects.map((project) => {
            const isActive = project.id === activeProjectId;
            return (
              <Link
                key={project.id}
                href={`/projects/${project.id}/board`}
                className={`flex items-center gap-2 px-2 py-1.5 rounded mb-0.5 text-[11px] font-medium transition-colors ${
                  isActive
                    ? "bg-[#0052cc] text-white"
                    : "text-[#172b4d] hover:bg-white"
                }`}
              >
                <span
                  className="w-[18px] h-[18px] rounded-[3px] flex-shrink-0 flex items-center justify-center text-[8px] font-bold text-white"
                  style={{ background: getColor(project.id) }}
                >
                  {project.name[0].toUpperCase()}
                </span>
                <span className="truncate">{project.name}</span>
              </Link>
            );
          })}

          <button
            onClick={() => setShowModal(true)}
            className="flex items-center gap-2 px-2 py-1.5 rounded w-full text-left text-[11px] text-[#5e6c84] hover:bg-white mt-0.5"
          >
            <span className="w-[18px] h-[18px] rounded-[3px] border-[1.5px] border-dashed border-[#b3bac5] flex items-center justify-center text-[12px] flex-shrink-0">
              +
            </span>
            New project
          </button>
        </div>

        {/* Per-project nav — shown only when on a project URL */}
        {activeProject && (
          <>
            <div className="h-px bg-[#dfe1e6] my-2 mx-3" />
            <div className="px-3 pb-3">
              <p className="text-[10px] font-semibold text-[#5e6c84] uppercase tracking-wider mb-2 truncate">
                {activeProject.name}
              </p>
              {NAV_ITEMS.map((item) => {
                const isActive = activeSection === item.key;
                return (
                  <Link
                    key={item.key}
                    href={`/projects/${activeProjectId}/${item.key}`}
                    className={`flex items-center gap-2 px-2 py-1.5 rounded mb-0.5 text-[11px] transition-colors ${
                      isActive
                        ? "bg-[#e3f2fd] text-[#0052cc] font-semibold"
                        : "text-[#172b4d] hover:bg-white"
                    }`}
                  >
                    <span>{item.icon}</span>
                    <span>{item.label}</span>
                  </Link>
                );
              })}
            </div>
          </>
        )}
      </aside>

      {showModal && (
        <CreateProjectModal
          onClose={() => setShowModal(false)}
          onCreate={handleCreate}
        />
      )}
    </>
  );
}
