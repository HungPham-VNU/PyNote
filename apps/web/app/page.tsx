import Link from "next/link";
import { SignedIn, SignedOut, UserButton } from "@clerk/nextjs";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-8 px-6 py-16">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">PyNote</h1>
        <SignedIn>
          <UserButton />
        </SignedIn>
      </header>

      <section className="space-y-4">
        <p className="text-lg text-neutral-700">
          A NotebookLM-style RAG application. Upload sources, ask grounded
          questions, get inline citations that jump to the source span.
        </p>

        <SignedOut>
          <div className="flex gap-3">
            <Link
              href="/sign-in"
              className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-800"
            >
              Sign in
            </Link>
            <Link
              href="/sign-up"
              className="rounded-md border border-neutral-300 px-4 py-2 text-sm font-medium hover:bg-neutral-100"
            >
              Create account
            </Link>
          </div>
        </SignedOut>

        <SignedIn>
          <Link
            href="/dashboard"
            className="inline-block rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-800"
          >
            Go to dashboard →
          </Link>
        </SignedIn>
      </section>

      <footer className="mt-auto text-xs text-neutral-500">
        Milestone 0 — foundation. See PLAN.md and COSTS.md.
      </footer>
    </main>
  );
}
