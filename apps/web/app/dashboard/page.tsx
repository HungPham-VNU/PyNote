import { auth } from "@clerk/nextjs/server";
import { OrganizationSwitcher, UserButton } from "@clerk/nextjs";
import Link from "next/link";
import { listNotebooks } from "@/lib/api";
import { CreateNotebookForm } from "@/components/create-notebook-form";
import { NotebookCard } from "@/components/notebook-card";
import { NotebookSearch } from "@/components/notebook-search";

export default async function DashboardPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  const { q } = await searchParams;
  const query = q?.trim() ?? "";
  const { getToken } = await auth();
  const token = await getToken();
  const notebooks = await listNotebooks(token, query || undefined);

  return (
    <main className="mx-auto max-w-5xl px-6 py-10">
      <header className="mb-10 flex items-center justify-between border-b border-[#424754] pb-6">
        <Link href="/" className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#4d8eff] font-bold text-[#00285d]">
            P
          </div>
          <div>
            <h1 className="text-base font-semibold tracking-tight text-[#e5e2e3]">
              PyNote
            </h1>
            <p className="text-[10px] uppercase tracking-wider text-[#c2c6d6]">
              Workspace
            </p>
          </div>
        </Link>
        <div className="flex items-center gap-3">
          <OrganizationSwitcher hidePersonal={false} />
          <UserButton />
        </div>
      </header>

      <div className="mb-8">
        <h2 className="text-2xl font-semibold tracking-tight text-[#e5e2e3]">
          My Notebooks
        </h2>
        <p className="mt-1 text-sm text-[#c2c6d6]">
          Each notebook is a scoped workspace over a set of sources.
        </p>
      </div>

      <CreateNotebookForm />

      <div className="mt-4">
        <NotebookSearch initialQuery={query} />
      </div>

      {notebooks.length === 0 ? (
        <div className="mt-8 rounded-2xl border border-dashed border-[#424754] bg-[#1c1b1c] p-12 text-center">
          {query ? (
            <>
              <p className="text-base font-medium text-[#e5e2e3]">
                No notebooks match “{query}”.
              </p>
              <p className="mt-2 text-sm text-[#c2c6d6]">
                Try a different search, or clear it to see all notebooks.
              </p>
            </>
          ) : (
            <>
              <p className="text-base font-medium text-[#e5e2e3]">
                Create your first notebook above.
              </p>
              <p className="mt-2 text-sm text-[#c2c6d6]">
                A notebook is a scoped workspace. Add PDF sources, then ask
                grounded questions with inline citations.
              </p>
            </>
          )}
        </div>
      ) : (
        <ul className="mt-8 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {notebooks.map((n) => (
            <NotebookCard key={n.id} notebook={n} />
          ))}
        </ul>
      )}
    </main>
  );
}
