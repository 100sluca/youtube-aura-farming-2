/**
 * Source de données factice — DÉTERMINISTE.
 *
 * Tout est dérivé d'une graine fixe (mulberry32) et de la date d'ancrage
 * `NOW` (2026-09-19T12:00:00Z) : le rendu serveur et le rendu client
 * produisent exactement les mêmes données.
 */
import type {
  Alert,
  Channel,
  ChannelMetricsDaily,
  Concept,
  DailyViewsPoint,
  Job,
  JobStatus,
  JobType,
  OverviewKpis,
  Production,
  ProductionCard,
  ProductionStatus,
  RetentionPoint,
  ScheduleSlot,
  ScriptScene,
  ScriptV1,
  Video,
  VideoFormat,
  VideoMetricsDaily,
  VideoOverview,
  VideoStatus,
} from "@/lib/types";
import {
  NOW,
  parisAddDays,
  parisDayKey,
  parisSlot,
  parisStartOfDay,
  toParisWallClock,
} from "@/lib/format";
import type {
  ChannelFilter,
  DataSource,
  ExperimentSummary,
  VideoComment,
  VideoDetail,
} from "./contract";
import { between, hashSeed, int, mulberry32, pick, type Rng, uuid, youtubeId } from "./seed";

/* ------------------------------------------------------------------------ */
/* Constantes                                                                */
/* ------------------------------------------------------------------------ */

const SLOTS = ["09:00", "13:00", "18:00"];
const DAY_MS = 86_400_000;
const TODAY = parisStartOfDay(NOW);

const day = (offset: number) => parisAddDays(TODAY, offset);
const slotAt = (dayOffset: number, slot: string) => parisSlot(day(dayOffset), slot);
const minutesAgo = (m: number) => new Date(NOW.getTime() - m * 60_000);
const iso = (d: Date) => d.toISOString();

const CHANNELS: Channel[] = [
  {
    id: "c0a1f7d2-0f4e-4a4b-9c1a-000000000001",
    slug: "fr",
    name: "Chaîne FR",
    lang: "fr",
    youtube_channel_id: "UCf3Kq9vB2xL8mN0pQ7rS4tW",
    timezone: "Europe/Paris",
    publish_slots: SLOTS,
    auto_publish: true,
    is_active: true,
  },
  {
    id: "c0a1f7d2-0f4e-4a4b-9c1a-000000000002",
    slug: "en",
    name: "Channel EN",
    lang: "en",
    youtube_channel_id: null,
    timezone: "Europe/Paris",
    publish_slots: SLOTS,
    auto_publish: false,
    is_active: true,
  },
];

const channelBySlug = (slug: string) => CHANNELS.find((c) => c.slug === slug)!;

interface Theme {
  category: string;
  /** Multiplicateur d'audience de la thématique. */
  pull: number;
  subject: { fr: string; en: string };
  titles: { fr: string[]; en: string[] };
  hook: { fr: string; en: string };
}

const THEMES: Theme[] = [
  {
    category: "secret_passages",
    pull: 1.8,
    subject: { fr: "le passage secret", en: "the secret passage" },
    titles: {
      fr: [
        "Le passage secret caché derrière la bibliothèque",
        "3 rangements cachés que personne ne remarque",
        "La trappe invisible sous le tapis du salon",
      ],
      en: [
        "The secret passage hidden behind the bookcase",
        "3 hidden storage spots nobody notices",
        "The invisible trapdoor under the living room rug",
      ],
    },
    hook: { fr: "Personne ne devine ce qui se cache derrière ce mur.", en: "Nobody guesses what is hidden behind this wall." },
  },
  {
    category: "space_optimization",
    pull: 1.3,
    subject: { fr: "la porte de garde-manger invisible", en: "the invisible pantry door" },
    titles: {
      fr: [
        "La porte de garde-manger totalement invisible",
        "Ce mur de cuisine cache un garde-manger entier",
        "Un garde-manger caché dans 40 cm de mur",
      ],
      en: [
        "The completely invisible pantry door",
        "This kitchen wall hides an entire pantry",
        "A hidden pantry inside a 16-inch wall",
      ],
    },
    hook: { fr: "Cette cuisine cache une pièce entière.", en: "This kitchen hides an entire room." },
  },
  {
    category: "pool",
    pull: 1.5,
    subject: { fr: "la piscine transformée", en: "the transformed pool" },
    titles: {
      fr: [
        "Piscine abandonnée → oasis en 60 secondes",
        "Ils ont transformé cette piscine en salon extérieur",
        "Le fond de piscine qui monte pour devenir une terrasse",
      ],
      en: [
        "Abandoned pool → oasis in 60 seconds",
        "They turned this pool into an outdoor lounge",
        "The pool floor that rises to become a deck",
      ],
    },
    hook: { fr: "Attendez de voir le fond de la piscine bouger.", en: "Wait until you see the pool floor move." },
  },
  {
    category: "container",
    pull: 1.4,
    subject: { fr: "le container enterré", en: "the buried container" },
    titles: {
      fr: [
        "Un container enterré sous le jardin",
        "Le bunker de jardin fait avec un container",
        "Container enterré : la cave secrète du jardin",
      ],
      en: [
        "A shipping container buried under the garden",
        "The backyard bunker made from a container",
        "Buried container: the garden’s secret cellar",
      ],
    },
    hook: { fr: "Sous cette pelouse : 30 m² cachés.", en: "Under this lawn: 320 hidden square feet." },
  },
  {
    category: "hidden_cinema",
    pull: 1.7,
    subject: { fr: "le cinéma caché", en: "the hidden cinema" },
    titles: {
      fr: [
        "Le cinéma caché derrière la bibliothèque",
        "Cette bibliothèque s’ouvre sur une salle de cinéma",
        "Un home cinéma secret derrière les livres",
      ],
      en: [
        "The cinema hidden behind the bookcase",
        "This bookcase opens into a movie theater",
        "A secret home theater behind the books",
      ],
    },
    hook: { fr: "Tirez sur le bon livre…", en: "Pull the right book…" },
  },
  {
    category: "slat_wall",
    pull: 1.1,
    subject: { fr: "le mur de tasseaux", en: "the slat wall" },
    titles: {
      fr: [
        "Mur acoustique en tasseaux + LED en 60 s",
        "Le mur de tasseaux qui change tout le salon",
        "Tasseaux + LED : le mur qui absorbe le bruit",
      ],
      en: [
        "Acoustic slat wall + LED in 60 seconds",
        "The slat wall that transforms the whole living room",
        "Slats + LED: the wall that absorbs noise",
      ],
    },
    hook: { fr: "Un mur qui fait taire la pièce.", en: "A wall that silences the room." },
  },
  {
    category: "smart_furniture",
    pull: 1.2,
    subject: { fr: "le bureau motorisé", en: "the motorized desk" },
    titles: {
      fr: [
        "Le bureau motorisé qui disparaît dans le mur",
        "Ce bureau se range tout seul au plafond",
        "Bureau motorisé : 2 m² gagnés en 5 secondes",
      ],
      en: [
        "The motorized desk that disappears into the wall",
        "This desk stores itself in the ceiling",
        "Motorized desk: 20 sq ft gained in 5 seconds",
      ],
    },
    hook: { fr: "Un bouton, et le bureau n’existe plus.", en: "One button and the desk is gone." },
  },
  {
    category: "office_pod",
    pull: 1.0,
    subject: { fr: "le pod bureau", en: "the office pod" },
    titles: {
      fr: [
        "Le pod bureau au fond du jardin",
        "Un bureau de jardin monté en une journée",
        "Le pod de jardin qui remplace le télétravail au salon",
      ],
      en: [
        "The office pod at the end of the garden",
        "A garden office built in one day",
        "The garden pod that replaces working from the couch",
      ],
    },
    hook: { fr: "Le télétravail, mais à 12 m de la maison.", en: "Remote work, 40 feet from the house." },
  },
  {
    category: "concrete_epoxy",
    pull: 1.2,
    subject: { fr: "l’îlot béton et époxy", en: "the concrete and epoxy island" },
    titles: {
      fr: [
        "Îlot de cuisine en béton et époxy",
        "Le plan de travail béton + époxy qui brille",
        "Îlot béton coulé sur place : le résultat",
      ],
      en: [
        "Concrete and epoxy kitchen island",
        "The concrete + epoxy countertop that glows",
        "Poured-in-place concrete island: the result",
      ],
    },
    hook: { fr: "Du béton brut… et une rivière d’époxy.", en: "Raw concrete… and a river of epoxy." },
  },
  {
    category: "under_stairs",
    pull: 1.4,
    subject: { fr: "la cave à vin sous l’escalier", en: "the wine cellar under the stairs" },
    titles: {
      fr: [
        "La cave à vin cachée sous l’escalier",
        "Sous cet escalier : 200 bouteilles",
        "L’escalier qui cache une cave à vin",
      ],
      en: [
        "The wine cellar hidden under the stairs",
        "Under these stairs: 200 bottles",
        "The staircase that hides a wine cellar",
      ],
    },
    hook: { fr: "Chaque marche cache quelque chose.", en: "Every step hides something." },
  },
  {
    category: "ceiling_storage",
    pull: 1.1,
    subject: { fr: "le rangement plafond motorisé", en: "the motorized ceiling storage" },
    titles: {
      fr: [
        "Le rangement motorisé qui descend du plafond",
        "Tout le garage rangé au plafond",
        "Rangement plafond motorisé : 4 m² récupérés",
      ],
      en: [
        "The motorized storage that drops from the ceiling",
        "The whole garage stored in the ceiling",
        "Motorized ceiling storage: 40 sq ft reclaimed",
      ],
    },
    hook: { fr: "Regardez le plafond descendre.", en: "Watch the ceiling come down." },
  },
  {
    category: "zen_bathroom",
    pull: 1.3,
    subject: { fr: "la salle de bain zen", en: "the zen bathroom" },
    titles: {
      fr: [
        "Salle de bain zen japonaise en 60 secondes",
        "Le bain japonais qui transforme la salle de bain",
        "Ofuro, bois et pierre : la salle de bain zen",
      ],
      en: [
        "Japanese zen bathroom in 60 seconds",
        "The Japanese soaking tub that transforms the bathroom",
        "Ofuro, wood and stone: the zen bathroom",
      ],
    },
    hook: { fr: "Une salle de bain qui ressemble à un onsen.", en: "A bathroom that feels like an onsen." },
  },
];

