import Link from "next/link";
import { auth } from "@clerk/nextjs/server";
import { notFound } from "next/navigation";
import { OrganizationSwitcher, UserButton } from "@clerk/nextjs";
import { getNotebook, listSources } from "@/lib/api";
import { SourceUploader } from "@/components/source-uploader";
import { SourceList } from "@/components/source-list";

export default async function NotebookPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { getToken } = await auth();
  const token = await getToken();

  const [notebook, sources] = await Promise.all([
    getNotebook(token, id).catch(() => null),
    listSources(token, id).catch(() => []),
  ]);
  if (!notebook) notFound();

  return (
    <main className="mx-auto max-w-4xl px-6 py-10">
      <header className="mb-8 flex items-center justify-between">
        <Link href="/dashboard" className="text-sm text-neutral-500 hover:text-neutral-900">
          ← All notebooks
        </Link>
        <div className="flex items-center gap-3">
          <OrganizationSwitcher hidePersonal={false} />
          <UserButton />
        </div>
      </header>

      <h1 className="mb-6 text-xl font-semibold">{notebook.title}</h1>

      <section className="mb-8">
        <h2 className="mb-2 text-sm font-medium uppercase tracking-wide text-neutral-500">
          Add a source
        </h2>
        <SourceUploader notebookId={id} />
      </section>

      <section>
        <h2 className="mb-2 text-sm font-medium uppercase tracking-wide text-neutral-500">
          Sources
        </h2>
        <SourceList notebookId={id} initial={sources} />
      </section>
    </main>
  );
}
