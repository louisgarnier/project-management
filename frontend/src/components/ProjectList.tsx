"use client";

import type { Project } from "@/types";
import Link from "next/link";

type Props = {
  projects: Project[];
  onCreateClick: () => void;
};

export default function ProjectList({ projects, onCreateClick }: Props) {
  return (
    <div className="max-w-2xl mx-auto py-10 px-4">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Projects</h1>
        <button
          onClick={onCreateClick}
          className="bg-blue-600 text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-blue-700"
        >
          New Project
        </button>
      </div>

      {projects.length === 0 ? (
        <p className="text-gray-500 text-sm">
          No projects yet — create your first one.
        </p>
      ) : (
        <ul className="space-y-3">
          {projects.map((project) => (
            <li key={project.id}>
              <Link
                href={`/projects/${project.id}`}
                className="block border border-gray-200 rounded-md p-4 hover:bg-gray-50"
              >
                <p className="font-medium text-gray-900">{project.name}</p>
                {project.description && (
                  <p className="text-sm text-gray-500 mt-1">
                    {project.description}
                  </p>
                )}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