const NARRATION = {
  fr: [
    "Personne ne devine ce qui se cache ici.",
    "Regardez bien : {s} est juste là, sous vos yeux.",
    "Tout commence par une idée simple : gagner de la place sans rien montrer.",
    "Un mécanisme discret, un rail, et le mur s’ouvre.",
    "De l’autre côté, l’espace change complètement d’ambiance.",
    "Les détails font tout : lumière chaude, matériaux bruts, silence.",
    "Et le meilleur ? Fermé, personne ne voit la différence.",
    "Vous en voulez un chez vous ? Dites-le en commentaire.",
  ],
  en: [
    "Nobody guesses what is hidden here.",
    "Look closely: {s} is right there, in plain sight.",
    "It all starts with a simple idea: gain space without showing anything.",
    "A discreet mechanism, a rail, and the wall opens.",
    "On the other side, the whole mood of the space changes.",
    "Details make it: warm light, raw materials, silence.",
    "And the best part? Closed, nobody can tell.",
    "Want one at home? Tell us in the comments.",
  ],
};

const ON_SCREEN = {
  fr: ["Attendez la fin…", "Regardez ce mur", "3… 2… 1…", "Avant / après", "Le détail qui change tout", "Fermé = invisible", "Votre avis ?", "Abonnez-vous pour la suite"],
  en: ["Wait for it…", "Look at this wall", "3… 2… 1…", "Before / after", "The detail that changes everything", "Closed = invisible", "Your take?", "Follow for part 2"],
};

const SFX = [
  "door slide, soft wood creak",
  "low ambient hum, room tone",
  "click + servo whir",
  "whoosh transition, riser",
  "fireplace crackle, distant rain",
  "reverse cymbal riser",
  "bass hit, sub drop",
  "soft outro pad, loop-friendly",
];

const VISUAL_PROMPTS = [
  "Slow cinematic push-in on {s}, warm interior light, photoreal, vertical 9:16",
  "Macro shot of the hidden mechanism sliding open, shallow depth of field, 9:16",
  "Wide reveal of the space behind, volumetric light through the opening, 9:16",
  "Before / after split screen, matched camera position, 9:16",
  "Detail of materials: oak, brushed steel, matte black, soft key light, 9:16",
  "Person walking through, back to camera, natural motion blur, 9:16",
  "Night version with LED accent lighting, moody, 9:16",
  "Final hero shot, slow dolly out, seamless loop, 9:16",
];

const COMMENT_POOL = {
  fr: {
    authors: ["@marie.deco", "@julien_bricole", "@camille.h", "@theo.archi", "@lea_maison", "@nico.diy", "@sarah.k", "@max_reno"],
    texts: [
      "Je veux exactement ça dans mon salon 😍",
      "Le bruit de la porte est trop satisfaisant",
      "Combien ça coûte un truc pareil ?",
      "Vidéo IA ou pas ? Le rendu est fou",
      "Le mécanisme à 0:12 est génial",
      "Mon chat trouverait le passage en 2 min 😂",
      "Tuto complet svp !",
      "J’ai regardé 4 fois de suite",
      "La lumière à la fin 🔥",
      "Ça me rappelle les films d’espionnage",
      "Où trouver les rails ?",
      "Abonné direct",
    ],
  },
  en: {
    authors: ["@homebuilder.joe", "@emily.designs", "@tinyhousetom", "@renovation.nerd", "@kate_m", "@dan.the.maker", "@sophie.interior", "@alex_builds"],
    texts: [
      "I need this in my house right now",
      "The sound design on this is unreal",
      "How much does something like this cost?",
      "AI or real? Either way it’s gorgeous",
      "That mechanism at 0:12 is genius",
      "My cat would find the passage in 2 minutes 😂",
      "Full tutorial please!",
      "Watched this 4 times in a row",
      "The lighting at the end 🔥",
      "Feels like a spy movie",
      "Where do you buy those rails?",
      "Instant subscribe",
    ],
  },
};

