import Link from "next/link";
import { auth } from "@clerk/nextjs/server";
import { notFound } from "next/navigation";
import { OrganizationSwitcher, UserButton } from "@clerk/nextjs";
import { getNotebook, listSources } from "@/lib/api";
import { SourceUploader } from "@/components/source-uploader";
import { SourceList } from "@/components/source-list";
import { ChatPanel } from "@/components/chat-panel";
import { SuggestedQuestions } from "@/components/suggested-questions";
import { SummaryButton } from "@/components/summary-button";

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

  const hasReadySource = sources.some((s) => s.status === "ready");
  const readyCount = sources.filter((s) => s.status === "ready").length;

  return (
    <div className="flex min-h-screen flex-col">
      {/* ---- Top bar ----------------------------------------------------- */}
      <header className="flex items-center justify-between border-b border-[#424754] bg-[#1c1b1c] px-6 py-3">
        <div className="flex items-center gap-3">
          <Link href="/dashboard" className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#4d8eff] font-bold text-[#00285d]">
              P
            </div>
            <div>
              <p className="text-sm font-semibold text-[#e5e2e3]">PyNote</p>
              <p className="text-[10px] uppercase tracking-wider text-[#c2c6d6]">
                Workspace
              </p>
            </div>
          </Link>
          <nav className="ml-6 hidden items-center gap-2 md:flex">
            <Link
              href="/dashboard"
              className="rounded-lg px-3 py-1.5 text-sm font-medium text-[#c2c6d6] hover:bg-[#2a2a2b] hover:text-[#e5e2e3]"
            >
              Notebooks
            </Link>
            <span className="rounded-lg bg-[#2a2a2b] px-3 py-1.5 text-sm font-semibold text-[#adc6ff]">
              {notebook.title}
            </span>
          </nav>
        </div>
        <div className="flex items-center gap-3">
          <OrganizationSwitcher hidePersonal={false} />
          <UserButton />
        </div>
      </header>

      {/* ---- 2-column workspace ----------------------------------------- */}
      <div className="grid flex-1 gap-0 lg:grid-cols-[340px_1fr]">
        {/* Sidebar — sources + uploader */}
        <aside className="flex flex-col gap-6 border-r border-[#424754] bg-[#1c1b1c] p-5">
          <div>
            <div className="mb-2 flex items-center gap-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#adc6ff]/20 text-[#adc6ff]">
                📚
              </div>
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-[#e5e2e3]">
                  {notebook.title}
                </p>
                <p className="text-xs text-[#c2c6d6]">
                  {readyCount}/{sources.length} source
                  {sources.length === 1 ? "" : "s"} ready
                </p>
              </div>
            </div>
          </div>

          <section>
            <h2 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-[#c2c6d6]">
              Add a Source
            </h2>
            <SourceUploader notebookId={id} />
          </section>

          <section className="flex-1">
            <h2 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-[#c2c6d6]">
              Sources
            </h2>
            <SourceList notebookId={id} initial={sources} />
          </section>
        </aside>

        {/* Main — summary + chat */}
        <section className="flex flex-col gap-6 bg-[#131314] p-6">
          {/* Summary card */}
          <div className="rounded-2xl border border-[#424754] bg-[#1c1b1c] p-5">
            <div className="mb-3 flex items-center justify-between">
              <div>
                <h2 className="text-base font-semibold text-[#e5e2e3]">
                  Notebook Summary
                </h2>
                <p className="text-xs text-[#c2c6d6]">
                  Single-shot artifact across all ready sources.
                </p>
              </div>
            </div>
            <SummaryButton
              notebookId={id}
              hasReadySource={hasReadySource}
            />
          </div>

          {/* Chat card */}
          <div className="flex flex-1 flex-col rounded-2xl border border-[#424754] bg-[#1c1b1c]">
            <header className="flex items-center justify-between border-b border-[#424754] px-5 py-3">
              <div className="flex items-center gap-2">
                <div className="flex h-7 w-7 items-center justify-center rounded-full bg-[#4d8eff]/20 text-[#adc6ff]">
                  ✦
                </div>
                <h2 className="text-sm font-semibold text-[#e5e2e3]">
                  Research Assistant
                </h2>
              </div>
              <p className="text-[10px] uppercase tracking-wider text-[#c2c6d6]">
                Citations Live
              </p>
            </header>

            <div className="px-5 pt-3">
              <SuggestedQuestions sources={sources} />
            </div>

            <div className="flex-1 px-5 pb-5 pt-3">
              <ChatPanel
                notebookId={id}
                hasReadySource={hasReadySource}
              />
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
