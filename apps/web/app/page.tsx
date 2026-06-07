import Link from "next/link";
import type { ReactNode } from "react";
import { SignedIn, SignedOut, UserButton } from "@clerk/nextjs";

export default function Home() {
  return (
    <main className="min-h-[100dvh] bg-[#131314] text-[#e5e2e3]">
      {/* ─────────────── Header ─────────────── */}
      <header className="border-b border-[#2a2a2b]">
        <div className="mx-auto flex max-w-[1280px] items-center justify-between px-6 py-5">
          <Link href="/" className="flex items-center gap-3">
            <BrandMark />
            <div className="hidden sm:block">
              <p className="text-sm font-semibold leading-none text-[#e5e2e3]">
                PyNote
              </p>
              <p className="mt-1.5 font-mono text-[10px] uppercase leading-none tracking-[0.18em] text-[#8c909f]">
                Research workspace
              </p>
            </div>
          </Link>
          <SignedIn>
            <div className="flex items-center gap-5">
              <Link
                href="/dashboard"
                className="text-sm text-[#c2c6d6] transition-colors hover:text-[#adc6ff]"
              >
                Open workspace
              </Link>
              <UserButton />
            </div>
          </SignedIn>
          <SignedOut>
            <Link
              href="/sign-in"
              className="text-sm text-[#c2c6d6] transition-colors hover:text-[#adc6ff]"
            >
              Sign in
            </Link>
          </SignedOut>
        </div>
      </header>

      {/* ─────────────── Hero (asymmetric split) ─────────────── */}
      <section className="border-b border-[#2a2a2b]">
        <div className="mx-auto max-w-[1280px] px-6 pt-16 pb-20 lg:pt-24 lg:pb-28">
          <div className="grid items-center gap-12 lg:grid-cols-[1.05fr_1fr]">
            <div>
              <h1 className="text-4xl font-semibold leading-[1.05] tracking-tight text-[#e5e2e3] md:text-5xl lg:text-[64px]">
                Every answer
                <br />
                <span className="text-[#adc6ff]">points back</span> to the
                source.
              </h1>
              <p className="mt-7 max-w-[58ch] text-base leading-relaxed text-[#c2c6d6] md:text-lg">
                Upload PDFs, ask grounded questions, and click any citation to
                land on the exact span in the source.
              </p>

              <SignedOut>
                <div className="mt-10 flex flex-wrap gap-3">
                  <Link
                    href="/sign-up"
                    className="rounded-xl bg-[#4d8eff] px-6 py-3 text-sm font-semibold text-[#00285d] transition-colors hover:bg-[#adc6ff] active:translate-y-[1px]"
                  >
                    Create account
                  </Link>
                  <Link
                    href="/sign-in"
                    className="rounded-xl border border-[#424754] px-6 py-3 text-sm font-medium text-[#e5e2e3] transition-colors hover:border-[#8c909f] hover:bg-[#1c1b1c] active:translate-y-[1px]"
                  >
                    Sign in
                  </Link>
                </div>
              </SignedOut>

              <SignedIn>
                <div className="mt-10">
                  <Link
                    href="/dashboard"
                    className="inline-flex items-center gap-2 rounded-xl bg-[#4d8eff] px-6 py-3 text-sm font-semibold text-[#00285d] transition-colors hover:bg-[#adc6ff] active:translate-y-[1px]"
                  >
                    Open your workspace
                    <span aria-hidden>→</span>
                  </Link>
                </div>
              </SignedIn>
            </div>

            <CitationPreview />
          </div>
        </div>
      </section>

      {/* ─────────────── The grounding mechanic (2-up compare) ─────────────── */}
      <section className="border-b border-[#2a2a2b]">
        <div className="mx-auto max-w-[1280px] px-6 py-20 lg:py-28">
          <div className="max-w-[680px]">
            <h2 className="text-2xl font-semibold leading-tight tracking-tight text-[#e5e2e3] md:text-3xl lg:text-4xl">
              An LLM hallucinates.{" "}
              <span className="text-[#fcd34d]">A citation cannot.</span>
            </h2>
            <p className="mt-5 max-w-[60ch] text-base leading-relaxed text-[#c2c6d6]">
              PyNote validates every citation against the original chunk text
              using Anthropic&apos;s Citations API. If the model invents an
              offset, the pill flags it.
            </p>
          </div>

          <div className="mt-12 grid gap-6 lg:grid-cols-2">
            <ComparisonCard
              label="A typical assistant"
              question="What does the paper say about training stability?"
              answer={
                <>
                  The paper discusses training stability through various
                  techniques like learning rate scheduling and gradient
                  clipping, which are common approaches in modern deep
                  learning.
                </>
              }
              issue="No source attached. No way to verify a single claim."
            />
            <ComparisonCard
              label="PyNote"
              question="What does the paper say about training stability?"
              answer={
                <>
                  Training stability is addressed through gradient clipping at
                  norm 1.0
                  <Pill index={1} /> and a cosine learning-rate schedule with
                  linear warmup
                  <Pill index={2} />.
                </>
              }
              evidence={[
                {
                  page: 7,
                  quote:
                    "We clip gradients globally at norm 1.0 across all parameters to prevent training divergence in the early steps.",
                },
                {
                  page: 11,
                  quote:
                    "Learning rate follows a cosine schedule with 2000 warmup steps reaching peak 3e-4.",
                },
              ]}
            />
          </div>
        </div>
      </section>

      {/* ─────────────── The stack (asymmetric text + bento) ─────────────── */}
      <section className="border-b border-[#2a2a2b]">
        <div className="mx-auto max-w-[1280px] px-6 py-20 lg:py-28">
          <div className="grid gap-12 lg:grid-cols-[1fr_1.4fr]">
            <div>
              <h2 className="text-2xl font-semibold leading-tight tracking-tight text-[#e5e2e3] md:text-3xl lg:text-4xl">
                Built like a
                <br />
                research tool.
              </h2>
              <p className="mt-5 max-w-[40ch] text-base leading-relaxed text-[#c2c6d6]">
                Every layer is chosen so the citation roundtrip survives the
                trip from source to answer.
              </p>
            </div>

            <div className="grid gap-px overflow-hidden rounded-2xl border border-[#2a2a2b] bg-[#2a2a2b] sm:grid-cols-2">
              <StackTile
                value="384-d"
                label="BGE embeddings"
                body="Hybrid retrieval over pgvector + tsvector, fused with RRF in a single SQL CTE."
              />
              <StackTile
                value="LangGraph"
                label="Stateful chat"
                body="AsyncPostgresSaver checkpoints conversation per thread. Refresh restores history."
              />
              <StackTile
                value="char-level"
                label="Citation roundtrip"
                body={
                  <>
                    Every{" "}
                    <code className="font-mono text-[#adc6ff]">
                      cited_text
                    </code>{" "}
                    from Anthropic is sliced from the chunk and verified
                    against the source.
                  </>
                }
              />
              <StackTile
                value="60 / 60"
                label="Tests passing"
                body="Pure-function chunker, citation parser, and metric helpers are all hermetic."
              />
            </div>
          </div>
        </div>
      </section>

      {/* ─────────────── Final CTA (panel) ─────────────── */}
      <section>
        <div className="mx-auto max-w-[1280px] px-6 py-20 lg:py-28">
          <div className="overflow-hidden rounded-3xl border border-[#2a2a2b] bg-gradient-to-br from-[#1c1b1c] via-[#1c1b1c] to-[#131314] p-10 lg:p-16">
            <h2 className="max-w-[20ch] text-3xl font-semibold leading-tight tracking-tight text-[#e5e2e3] md:text-4xl lg:text-5xl">
              Start asking grounded questions.
            </h2>
            <p className="mt-5 max-w-[60ch] text-base leading-relaxed text-[#c2c6d6]">
              Bring your own Anthropic key. Five dollars of free credit covers
              thousands of citations.
            </p>

            <SignedOut>
              <div className="mt-10 flex flex-wrap items-center gap-5">
                <Link
                  href="/sign-up"
                  className="rounded-xl bg-[#4d8eff] px-6 py-3 text-sm font-semibold text-[#00285d] transition-colors hover:bg-[#adc6ff] active:translate-y-[1px]"
                >
                  Create account
                </Link>
                <Link
                  href="/sign-in"
                  className="text-sm text-[#c2c6d6] underline-offset-4 transition-colors hover:text-[#adc6ff] hover:underline"
                >
                  Already have one? Sign in
                </Link>
              </div>
            </SignedOut>

            <SignedIn>
              <div className="mt-10">
                <Link
                  href="/dashboard"
                  className="inline-flex items-center gap-2 rounded-xl bg-[#4d8eff] px-6 py-3 text-sm font-semibold text-[#00285d] transition-colors hover:bg-[#adc6ff] active:translate-y-[1px]"
                >
                  Open your workspace
                  <span aria-hidden>→</span>
                </Link>
              </div>
            </SignedIn>
          </div>
        </div>
      </section>

      {/* ─────────────── Footer ─────────────── */}
      <footer className="border-t border-[#2a2a2b]">
        <div className="mx-auto flex max-w-[1280px] flex-col items-start gap-3 px-6 py-8 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <BrandMark size="sm" />
            <p className="text-sm font-medium text-[#e5e2e3]">PyNote</p>
            <p className="font-mono text-[11px] text-[#8c909f]">MIT</p>
          </div>
          <p className="font-mono text-[11px] text-[#8c909f]">
            Postgres + pgvector / LangGraph / Anthropic / react-pdf
          </p>
        </div>
      </footer>
    </main>
  );
}