/* ------------------------------------------------------------------------ */
/* Générateurs                                                               */
/* ------------------------------------------------------------------------ */

function buildScript(rng: Rng, theme: Theme, format: VideoFormat, titles: { fr: string; en: string }): ScriptV1 {
  const count = int(rng, 6, 8);
  const scenes: ScriptScene[] = [];
  for (let i = 0; i < count; i++) {
    const scene: ScriptScene = {
      index: i,
      duration_s: int(rng, 4, 8),
      visual_prompt: VISUAL_PROMPTS[i].replace("{s}", theme.subject.en),
      narration:
        format === "A_voiceover"
          ? {
              fr: NARRATION.fr[i].replace("{s}", theme.subject.fr),
              en: NARRATION.en[i].replace("{s}", theme.subject.en),
            }
          : {},
      on_screen_text: { fr: ON_SCREEN.fr[i], en: ON_SCREEN.en[i] },
      sfx: SFX[i],
    };
    scenes.push(scene);
  }
  return {
    version: 1,
    scenes,
    loop_note: "Le dernier plan raccorde sur le premier (boucle).",
    metadata: {
      fr: {
        title: titles.fr,
        description: `${theme.hook.fr} #shorts #maison #deco`,
        tags: ["maison", "déco", "rénovation", theme.category, "shorts"],
      },
      en: {
        title: titles.en,
        description: `${theme.hook.en} #shorts #home #design`,
        tags: ["home", "design", "renovation", theme.category, "shorts"],
      },
    },
  };
}

function buildRetention(rng: Rng, avgViewPct: number): RetentionPoint[] {
  const end = Math.max(0.08, (avgViewPct / 100) * between(rng, 0.8, 0.95));
  const points: RetentionPoint[] = [];
  for (let i = 0; i <= 20; i++) {
    const t = i / 20;
    const dip = 0.16 * (1 - Math.exp(-t / 0.06));
    const slope = (1 - end - 0.16) * Math.pow(t, 1.15);
    let w = 1 - dip - slope + (i === 0 ? 0 : between(rng, -0.015, 0.015));
    if (i === 20) w += 0.03; // rebond de fin (boucle)
    w = Math.max(0.04, Math.min(1, w));
    const baseline = 1 - 0.5 * t;
    points.push({
      t: Number(t.toFixed(2)),
      w: Number(w.toFixed(3)),
      rel: w > baseline + 0.05 ? "ABOVE_AVERAGE" : w < baseline - 0.05 ? "BELOW_AVERAGE" : "AVERAGE",
    });
  }
  return points;
}

interface PublishedEntry {
  overview: VideoOverview;
  production: Production;
  daily: VideoMetricsDaily[];
  retention: RetentionPoint[];
  comments: VideoComment[];
}

function buildPublishedVideo(
  rng: Rng,
  production: Production,
  theme: Theme,
  channel: Channel,
  title: string,
  publishedAt: Date,
  viral: boolean
): PublishedEntry {
  const id = uuid(rng);
  const ytId = youtubeId(rng);
  const format = production.format;
  const duration = int(rng, 32, 58);
  const basePct = format === "A_voiceover" ? between(rng, 62, 84) : between(rng, 52, 94);
  const avgViewPct = Math.min(98, basePct + (viral ? 5 : 0));
  const peak =
    between(rng, 6000, 30000) *
    theme.pull *
    (format === "B_visual" ? 1.15 : 1) *
    (channel.lang === "en" ? 0.55 : 1) *
    (viral ? between(rng, 4, 8) : 1);
  const likeRate = between(rng, 0.03, 0.06);
  const commentRate = between(rng, 0.002, 0.005);
  const shareRate = between(rng, 0.003, 0.006);
  const subRate = between(rng, 0.0008, 0.002);

  const ageDays = (NOW.getTime() - publishedAt.getTime()) / DAY_MS;
  const daily: VideoMetricsDaily[] = [];
  const dayCount = Math.floor(ageDays) + 1;
  for (let k = 0; k < dayCount; k++) {
    const dayStart = parisAddDays(parisStartOfDay(publishedAt), k);
    const dayEnd = parisAddDays(dayStart, 1);
    const from = Math.max(dayStart.getTime(), publishedAt.getTime());
    const to = Math.min(dayEnd.getTime(), NOW.getTime());
    if (to <= from) continue;
    const fraction = (to - from) / DAY_MS;
    const raw =
      (peak * 0.35 * Math.exp(-k / 2.2) + peak * 0.004 * between(rng, 0.6, 1.4)) *
      between(rng, 0.85, 1.15) *
      fraction;
    const views = Math.max(1, Math.round(raw));
    const pct = Math.max(20, Math.min(98, avgViewPct + between(rng, -3, 3)));
    daily.push({
      video_id: id,
      day: parisDayKey(dayStart),
      views,
      likes: Math.round(views * likeRate),
      comments: Math.round(views * commentRate),
      shares: Math.round(views * shareRate),
      subscribers_gained: Math.round(views * subRate),
      average_view_duration_s: Number(((duration * pct) / 100).toFixed(1)),
      average_view_pct: Number(pct.toFixed(1)),
    });
  }
  const sum = (key: "views" | "likes" | "comments" | "shares" | "subscribers_gained") =>
    daily.reduce((acc, row) => acc + row[key], 0);

  const pool = COMMENT_POOL[channel.lang];
  const commentCount = int(rng, 3, 6);
  const comments: VideoComment[] = [];
  const usedTexts = new Set<number>();
  for (let i = 0; i < commentCount; i++) {
    let idx = int(rng, 0, pool.texts.length - 1);
    while (usedTexts.has(idx)) idx = (idx + 1) % pool.texts.length;
    usedTexts.add(idx);
    const at = new Date(
      Math.min(NOW.getTime() - 60_000, publishedAt.getTime() + between(rng, 0.2, Math.max(0.5, ageDays * 24)) * 3_600_000)
    );
    comments.push({
      id: uuid(rng),
      author: pick(rng, pool.authors),
      text: pool.texts[idx],
      like_count: int(rng, 0, viral ? 900 : 120),
      published_at: iso(at),
    });
  }
  comments.sort((a, b) => b.published_at.localeCompare(a.published_at));

  const overview: VideoOverview = {
    id,
    production_id: production.id,
    channel_id: channel.id,
    channel_slug: channel.slug,
    lang: channel.lang,
    format,
    status: "published",
    title,
    category: theme.category,
    scheduled_at: iso(publishedAt),
    youtube_video_id: ytId,
    youtube_publish_at: iso(publishedAt),
    published_at: iso(publishedAt),
    duration_s: duration,
    views: sum("views"),
    likes: sum("likes"),
    comments: sum("comments"),
    shares: sum("shares"),
    subscribers_gained: sum("subscribers_gained"),
    average_view_pct: Number(avgViewPct.toFixed(1)),
  };

  return { overview, production, daily, retention: buildRetention(rng, avgViewPct), comments };
}

