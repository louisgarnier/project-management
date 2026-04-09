export default async function ProjectPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  return (
    <div className="min-h-screen bg-gray-50 py-10 px-4">
      <div className="max-w-2xl mx-auto">
        <p className="text-xs text-gray-400 font-mono mb-2">{id}</p>
        <h1 className="text-2xl font-bold text-gray-900">Project</h1>
        <p className="text-gray-500 mt-2 text-sm">
          Calls and artifacts coming in EPIC-3.
        </p>
      </div>
    </div>
  );
}