/* ───────────────────────── sub-components ───────────────────────── */

function BrandMark({ size = "md" }: { size?: "sm" | "md" }) {
  const dims = size === "sm" ? "h-7 w-7" : "h-9 w-9";
  const textSize = size === "sm" ? "text-xs" : "text-sm";
  return (
    <div
      aria-hidden
      className={`flex ${dims} items-center justify-center rounded-lg bg-gradient-to-br from-[#4d8eff] to-[#adc6ff] font-bold text-[#00285d] ${textSize}`}
    >
      P
    </div>
  );
}

function Pill({ index }: { index: number }) {
  return (
    <span className="mx-0.5 inline-flex items-center rounded-md bg-[#4d8eff]/30 px-1.5 align-baseline text-[10px] font-semibold text-[#adc6ff]">
      [{index}]
    </span>
  );
}

function ComparisonCard({
  label,
  question,
  answer,
  issue,
  evidence,
}: {
  label: string;
  question: string;
  answer: ReactNode;
  issue?: string;
  evidence?: { page: number; quote: string }[];
}) {
  const borderTone = evidence
    ? "border-[#4d8eff]/40"
    : "border-[#2a2a2b]";
  return (
    <div className={`rounded-2xl border ${borderTone} bg-[#1c1b1c] p-6`}>
      <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-[#8c909f]">
        {label}
      </p>
      <p className="mt-4 text-xs italic text-[#8c909f]">{question}</p>
      <div className="mt-3 rounded-xl bg-[#131314] p-4 text-sm leading-relaxed text-[#e5e2e3]">
        {answer}
      </div>
      {issue && (
        <p className="mt-4 text-xs leading-relaxed text-[#fca5a5]">{issue}</p>
      )}
      {evidence && (
        <div className="mt-4 space-y-2">
          {evidence.map((e, i) => (
            <div
              key={i}
              className="rounded-lg border border-[#424754] bg-[#131314] p-3"
            >
              <p className="font-mono text-[10px] uppercase tracking-wider text-[#8c909f]">
                Source / page {e.page}
              </p>
              <p className="mt-1.5 text-xs leading-relaxed text-[#c2c6d6]">
                <span className="bg-[#fcd34d]/25 px-1 py-0.5 text-[#e5e2e3]">
                  {e.quote}
                </span>
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function StackTile({
  value,
  label,
  body,
}: {
  value: string;
  label: ReactNode;
  body: ReactNode;
}) {
  return (
    <div className="bg-[#131314] p-6 transition-colors hover:bg-[#1c1b1c]">
      <p className="font-mono text-2xl font-medium leading-none tracking-tight text-[#adc6ff]">
        {value}
      </p>
      <p className="mt-3 text-sm font-semibold text-[#e5e2e3]">{label}</p>
      <p className="mt-2 text-xs leading-relaxed text-[#c2c6d6]">{body}</p>
    </div>
  );
}

function CitationPreview() {
  return (
    <div className="relative">
      {/* Assistant answer card */}
      <div className="rounded-2xl border border-[#2a2a2b] bg-[#1c1b1c] p-5 shadow-2xl shadow-black/40">
        <div className="mb-3 flex items-center gap-2">
          <div
            aria-hidden
            className="flex h-6 w-6 items-center justify-center rounded-full bg-[#4d8eff]/20 text-[#adc6ff]"
          >
            ✦
          </div>
          <p className="text-xs font-semibold text-[#e5e2e3]">
            Research assistant
          </p>
        </div>
        <p className="text-sm leading-relaxed text-[#e5e2e3]">
          Backpropagation computes gradients via the chain rule applied layer
          by layer
          <Pill index={1} />, with the cost averaged over the training batch
          <Pill index={2} />.
        </p>
      </div>

      {/* Linked source preview */}
      <div className="mt-3 rounded-2xl border border-[#fcd34d]/20 bg-[#1c1b1c] p-5">
        <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-[#fcd34d]">
          Source / page 18
        </p>
        <p className="mt-3 text-sm leading-relaxed text-[#c2c6d6]">
          ...the cost is averaged over the training batch.{" "}
          <span className="bg-[#fcd34d]/25 px-1 py-0.5 text-[#e5e2e3]">
            Backpropagation applies the chain rule layer by layer
          </span>
          , giving exact gradients with respect to every weight.
        </p>
      </div>
    </div>
  );
}