function buildPublished(rng: Rng): PublishedEntry[] {
  const entries: PublishedEntry[] = [];
  const usage = new Array<number>(THEMES.length).fill(0);
  let lastTheme = -1;

  for (let d = -60; d <= 0; d++) {
    for (const slot of SLOTS) {
      const at = slotAt(d, slot);
      if (at.getTime() >= NOW.getTime()) continue;
      const publish = d >= -4 ? true : rng() < 0.06;
      if (!publish) continue;

      let themeIdx = int(rng, 0, THEMES.length - 1);
      if (themeIdx === lastTheme) themeIdx = (themeIdx + 1) % THEMES.length;
      lastTheme = themeIdx;
      const theme = THEMES[themeIdx];
      const variant = usage[themeIdx] % theme.titles.fr.length;
      const suffix = usage[themeIdx] >= theme.titles.fr.length ? " · partie 2" : "";
      usage[themeIdx] += 1;
      const titles = { fr: theme.titles.fr[variant] + suffix, en: theme.titles.en[variant] + suffix };

      const format: VideoFormat = rng() < 0.5 ? "A_voiceover" : "B_visual";
      const createdAt = new Date(at.getTime() - between(rng, 6, 30) * 3_600_000);
      const production: Production = {
        id: uuid(rng),
        concept_id: uuid(rng),
        format,
        status: "archived",
        script: null,
        target_duration_s: 45,
        style_preset: format === "A_voiceover" ? "documentary-warm" : "cinematic-loop",
        video_provider: "comfy_ltx",
        error: null,
        created_at: iso(createdAt),
        updated_at: iso(at),
      };
      production.script = buildScript(rng, theme, format, titles);
      const viral = rng() < 0.12;
      for (const channel of CHANNELS) {
        entries.push(buildPublishedVideo(rng, production, theme, channel, titles[channel.lang], at, viral));
      }
    }
  }
  entries.sort((a, b) => b.overview.published_at!.localeCompare(a.overview.published_at!));
  return entries;
}

function buildChannelDaily(rng: Rng, channel: Channel): ChannelMetricsDaily[] {
  const isFr = channel.lang === "fr";
  const startSubs = isFr ? 118 : 54;
  const targetSubs = isFr ? 612 : 288;
  const views: number[] = [];
  const rawGains: number[] = [];
  for (let i = 0; i < 90; i++) {
    const offset = i - 89;
    const date = day(offset);
    const dow = toParisWallClock(date).getDay();
    const weekend = dow === 0 || dow === 6;
    const growth = Math.pow(1.042, i);
    const base = (isFr ? 900 : 420) * growth;
    const partial = offset === 0 ? (NOW.getTime() - TODAY.getTime()) / DAY_MS : 1;
    const v = Math.round(base * between(rng, 0.8, 1.2) * (weekend ? 1.15 : 1) * partial);
    views.push(v);
    rawGains.push(v * between(rng, 0.0006, 0.0011));
  }
  const totalRaw = rawGains.reduce((a, b) => a + b, 0);
  const scale = (targetSubs - startSubs) / totalRaw;
  let subs = startSubs;
  const rows: ChannelMetricsDaily[] = [];
  let carry = 0;
  for (let i = 0; i < 90; i++) {
    const exact = rawGains[i] * scale + carry;
    const gained = Math.round(exact);
    carry = exact - gained;
    subs += gained;
    const v = views[i];
    rows.push({
      channel_id: channel.id,
      day: parisDayKey(day(i - 89)),
      subscribers: subs,
      subscribers_gained: gained,
      views: v,
      estimated_minutes_watched: Math.round((v * between(rng, 24, 30)) / 60),
      likes: Math.round(v * between(rng, 0.04, 0.05)),
      comments: Math.round(v * between(rng, 0.0025, 0.0035)),
    });
  }
  return rows;
}

/* ------------------------------------------------------------------------ */
/* Pipeline de production                                                    */
/* ------------------------------------------------------------------------ */

interface JobSpec {
  type: JobType;
  status: JobStatus;
  lang?: "fr" | "en";
  progress?: number;
  label?: string | null;
  attempts?: number;
  startedMinutesAgo?: number | null;
  durationMinutes?: number | null;
  error?: string | null;
}

interface PipelineSpec {
  status: ProductionStatus;
  themeIdx: number;
  variant: number;
  format: VideoFormat;
  ageMinutes: number;
  updatedMinutesAgo: number;
  error?: string | null;
  jobs: JobSpec[];
  videos: [VideoStatus, VideoStatus];
  /** Créneau assigné aux vidéos : [décalage jour, "HH:mm"]. */
  slot?: [number, string] | null;
  videoErrors?: [string | null, string | null];
  uploaded?: boolean;
  current_step: string | null;
  eta_minutes: number | null;
  withScript?: boolean;
}

function clipJobs(done: number, running: number | null, queued: number, failedScene?: number): JobSpec[] {
  const jobs: JobSpec[] = [];
  let scene = 0;
  for (let i = 0; i < done; i++, scene++) {
    jobs.push({ type: "generate_clip", status: "done", progress: 100, label: `Scène ${scene + 1}/8`, startedMinutesAgo: 90 - scene * 6, durationMinutes: 4 });
  }
  if (failedScene != null) {
    jobs.push({ type: "generate_clip", status: "failed", progress: 35, label: `Scène ${failedScene + 1}/8`, attempts: 3, startedMinutesAgo: 60, durationMinutes: 10, error: "Timeout ComfyUI (LTX-Video) après 600 s — 3/3 tentatives" });
    scene++;
  }
  if (running != null) {
    jobs.push({ type: "generate_clip", status: "running", progress: running, label: `Scène ${scene + 1}/8 · étape ${Math.round((running / 100) * 30)}/30`, startedMinutesAgo: 3, durationMinutes: null });
    scene++;
  }
  for (let i = 0; i < queued; i++, scene++) {
    jobs.push({ type: "generate_clip", status: "queued", progress: 0, label: `Scène ${scene + 1}/8`, startedMinutesAgo: null, durationMinutes: null });
  }
  return jobs;
}

