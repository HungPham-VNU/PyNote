import { auth } from "@clerk/nextjs/server";
import { OrganizationSwitcher, UserButton } from "@clerk/nextjs";
import { listNotebooks } from "@/lib/api";
import { CreateNotebookForm } from "@/components/create-notebook-form";

export default async function DashboardPage() {
  const { getToken, orgId } = await auth();

  if (!orgId) {
    return (
      <main className="mx-auto max-w-3xl px-6 py-16">
        <p className="text-neutral-700">
          You need to be in an organization to use PyNote.
        </p>
        <div className="mt-4">
          <OrganizationSwitcher
            createOrganizationMode="modal"
            hidePersonal={false}
          />
        </div>
      </main>
    );
  }

  const token = await getToken();
  const notebooks = await listNotebooks(token);

  return (
    <main className="mx-auto max-w-4xl px-6 py-10">
      <header className="mb-8 flex items-center justify-between">
        <h1 className="text-xl font-semibold">Notebooks</h1>
        <div className="flex items-center gap-3">
          <OrganizationSwitcher hidePersonal={false} />
          <UserButton afterSignOutUrl="/" />
        </div>
      </header>

      <CreateNotebookForm />

      <ul className="mt-8 divide-y divide-neutral-200 rounded-md border border-neutral-200 bg-white">
        {notebooks.length === 0 && (
          <li className="px-4 py-6 text-sm text-neutral-500">
            No notebooks yet. Create one above.
          </li>
        )}
        {notebooks.map((n) => (
          <li key={n.id} className="px-4 py-3 text-sm">
            <span className="font-medium">{n.title}</span>
            <span className="ml-2 text-neutral-500">{n.id}</span>
          </li>
        ))}
      </ul>
    </main>
  );
}
