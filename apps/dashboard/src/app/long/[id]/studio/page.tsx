import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { Studio } from "@/components/long/studio";
import { getLongDetail } from "@/lib/long";
import { allParagraphs, titleOf } from "@/lib/long-types";

export const metadata: Metadata = { title: "Studio voix" };
export const dynamic = "force-dynamic";

/** Studio voix (docs/63 §4) : Luca lit le script au micro, paragraphe par paragraphe. */
export default async function StudioPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const data = await getLongDetail(id);
  if (!data || !data.video.script) notFound();
  const v = data.video;
  const paragraphs = allParagraphs(v.script).map((p) => ({ key: p.key, text: p.text, chapter: p.chapter, chapterTitle: p.chapterTitle }));
  return (
    <Studio
      id={v.id}
      title={titleOf(v)}
      paragraphs={paragraphs}
      initial={{ stage: v.stage, voice_done_at: v.voice_done_at, error: v.error, takes: data.takes, jobs: data.jobs }}
    />
  );
}