function pair(type: JobType, fr: JobStatus, en: JobStatus, extra: Partial<JobSpec> = {}): JobSpec[] {
  const base = (status: JobStatus): Partial<JobSpec> =>
    status === "done"
      ? { progress: 100, startedMinutesAgo: 30, durationMinutes: 3 }
      : status === "running"
        ? { progress: extra.progress ?? 50, startedMinutesAgo: 2, durationMinutes: null }
        : { progress: 0, startedMinutesAgo: null, durationMinutes: null };
  return [
    { type, status: fr, lang: "fr", ...base(fr), ...(fr === "running" ? extra : {}) },
    { type, status: en, lang: "en", ...base(en), ...(en === "running" ? extra : {}) },
  ];
}

const PIPELINE: PipelineSpec[] = [
  {
    status: "ready",
    themeIdx: 4,
    variant: 2,
    format: "A_voiceover",
    ageMinutes: 26 * 60,
    updatedMinutesAgo: 48,
    jobs: [
      { type: "script", status: "done", progress: 100, startedMinutesAgo: 25 * 60, durationMinutes: 2 },
      ...clipJobs(8, null, 0),
      ...pair("tts", "done", "done"),
      ...pair("assemble", "done", "done"),
      ...pair("qa", "done", "done"),
      ...pair("upload", "done", "done"),
    ],
    videos: ["scheduled", "scheduled"],
    slot: [0, "18:00"],
    uploaded: true,
    current_step: "Programmée sur YouTube",
    eta_minutes: null,
    withScript: true,
  },
  {
    status: "ready",
    themeIdx: 0,
    variant: 1,
    format: "B_visual",
    ageMinutes: 20 * 60,
    updatedMinutesAgo: 95,
    jobs: [
      { type: "script", status: "done", progress: 100, startedMinutesAgo: 19 * 60, durationMinutes: 2 },
      ...clipJobs(8, null, 0),
      ...pair("assemble", "done", "done"),
      ...pair("qa", "done", "done"),
      ...pair("upload", "done", "done"),
    ],
    videos: ["scheduled", "scheduled"],
    slot: [1, "09:00"],
    uploaded: true,
    current_step: "Programmée sur YouTube",
    eta_minutes: null,
    withScript: true,
  },
  {
    status: "ready",
    themeIdx: 9,
    variant: 1,
    format: "A_voiceover",
    ageMinutes: 14 * 60,
    updatedMinutesAgo: 35,
    jobs: [
      { type: "script", status: "done", progress: 100, startedMinutesAgo: 13 * 60, durationMinutes: 2 },
      ...clipJobs(8, null, 0),
      ...pair("tts", "done", "done"),
      ...pair("assemble", "done", "done"),
      ...pair("qa", "done", "done"),
      { type: "upload", status: "queued", lang: "fr", progress: 0, startedMinutesAgo: null, durationMinutes: null },
      { type: "upload", status: "failed", lang: "en", progress: 0, attempts: 3, startedMinutesAgo: 40, durationMinutes: 1, error: "YouTube Data API : uploadLimitExceeded (quota journalier)" },
    ],
    videos: ["ready", "failed"],
    videoErrors: [null, "uploadLimitExceeded — nouvelle tentative au reset du quota"],
    slot: [1, "13:00"],
    current_step: "Envoi FR en attente · EN en échec",
    eta_minutes: 20,
    withScript: true,
  },
  {
    status: "assembling",
    themeIdx: 2,
    variant: 2,
    format: "B_visual",
    ageMinutes: 6 * 60,
    updatedMinutesAgo: 4,
    jobs: [
      { type: "script", status: "done", progress: 100, startedMinutesAgo: 6 * 60, durationMinutes: 2 },
      ...clipJobs(8, null, 0),
      ...pair("assemble", "done", "done"),
      ...pair("qa", "done", "running", { progress: 45, label: "Vérification audio + bords noirs" }),
    ],
    videos: ["review", "qa"],
    slot: [2, "09:00"],
    current_step: "Contrôle qualité EN",
    eta_minutes: 8,
    withScript: true,
  },
  {
    status: "assembling",
    themeIdx: 11,
    variant: 0,
    format: "A_voiceover",
    ageMinutes: 4 * 60,
    updatedMinutesAgo: 2,
    jobs: [
      { type: "script", status: "done", progress: 100, startedMinutesAgo: 4 * 60, durationMinutes: 2 },
      ...clipJobs(8, null, 0),
      ...pair("tts", "done", "done"),
      ...pair("assemble", "done", "running", { progress: 70, label: "Mixage voix + SFX" }),
      ...pair("qa", "queued", "queued"),
    ],
    videos: ["rendering", "rendering"],
    slot: [1, "18:00"],
    current_step: "Assemblage EN",
    eta_minutes: 12,
    withScript: true,
  },
  {
    status: "generating",
    themeIdx: 6,
    variant: 1,
    format: "A_voiceover",
    ageMinutes: 3 * 60,
    updatedMinutesAgo: 1,
    jobs: [
      { type: "script", status: "done", progress: 100, startedMinutesAgo: 3 * 60, durationMinutes: 2 },
      ...clipJobs(7, 80, 0),
      ...pair("tts", "done", "queued"),
      ...pair("assemble", "queued", "queued"),
      ...pair("qa", "queued", "queued"),
    ],
    videos: ["pending", "pending"],
    slot: [2, "13:00"],
    current_step: "Clips 8/8",
    eta_minutes: 18,
    withScript: true,
  },
  {
    status: "generating",
    themeIdx: 8,
    variant: 0,
    format: "B_visual",
    ageMinutes: 110,
    updatedMinutesAgo: 3,
    jobs: [
      { type: "script", status: "done", progress: 100, startedMinutesAgo: 110, durationMinutes: 2 },
      ...clipJobs(4, 60, 3),
      ...pair("assemble", "queued", "queued"),
      ...pair("qa", "queued", "queued"),
    ],
    videos: ["pending", "pending"],
    slot: [2, "18:00"],
    current_step: "Clips 5/8",
    eta_minutes: 34,
    withScript: true,
  },
  {
    status: "generating",
    themeIdx: 10,
    variant: 2,
    format: "A_voiceover",
    ageMinutes: 55,
    updatedMinutesAgo: 6,
    jobs: [
      { type: "script", status: "done", progress: 100, startedMinutesAgo: 55, durationMinutes: 3 },
      ...clipJobs(2, 25, 5),
      ...pair("tts", "queued", "queued"),
      ...pair("assemble", "queued", "queued"),
      ...pair("qa", "queued", "queued"),
    ],
    videos: ["pending", "pending"],
    slot: null,
    current_step: "Clips 3/8",
    eta_minutes: 52,
    withScript: true,
  },
  {
    status: "scripting",
    themeIdx: 3,
    variant: 1,
    format: "B_visual",
    ageMinutes: 18,
    updatedMinutesAgo: 1,
    jobs: [{ type: "script", status: "running", progress: 40, label: "Rédaction des 8 scènes", startedMinutesAgo: 2, durationMinutes: null }],
    videos: ["pending", "pending"],
    slot: null,
    current_step: "Script en cours",
    eta_minutes: 4,
  },
  {
    status: "scripting",
    themeIdx: 1,
    variant: 2,
    format: "A_voiceover",
    ageMinutes: 9,
    updatedMinutesAgo: 9,
    jobs: [{ type: "script", status: "queued", progress: 0, startedMinutesAgo: null, durationMinutes: null }],
    videos: ["pending", "pending"],
    slot: null,
    current_step: "Script en file d’attente",
    eta_minutes: 9,
  },
  {
    status: "draft",
    themeIdx: 7,
    variant: 1,
    format: "B_visual",
    ageMinutes: 3,
    updatedMinutesAgo: 3,
    jobs: [],
    videos: ["pending", "pending"],
    slot: null,
    current_step: "Brouillon — en attente de validation",
    eta_minutes: null,
  },
  {
    status: "failed",
    themeIdx: 5,
    variant: 1,
    format: "A_voiceover",
    ageMinutes: 5 * 60,
    updatedMinutesAgo: 120,
    error: "generate_clip scène 5 : timeout ComfyUI (LTX-Video) après 3 tentatives",
    jobs: [
      { type: "script", status: "done", progress: 100, startedMinutesAgo: 5 * 60, durationMinutes: 2 },
      ...clipJobs(4, null, 0, 4),
      { type: "generate_clip", status: "cancelled", progress: 0, label: "Scène 6/8", startedMinutesAgo: null, durationMinutes: null },
      { type: "generate_clip", status: "cancelled", progress: 0, label: "Scène 7/8", startedMinutesAgo: null, durationMinutes: null },
      { type: "generate_clip", status: "cancelled", progress: 0, label: "Scène 8/8", startedMinutesAgo: null, durationMinutes: null },
      ...pair("tts", "done", "done"),
    ],
    videos: ["pending", "pending"],
    slot: null,
    current_step: "Échec — clip scène 5",
    eta_minutes: null,
    withScript: true,
  },
];

interface PipelineEntry {
  card: ProductionCard;
  videos: Video[];
}

function buildPipeline(rng: Rng): PipelineEntry[] {
  return PIPELINE.map((spec, index) => {
    const theme = THEMES[spec.themeIdx];
    const titles = { fr: theme.titles.fr[spec.variant], en: theme.titles.en[spec.variant] };
    const productionId = uuid(rng);
    const conceptId = uuid(rng);
    const createdAt = minutesAgo(spec.ageMinutes);
    const updatedAt = minutesAgo(spec.updatedMinutesAgo);
    const production: Production = {
      id: productionId,
      concept_id: conceptId,
      format: spec.format,
      status: spec.status,
      script: spec.withScript ? buildScript(rng, theme, spec.format, titles) : null,
      target_duration_s: 45,
      style_preset: spec.format === "A_voiceover" ? "documentary-warm" : "cinematic-loop",
      video_provider: "comfy_ltx",
      error: spec.error ?? null,
      created_at: iso(createdAt),
      updated_at: iso(updatedAt),
    };

    const slotDate = spec.slot ? slotAt(spec.slot[0], spec.slot[1]) : null;
    const videos: Video[] = CHANNELS.map((channel, i) => {
      const status = spec.videos[i];
      const uploaded = Boolean(spec.uploaded) && (status === "scheduled" || status === "published");
      return {
        id: uuid(rng),
        production_id: productionId,
        channel_id: channel.id,
        lang: channel.lang,
        format: spec.format,
        status,
        title: titles[channel.lang],
        description: production.script?.metadata[channel.lang].description ?? null,
        tags: production.script?.metadata[channel.lang].tags ?? [],
        duration_s: production.script ? production.script.scenes.reduce((a, s) => a + s.duration_s, 0) : null,
        scheduled_at: slotDate ? iso(slotDate) : null,
        youtube_video_id: uploaded ? youtubeId(rng) : null,
        youtube_publish_at: uploaded && slotDate ? iso(slotDate) : null,
        published_at: null,
        error: spec.videoErrors?.[i] ?? null,
        created_at: iso(createdAt),
        updated_at: iso(updatedAt),
      };
    });

    const jobs: Job[] = spec.jobs.map((j, jIndex) => {
      const started = j.startedMinutesAgo != null ? minutesAgo(j.startedMinutesAgo) : null;
      const finished =
        started && j.durationMinutes != null ? new Date(started.getTime() + j.durationMinutes * 60_000) : null;
      const video = j.lang ? videos.find((v) => v.lang === j.lang) ?? null : null;
      return {
        id: uuid(rng),
        type: j.type,
        status: j.status,
        priority: 100 - index * 5,
        production_id: productionId,
        video_id: video?.id ?? null,
        channel_id: video?.channel_id ?? null,
        progress: j.progress ?? (j.status === "done" ? 100 : 0),
        progress_label: j.label ?? (j.lang ? j.lang.toUpperCase() : null),
        attempts: j.attempts ?? (j.status === "queued" ? 0 : 1),
        max_attempts: 3,
        run_after: iso(new Date(createdAt.getTime() + jIndex * 30_000)),
        locked_by: j.status === "running" ? (j.type === "generate_clip" ? "worker-gpu-01" : "worker-cpu-02") : null,
        started_at: started ? iso(started) : null,
        finished_at: finished && j.status !== "running" ? iso(finished) : null,
        error: j.error ?? null,
        created_at: iso(new Date(createdAt.getTime() + jIndex * 30_000)),
      };
    });

    const progress_pct =
      jobs.length === 0
        ? 0
        : Math.round(jobs.reduce((acc, j) => acc + (j.status === "done" ? 100 : j.status === "running" ? j.progress : 0), 0) / jobs.length);

    const card: ProductionCard = {
      production,
      concept: { id: conceptId, title: titles.fr, hook: theme.hook.fr, category: theme.category },
      videos,
      jobs,
      progress_pct: spec.status === "ready" ? 100 : progress_pct,
      current_step: spec.current_step,
      eta_minutes: spec.eta_minutes,
    };
    return { card, videos };
  });
}

/* ------------------------------------------------------------------------ */
/* Idées & alertes                                                           */
/* ------------------------------------------------------------------------ */

const CONCEPT_SPECS: Array<[string, string, string, Concept["status"], Concept["source"], number]> = [
  ["Le garage qui devient une salle de sport cachée", "Un mur coulissant et le garage disparaît.", "smart_furniture", "proposed", "agent", 88],
  ["Le miroir qui ouvre sur un dressing secret", "Personne ne pousse jamais ce miroir…", "secret_passages", "approved", "agent", 92],
  ["Piscine à fond mobile → terrasse en 90 s", "Le sol monte, l’eau disparaît.", "pool", "used", "agent", 95],
  ["Escalier à tiroirs : 12 rangements invisibles", "Chaque marche est un tiroir.", "under_stairs", "approved", "manual", 81],
  ["Containers empilés : la maison de 40 m²", "Deux boîtes, une maison.", "container", "proposed", "agent", 74],
  ["Le plafond qui descend un écran de 120 pouces", "Le salon devient un cinéma en 8 secondes.", "hidden_cinema", "approved", "clone", 90],
  ["Tête de lit en tasseaux avec LED et rangement", "Le mur qui range et qui éclaire.", "slat_wall", "proposed", "agent", 67],
  ["Le pod bureau sur le toit-terrasse", "Un bureau avec vue, à 30 cm du ciel.", "office_pod", "rejected", "agent", 43],
  ["Table basse béton + époxy façon rivière", "Une rivière figée dans le béton.", "concrete_epoxy", "proposed", "manual", 71],
  ["Vélos rangés au plafond du garage (motorisé)", "Appuyez, les vélos montent.", "ceiling_storage", "used", "agent", 84],
  ["Douche japonaise en pierre et cèdre", "Le cèdre, la pierre, la vapeur.", "zen_bathroom", "approved", "agent", 79],
  ["La porte de cave à vin déguisée en tableau", "Le tableau s’ouvre : 300 bouteilles.", "under_stairs", "proposed", "clone", 77],
  ["Le passage secret entre deux chambres d’enfants", "Un tunnel dans l’armoire.", "secret_passages", "used", "agent", 86],
  ["Un mur entier qui pivote pour cacher la buanderie", "Machine à laver ? Quelle machine à laver ?", "space_optimization", "proposed", "agent", 69],
  ["Sauna extérieur caché dans un abri de jardin", "L’abri de jardin le plus chaud du quartier.", "zen_bathroom", "rejected", "manual", 38],
];

function buildConcepts(rng: Rng): Concept[] {
  return CONCEPT_SPECS.map(([title, hook, category, status, source, score], i) => ({
    id: uuid(rng),
    title,
    hook,
    category,
    premise: `${hook} Plan en 8 scènes, révélation à la scène 4, boucle sur le plan final.`,
    visual_beats: ["Plan d’ouverture intrigant", "Détail du mécanisme", "Révélation", "Plan final en boucle"],
    source,
    score,
    status,
    created_at: iso(minutesAgo(45 + i * 9 * 60 + int(rng, 0, 120))),
  }));
}

function buildAlerts(rng: Rng, pipeline: PipelineEntry[]): Alert[] {
  const failedUpload = pipeline[2];
  const failedProd = pipeline[11];
  const failedJob = failedProd.card.jobs.find((j) => j.status === "failed") ?? null;
  const uploadJob = failedUpload.card.jobs.find((j) => j.type === "upload" && j.status === "failed") ?? null;
  const specs: Array<Omit<Alert, "id">> = [
    {
      severity: "error",
      title: "Envoi YouTube échoué — quota dépassé (Channel EN)",
      body: `uploadLimitExceeded pour « ${failedUpload.videos[1].title} ». Nouvelle tentative au reset du quota (09:00 heure du Pacifique).`,
      job_id: uploadJob?.id ?? null,
      video_id: failedUpload.videos[1].id,
      acknowledged_at: null,
      created_at: iso(minutesAgo(38)),
    },
    {
      severity: "error",
      title: "Génération de clip en échec (3/3 tentatives)",
      body: `Scène 5 — timeout ComfyUI (LTX-Video) après 600 s sur « ${failedProd.card.concept?.title} ». Production mise en échec.`,
      job_id: failedJob?.id ?? null,
      video_id: null,
      acknowledged_at: null,
      created_at: iso(minutesAgo(125)),
    },
    {
      severity: "warning",
      title: "Créneau demain 13:00 — Channel EN sans vidéo prête",
      body: "La vidéo EN prévue a échoué à l’envoi. 23 h avant le créneau : relancer l’upload ou réassigner une vidéo prête.",
      job_id: null,
      video_id: failedUpload.videos[1].id,
      acknowledged_at: null,
      created_at: iso(minutesAgo(60)),
    },
    {
      severity: "warning",
      title: "Rétention < 50 % sur 3 Shorts B_visual cette semaine",
      body: "Les formats visuels sans voix off décrochent entre 8 s et 12 s. Suggestion : hook texte plus tôt (≤ 1,5 s).",
      job_id: null,
      video_id: null,
      acknowledged_at: null,
      created_at: iso(minutesAgo(5 * 60)),
    },
    {
      severity: "warning",
      title: "Quota YouTube Data API à 82 % (Chaîne FR)",
      body: "8 200 / 10 000 unités consommées (hors envois, qui ont leur propre compteur de 100 par jour).",
      job_id: null,
      video_id: null,
      acknowledged_at: null,
      created_at: iso(minutesAgo(3 * 60)),
    },
    {
      severity: "info",
      title: "Prompt « script » v4 activé",
      body: "Hook raccourci (≤ 2 s), CTA « abonne-toi » retiré, boucle explicite sur le dernier plan.",
      job_id: null,
      video_id: null,
      acknowledged_at: iso(minutesAgo(20 * 60)),
      created_at: iso(minutesAgo(26 * 60)),
    },
    {
      severity: "info",
      title: "Synchronisation des métriques terminée",
      body: "42 vidéos mises à jour (vues, likes, commentaires, rétention).",
      job_id: null,
      video_id: null,
      acknowledged_at: iso(minutesAgo(5 * 60)),
      created_at: iso(minutesAgo(6 * 60)),
    },
    {
      severity: "info",
      title: "10 nouvelles idées proposées par l’agent",
      body: "Score moyen 74/100. 3 idées au-dessus de 85 à valider.",
      job_id: null,
      video_id: null,
      acknowledged_at: null,
      created_at: iso(minutesAgo(8 * 60)),
    },
  ];
  return specs.map((a) => ({ id: uuid(rng), ...a }));
}

/* ------------------------------------------------------------------------ */
/* Monde                                                                     */
/* ------------------------------------------------------------------------ */

interface World {
  published: PublishedEntry[];
  channelDaily: Record<string, ChannelMetricsDaily[]>;
  pipeline: PipelineEntry[];
  concepts: Concept[];
  alerts: Alert[];
  slotIndex: Map<string, ScheduleSlot["video"]>;
}

function buildWorld(): World {
  const rng = mulberry32(hashSeed("youtube-2.0/mock/v1"));
  const published = buildPublished(rng);
  const channelDaily: Record<string, ChannelMetricsDaily[]> = {};
  for (const channel of CHANNELS) channelDaily[channel.slug] = buildChannelDaily(rng, channel);
  const pipeline = buildPipeline(rng);
  const concepts = buildConcepts(rng);
  const alerts = buildAlerts(rng, pipeline);

  const slotIndex = new Map<string, ScheduleSlot["video"]>();
  for (const entry of published) {
    const v = entry.overview;
    slotIndex.set(`${v.channel_slug}|${v.published_at}`, {
      id: v.id,
      title: v.title,
      status: v.status,
      format: v.format ?? "A_voiceover",
      youtube_video_id: v.youtube_video_id,
    });
  }
  for (const entry of pipeline) {
    for (const v of entry.videos) {
      const at = v.youtube_publish_at ?? v.scheduled_at;
      if (!at) continue;
      const slug = CHANNELS.find((c) => c.id === v.channel_id)!.slug;
      slotIndex.set(`${slug}|${at}`, {
        id: v.id,
        title: v.title,
        status: v.status,
        format: v.format,
        youtube_video_id: v.youtube_video_id,
      });
    }
  }
  return { published, channelDaily, pipeline, concepts, alerts, slotIndex };
}

const WORLD = buildWorld();

/* ------------------------------------------------------------------------ */
/* Source                                                                    */
/* ------------------------------------------------------------------------ */

function channelRows(channel?: ChannelFilter): ChannelMetricsDaily[][] {
  return channel ? [WORLD.channelDaily[channel]] : CHANNELS.map((c) => WORLD.channelDaily[c.slug]);
}

function sumLast(rows: ChannelMetricsDaily[][], key: "views" | "subscribers_gained", from: number, to: number): number {
  let total = 0;
  for (const series of rows) {
    const slice = series.slice(series.length - from, series.length - to);
    total += slice.reduce((acc, r) => acc + r[key], 0);
  }
  return total;
}

export const mockSource: DataSource = {
  async getChannels() {
    return CHANNELS.map((c) => ({ ...c, publish_slots: [...c.publish_slots] }));
  },

  async getOverviewKpis(channel) {
    const rows = channelRows(channel);
    const subscribers = rows.reduce((acc, s) => acc + (s[s.length - 1]?.subscribers ?? 0), 0);
    const views7 = sumLast(rows, "views", 7, 0);
    const viewsPrev7 = sumLast(rows, "views", 14, 7);
    const minutes28 = rows.reduce(
      (acc, s) => acc + s.slice(-28).reduce((a, r) => a + (r.estimated_minutes_watched ?? 0), 0),
      0
    );
    const cutoff7 = NOW.getTime() - 7 * DAY_MS;
    const cutoff28 = NOW.getTime() - 28 * DAY_MS;
    const videos = WORLD.published.map((e) => e.overview).filter((v) => !channel || v.channel_slug === channel);
    const recent28 = videos.filter((v) => new Date(v.published_at!).getTime() >= cutoff28);
    const weightedPct = recent28.reduce((acc, v) => acc + (v.average_view_pct ?? 0) * v.views, 0);
    const weight = recent28.reduce((acc, v) => acc + v.views, 0);
    const pipelineVideos = WORLD.pipeline.flatMap((p) => p.videos).filter((v) => !channel || channelBySlug(channel).id === v.channel_id);
    return {
      subscribers,
      subscribers_delta_7d: sumLast(rows, "subscribers_gained", 7, 0),
      views_7d: views7,
      views_7d_delta_pct: viewsPrev7 > 0 ? Number((((views7 - viewsPrev7) / viewsPrev7) * 100).toFixed(1)) : null,
      average_view_pct_28d: weight > 0 ? Number((weightedPct / weight).toFixed(1)) : null,
      watch_hours_28d: Math.round(minutes28 / 60),
      published_7d: videos.filter((v) => new Date(v.published_at!).getTime() >= cutoff7).length,
      pipeline: {
        generating: WORLD.pipeline.filter((p) => ["scripting", "generating", "assembling"].includes(p.card.production.status)).length,
        ready: WORLD.pipeline.filter((p) => p.card.production.status === "ready").length,
        scheduled: pipelineVideos.filter((v) => v.status === "scheduled").length,
        failed:
          WORLD.pipeline.filter((p) => p.card.production.status === "failed").length +
          pipelineVideos.filter((v) => v.status === "failed").length,
      },
      ypp: {
        subs_target: 1000,
        views_90d: sumLast(rows, "views", 90, 0),
        views_90d_target: 10_000_000,
      },
    } satisfies OverviewKpis;
  },

  async getDailyViews(days) {
    const fr = WORLD.channelDaily.fr.slice(-days);
    const en = WORLD.channelDaily.en.slice(-days);
    return fr.map((row, i): DailyViewsPoint => ({ day: row.day, fr: row.views, en: en[i]?.views ?? 0 }));
  },

  async getVideoDetail(id) {
    const entry = WORLD.published.find((e) => e.overview.id === id);
    if (!entry) return null;
    const detail: VideoDetail = {
      video: { ...entry.overview },
      daily: entry.daily.slice(-14),
      retention: entry.retention,
      comments: entry.comments,
      script: entry.production.script,
    };
    return detail;
  },

  async listProductions() {
    return WORLD.pipeline.map((p) => p.card);
  },

  async getProductionCard(id) {
    return WORLD.pipeline.find((p) => p.card.production.id === id)?.card ?? null;
  },

  async getSchedule(fromISO, days) {
    const start = parisStartOfDay(new Date(fromISO));
    const slots: ScheduleSlot[] = [];
    for (let i = 0; i < days; i++) {
      const dayDate = parisAddDays(start, i);
      for (const channel of CHANNELS) {
        for (const slot of channel.publish_slots) {
          const at = iso(parisSlot(dayDate, slot));
          slots.push({ channel_slug: channel.slug, at, video: WORLD.slotIndex.get(`${channel.slug}|${at}`) ?? null });
        }
      }
    }
    return slots;
  },

  async listConcepts() {
    return [...WORLD.concepts].sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
  },

  async getExperimentSummary() {
    const videos = WORLD.published.map((e) => e.overview);
    const formats: VideoFormat[] = ["A_voiceover", "B_visual"];
    const byFormat = formats.map((format) => {
      const list = videos.filter((v) => v.format === format);
      const views = list.reduce((a, v) => a + v.views, 0);
      const subs = list.reduce((a, v) => a + (v.subscribers_gained ?? 0), 0);
      return {
        format,
        videos: list.length,
        avg_view_pct: list.length ? Number((list.reduce((a, v) => a + (v.average_view_pct ?? 0), 0) / list.length).toFixed(1)) : 0,
        views_per_video: list.length ? Math.round(views / list.length) : 0,
        subs_per_1k_views: views ? Number(((subs / views) * 1000).toFixed(2)) : 0,
      };
    });
    const categories = Array.from(new Set(videos.map((v) => v.category ?? "autre")));
    const byCategory = categories
      .map((category) => {
        const list = videos.filter((v) => (v.category ?? "autre") === category);
        return {
          category,
          videos: list.length,
          avg_view_pct: Number((list.reduce((a, v) => a + (v.average_view_pct ?? 0), 0) / list.length).toFixed(1)),
          views_per_video: Math.round(list.reduce((a, v) => a + v.views, 0) / list.length),
        };
      })
      .sort((a, b) => b.views_per_video - a.views_per_video);
    const summary: ExperimentSummary = { byFormat, byCategory };
    return summary;
  },
};
