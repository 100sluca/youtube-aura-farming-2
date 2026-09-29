"use client";

/**
 * Aperçu 9:16 de l'onglet Montage : le clip (ou l'image) d'une production en fond, et par-dessus les trois couches du
 * modèle, dessinées comme le montage les grave (docs/23-montage.md) :
 *   - titre d'accroche : même découpage en lignes que Pillow (worker/hooktitle.py), plaques, marges, alignement ;
 *   - sous-titres : légendes du worker (mots par légende, deux lignes au plus), taille ASS (libass), contour, ombre,
 *     boîte, mot prononcé ; ils défilent comme sur la vidéo ;
 *   - textes à l'écran : boîte ou contour, rapetissés s'ils sont trop larges.
 * Tout est posé dans un repère 1080 × 1920 (px du final) mis à l'échelle. On déplace une couche à la souris (ou aux
 * flèches du clavier, Maj = 10 px) ; elle s'aimante au centre. Le bouton « Rendu exact » de l'éditeur montre le vrai
 * rendu FFmpeg.
 */
import * as React from "react";

import {
  FRAME_H,
  FRAME_W,
  LAYER_LABELS,
  type FontFaceInfo,
  type LayerKey,
  type MontageBackground,
  type MontageFormat,
  type MontageTemplate,
} from "@/lib/montage-types";
import {
  assEm,
  cleanHook,
  cssFamily,
  displayWord,
  distributeWords,
  groupWords,
  hexToRgba,
  pickFace,
  shadowOffset,
  splitLines,
  stripEmojis,
} from "@/lib/montage-text";

const LOOP_S = 5; // durée d'une boucle de l'aperçu (comme le rendu exact)
const SNAP = 14; // px du final : aimantation au centre

/** Zones que l'interface de YouTube Shorts recouvre souvent (approximatives, téléphone 9:16). */
const SAFE_ZONES = [
  { x: 0, y: 0, w: 1080, h: 120, label: "Barre du haut" },
  { x: 950, y: 800, w: 130, h: 740, label: "Boutons" },
  { x: 0, y: 1540, w: 1080, h: 380, label: "Titre, chaîne, son" },
];

/** Incrémenté quand le navigateur a fini de charger des polices : les mesures de texte sont alors refaites. */
function useFontsVersion(): number {
  const [version, setVersion] = React.useState(0);
  React.useEffect(() => {
    const fonts = document.fonts;
    const bump = () => setVersion((v) => v + 1);
    fonts.addEventListener("loadingdone", bump);
    void fonts.ready.then(bump);
    return () => fonts.removeEventListener("loadingdone", bump);
  }, []);
  return version;
}

/** Vrai dans le navigateur seulement : les mesures de texte ont besoin d'un canvas (l'aperçu n'est pas rendu côté serveur). */
const noop = () => () => undefined;
function useIsClient(): boolean {
  return React.useSyncExternalStore(noop, () => true, () => false);
}

let measureCtx: CanvasRenderingContext2D | null = null;
function measure(text: string, font: string, letterSpacing = 0): number {
  if (typeof document === "undefined") return text.length * 20;
  measureCtx ??= document.createElement("canvas").getContext("2d");
  if (!measureCtx) return text.length * 20;
  measureCtx.font = font;
  return measureCtx.measureText(text).width + letterSpacing * Math.max(0, text.length - 1);
}

/** Les @font-face de l'aperçu : chaque police en deux variantes, métriques verticales de libass (a) et de Pillow (p). */
export function MontageFontFaces({ faces }: { faces: FontFaceInfo[] }) {
  const css = faces
    .map((f) => {
      const id = f.id.replace(/[^A-Za-z0-9_-]/g, "_");
      const pct = (v: number) => `${((v / f.unitsPerEm) * 100).toFixed(3)}%`;
      const src = `src: url("${f.url}") format("${f.file.toLowerCase().endsWith(".otf") ? "opentype" : "truetype"}");`;
      return [
        `@font-face { font-family: "yt2a-${id}"; ${src} ascent-override: ${pct(f.winAscent)}; descent-override: ${pct(f.winDescent)}; line-gap-override: 0%; font-display: swap; }`,
        `@font-face { font-family: "yt2p-${id}"; ${src} ascent-override: ${pct(f.hheaAscent)}; descent-override: ${pct(f.hheaDescent)}; line-gap-override: 0%; font-display: swap; }`,
      ].join("\n");
    })
    .join("\n");
  return <style>{`${css}\n${ANIMATIONS}`}</style>;
}

const ANIMATIONS = `
@keyframes yt2-pop { 0% { transform: translate(-50%, -50%) scale(.8); } 56% { transform: translate(-50%, -50%) scale(1.08); } 100% { transform: translate(-50%, -50%) scale(1); } }
@keyframes yt2-bounce { 0% { transform: translate(-50%, -50%) scale(.6); } 44% { transform: translate(-50%, -50%) scale(1.18); } 76% { transform: translate(-50%, -50%) scale(.94); } 100% { transform: translate(-50%, -50%) scale(1); } }
@keyframes yt2-fade { from { opacity: 0; } to { opacity: 1; } }
@keyframes yt2-slide { from { transform: translate(-50%, calc(-50% + 60px)); } to { transform: translate(-50%, -50%); } }
`;
const ANIMATION_CSS: Record<string, string | undefined> = {
  pop: "yt2-pop 160ms ease-out",
  bounce: "yt2-bounce 250ms ease-out",
  fade: "yt2-fade 120ms linear",
  slide_up: "yt2-slide 160ms ease-out",
};

export interface StageProps {
  template: MontageTemplate;
  format: MontageFormat;
  faces: FontFaceInfo[];
  background: MontageBackground | null;
  texts: { hook: string; subtitle: string; title: string };
  selected: LayerKey | null;
  onSelect: (layer: LayerKey | null) => void;
  onMove: (layer: LayerKey, pos: { x: number; y: number }) => void;
  playing: boolean;
  showSafe: boolean;
  width: number;
}

type Drag = { layer: LayerKey; startX: number; startY: number; fromX: number; fromY: number; pointer: number };

export function MontageStage(props: StageProps) {
  const isClient = useIsClient();
  if (!isClient) {
    return <div className="shrink-0 rounded-xl bg-black/80" style={{ width: props.width, height: (props.width * FRAME_H) / FRAME_W }} />;
  }
  return <Stage {...props} />;
}

function Stage(props: StageProps) {
  const { template, format, faces, background, texts, selected, onSelect, onMove, playing, showSafe, width } = props;
  const scale = width / FRAME_W;
  const fontsVersion = useFontsVersion();
  const [time, setTime] = React.useState(1.2);
  const [drag, setDrag] = React.useState<Drag | null>(null);
  const [guides, setGuides] = React.useState<{ v: boolean; h: boolean }>({ v: false, h: false });
  const videoRef = React.useRef<HTMLVideoElement>(null);

  React.useEffect(() => {
    if (!playing) {
      videoRef.current?.pause();
      return;
    }
    void videoRef.current?.play().catch(() => undefined);
    let raf = 0;
    const t0 = performance.now() - time * 1000;
    const tick = (now: number) => {
      setTime(((now - t0) / 1000) % LOOP_S);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- la boucle repart de l'instant affiché
  }, [playing]);

  const shows = {
    hook: template.hook.formats.includes(format) && Boolean(cleanHook(texts.hook)),
    subtitles: format === "story" && template.subtitles.enabled,
    titles: template.titles.formats.includes(format),
  };
  const arialBlack = faces.find((f) => f.id === "win~ariblk.ttf") ?? null;

  // ---- Titre d'accroche : mise en page de Pillow (render_image) ----
  const hook = React.useMemo(() => {
    const h = template.hook;
    const picked = pickFace(faces, h.font_family, h.bold);
    const face = picked.face ?? arialBlack; // Pillow se rabat sur Arial Black
    const fontCss = cssFamily(face, "pil", '"Arial Black", Arial, sans-serif');
    const weight = picked.synthetic && picked.face ? "bold" : "normal";
    const font = `${weight} ${h.size}px ${fontCss}`;
    let text = cleanHook(texts.hook);
    if (h.uppercase) text = text.toUpperCase();
    const bg = h.background !== "none";
    const stroke = bg ? 0 : h.outline_width;
    const maxW = Math.max(50, Math.floor(FRAME_W * h.width_pct) - 2 * h.padding_x);
    const lines: string[] = [];
    let cur: string[] = [];
    for (const word of text.split(" ").filter(Boolean)) {
      const trial = [...cur, word].join(" ");
      if (cur.length && measure(trial, font) > maxW) {
        lines.push(cur.join(" "));
        cur = [word];
      } else cur.push(word);
    }
    if (cur.length) lines.push(cur.join(" "));
    if (!lines.length) lines.push(text);
    const upm = face?.unitsPerEm ?? 2048;
    const asc = Math.ceil(((face?.hheaAscent ?? 2254) * h.size) / upm);
    const desc = Math.ceil(((face?.hheaDescent ?? 634) * h.size) / upm);
    const boxH = asc + desc + 2 * h.padding_y;
    const step = Math.max(1, Math.floor(boxH * h.line_spacing));
    const blockH = step * (lines.length - 1) + boxH;
    const widths = lines.map((l) => Math.floor(measure(l, font)));
    const blockW = Math.max(...widths) + 2 * h.padding_x;
    const left = blockW <= FRAME_W ? Math.min(Math.max(0, h.x - Math.floor(blockW / 2)), FRAME_W - blockW) : Math.floor((FRAME_W - blockW) / 2);
    return { h, fontCss, weight, lines, widths, asc, desc, boxH, step, blockH, blockW, left, top: h.y + stroke, stroke, bg };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fontsVersion : refaire les mesures quand une police arrive
  }, [template.hook, texts.hook, faces, arialBlack, fontsVersion]);

  // ---- Sous-titres : légendes du worker, qui défilent ----
  const subs = template.subtitles;
  const captions = React.useMemo(
    () => groupWords(distributeWords(texts.subtitle, 0.3, LOOP_S - 0.3), subs),
    [texts.subtitle, subs],
  );
  const caption = captions.find((c) => time >= c.start && time < c.end) ?? (playing ? null : captions[0] ?? null);
  const captionIndex = caption ? captions.indexOf(caption) : -1;
  const subFace = pickFace(faces, subs.font_family, subs.bold);

  // ---- Textes à l'écran : rapetissés s'ils sont trop larges (comme _fit_size) ----
  const titles = template.titles;
  const titleText = React.useMemo(() => {
    const raw = stripEmojis(texts.title).trim();
    return titles.uppercase ? raw.toUpperCase() : raw;
  }, [texts.title, titles.uppercase]);
  const titleFace = pickFace(faces, titles.font_family, titles.bold);
  const titleSize = React.useMemo(() => {
    const border = titles.background === "box" ? titles.padding : titles.background === "outline" ? titles.outline_width : 0;
    const room = 1000 - 2 * border;
    const em = assEm(titleFace.face, titles.size);
    const w = measure(titleText, `${titleFace.synthetic ? "bold" : "normal"} ${em}px ${cssFamily(titleFace.face, "ass", titles.font_family)}`, subs.letter_spacing);
    return w > room && w > 0 ? Math.max(Math.round(titles.size * 0.55), Math.floor((titles.size * room) / w)) : titles.size;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fontsVersion : refaire la mesure quand la police arrive
  }, [titleText, titles, titleFace.face, titleFace.synthetic, subs.letter_spacing, fontsVersion]);

  // ---- Déplacement ----
  const positionOf = (layer: LayerKey) => template[layer];
  const startDrag = (layer: LayerKey) => (e: React.PointerEvent) => {
    e.preventDefault();
    e.stopPropagation();
    onSelect(layer);
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    const p = positionOf(layer);
    setDrag({ layer, startX: e.clientX, startY: e.clientY, fromX: p.x, fromY: p.y, pointer: e.pointerId });
  };
  const moveDrag = (e: React.PointerEvent) => {
    if (!drag || e.pointerId !== drag.pointer) return;
    let x = Math.round(drag.fromX + (e.clientX - drag.startX) / scale);
    let y = Math.round(drag.fromY + (e.clientY - drag.startY) / scale);
    const snapV = Math.abs(x - FRAME_W / 2) <= SNAP;
    if (snapV) x = FRAME_W / 2;
    const snapH = drag.layer !== "hook" && Math.abs(y - FRAME_H / 2) <= SNAP;
    if (snapH) y = FRAME_H / 2;
    setGuides({ v: snapV, h: snapH });
    x = Math.min(FRAME_W, Math.max(0, x));
    y = drag.layer === "hook" ? Math.min(1800, Math.max(0, y)) : Math.min(1880, Math.max(40, y));
    onMove(drag.layer, { x, y });
  };
  const endDrag = () => {
    setDrag(null);
    setGuides({ v: false, h: false });
  };
  const nudge = (layer: LayerKey) => (e: React.KeyboardEvent) => {
    const d = e.shiftKey ? 10 : 1;
    const delta: Record<string, [number, number]> = { ArrowLeft: [-d, 0], ArrowRight: [d, 0], ArrowUp: [0, -d], ArrowDown: [0, d] };
    const move = delta[e.key];
    if (!move) return;
    e.preventDefault();
    const p = positionOf(layer);
    onMove(layer, { x: Math.min(FRAME_W, Math.max(0, p.x + move[0])), y: Math.max(layer === "hook" ? 0 : 40, p.y + move[1]) });
  };
  const layerProps = (layer: LayerKey) => ({
    role: "button" as const,
    tabIndex: 0,
    "aria-label": `${LAYER_LABELS[layer]} : cliquer-glisser pour déplacer, flèches pour ajuster`,
    onPointerDown: startDrag(layer),
    onPointerMove: moveDrag,
    onPointerUp: endDrag,
    onPointerCancel: endDrag,
    onKeyDown: nudge(layer),
    onFocus: () => onSelect(layer),
  });
  const ring = (layer: LayerKey): React.CSSProperties =>
    selected === layer
      ? { outline: `${2 / scale}px dashed rgba(56, 189, 248, 0.95)`, outlineOffset: `${6 / scale}px` }
      : {};
  const ghost = (visible: boolean): React.CSSProperties => (visible ? {} : { opacity: 0.3 });

  // ---- Rendu ----
  const h = hook.h;
  // Titre éphémère : il s'efface en fondu de 0,4 s à la fin de son temps, comme au montage (worker/hooktitle.py, fade_filter)
  const hookFade = h.duration_s !== null && playing ? Math.min(1, Math.max(0, (h.duration_s - time) / Math.min(0.4, h.duration_s / 2))) : 1;
  const hookVisible = shows.hook && hookFade > 0;
  const sd = shadowOffset(subs.shadow_distance, subs.shadow_angle);
  const shadowOn = subs.shadow_opacity > 0 && (subs.shadow_distance > 0 || subs.shadow_blur > 0) && subs.background !== "box";
  const subEm = assEm(subFace.face, subs.font_size);
  const subFont: React.CSSProperties = {
    fontFamily: cssFamily(subFace.face, "ass", subs.font_family),
    fontSize: subEm,
    fontWeight: subFace.synthetic ? "bold" : "normal",
    fontStyle: subs.italic ? "italic" : "normal",
    letterSpacing: subs.letter_spacing,
    lineHeight: "normal",
    whiteSpace: "pre",
    textAlign: "center",
  };
  const words = caption ? caption.words.map((w) => displayWord(w.text, subs.text_transform)) : [];
  const active = caption ? Math.max(0, caption.words.filter((w) => w.start <= time).length - 1) : -1;
  const captionLines = caption ? splitLines(words, subs.max_chars) : [];
  const wordColor = (k: number) => {
    if (subs.highlight_mode === "word") return k === active ? subs.highlight_color : subs.text_color;
    if (subs.highlight_mode === "karaoke") return k <= active ? subs.highlight_color : subs.text_color;
    return subs.text_color;
  };
  const renderLines = (colorOf: (k: number) => string) => {
    let k = -1;
    return captionLines.map((line, i) => (
      <React.Fragment key={i}>
        {i > 0 ? "\n" : null}
        {line.map((w, j) => {
          k += 1;
          return (
            <React.Fragment key={j}>
              {j > 0 ? " " : null}
              <span style={{ color: colorOf(k) }}>{w}</span>
            </React.Fragment>
          );
        })}
      </React.Fragment>
    ));
  };
  const titleEm = assEm(titleFace.face, titleSize);
  const titleShown = format === "timelapse" ? (titles.uppercase ? texts.title.toUpperCase() : texts.title) : titleText;

  return (
    <div
      className="relative shrink-0 overflow-hidden rounded-xl bg-black shadow-lg ring-1 ring-black/10 select-none"
      style={{ width, height: (width * FRAME_H) / FRAME_W }}
      onPointerDown={() => onSelect(null)}
    >
      <div className="absolute top-0 left-0 origin-top-left" style={{ width: FRAME_W, height: FRAME_H, transform: `scale(${scale})` }}>
        {background?.kind === "clip" ? (
          <video
            ref={videoRef}
            key={background.url}
            src={background.url}
            className="absolute inset-0 size-full object-cover"
            muted
            loop
            playsInline
            autoPlay={playing}
            preload="auto"
          />
        ) : background?.kind === "image" ? (
          // eslint-disable-next-line @next/next/no-img-element -- fichier local servi par /api/media
          <img src={background.url} alt="" className="absolute inset-0 size-full object-cover" draggable={false} />
        ) : (
          <div className="absolute inset-0" style={{ background: "linear-gradient(160deg, #2B3A55, #C9A66B)" }} />
        )}

        {showSafe
          ? SAFE_ZONES.map((z) => (
              <div
                key={z.label}
                className="pointer-events-none absolute flex items-center justify-center"
                style={{
                  left: z.x,
                  top: z.y,
                  width: z.w,
                  height: z.h,
                  background: "repeating-linear-gradient(135deg, rgba(239,68,68,.28) 0 18px, rgba(239,68,68,.12) 18px 36px)",
                  border: "3px dashed rgba(239,68,68,.7)",
                }}
              >
                <span className="rounded bg-black/60 px-3 py-1 text-[26px] font-medium text-white">{z.label}</span>
              </div>
            ))
          : null}

        {/* Sous-titres (couches ASS 1 et 2) */}
        {(shows.subtitles || selected === "subtitles") && caption ? (
          <>
            {shadowOn && shows.subtitles ? (
              <div
                aria-hidden
                className="pointer-events-none absolute"
                style={{
                  ...subFont,
                  left: subs.x + sd[0],
                  top: subs.y + sd[1],
                  transform: "translate(-50%, -50%)",
                  color: hexToRgba(subs.shadow_color, subs.shadow_opacity),
                  WebkitTextStroke: subs.outline_width ? `${subs.outline_width * 2}px ${hexToRgba(subs.shadow_color, subs.shadow_opacity)}` : undefined,
                  paintOrder: "stroke fill",
                  filter: subs.shadow_blur ? `blur(${subs.shadow_blur * 0.6}px)` : undefined,
                }}
              >
                {renderLines(() => hexToRgba(subs.shadow_color, subs.shadow_opacity))}
              </div>
            ) : null}
            <div
              key={`cap-${captionIndex}`}
              {...layerProps("subtitles")}
              className="absolute cursor-move touch-none"
              style={{
                ...subFont,
                ...ghost(shows.subtitles),
                ...ring("subtitles"),
                left: subs.x,
                top: subs.y,
                transform: "translate(-50%, -50%)",
                animation: playing ? ANIMATION_CSS[subs.animation] : undefined,
                WebkitTextStroke: subs.outline_width ? `${subs.outline_width * 2}px ${subs.outline_color}` : undefined,
                paintOrder: "stroke fill",
                padding: subs.background === "box" ? subs.outline_width + subs.background_padding : 0,
                background: subs.background === "box" ? hexToRgba(subs.background_color, subs.background_opacity) : undefined,
              }}
            >
              {renderLines(wordColor)}
            </div>
          </>
        ) : null}

        {/* Textes à l'écran (couche ASS 3) */}
        {shows.titles || selected === "titles" ? (
          <div
            {...layerProps("titles")}
            className="absolute cursor-move touch-none"
            style={{
              ...ghost(shows.titles),
              ...ring("titles"),
              left: titles.x,
              top: titles.y,
              transform: "translate(-50%, -50%)",
              fontFamily: cssFamily(titleFace.face, "ass", titles.font_family),
              fontSize: titleEm,
              fontWeight: titleFace.synthetic ? "bold" : "normal",
              letterSpacing: subs.letter_spacing,
              lineHeight: "normal",
              whiteSpace: "pre",
              color: titles.text_color,
              padding: titles.background === "box" ? titles.padding : 0,
              background: titles.background === "box" ? hexToRgba(titles.box_color, titles.box_opacity) : undefined,
              WebkitTextStroke: titles.background === "outline" && titles.outline_width ? `${titles.outline_width * 2}px ${titles.outline_color}` : undefined,
              paintOrder: "stroke fill",
            }}
          >
            {titleShown || " "}
          </div>
        ) : null}

        {/* Titre d'accroche (PNG incrusté par-dessus tout) */}
        {hookVisible || (selected === "hook" && hook.lines.length) ? (
          <div
            {...layerProps("hook")}
            className="absolute cursor-move touch-none"
            style={{
              ...(hookVisible && hookFade < 1 ? { opacity: hookFade } : ghost(hookVisible)),
              ...ring("hook"),
              left: hook.left,
              top: hook.top,
              width: hook.blockW,
              height: hook.blockH,
            }}
          >
            {hook.bg && h.background === "block" ? (
              <div
                className="absolute inset-0"
                style={{ borderRadius: Math.min(h.radius, Math.floor(hook.blockH / 2)), background: hexToRgba(h.background_color, h.background_opacity) }}
              />
            ) : null}
            {hook.lines.map((line, i) => {
              const lineW = hook.widths[i] + 2 * h.padding_x;
              const x0 = h.align === "left" ? 0 : h.align === "right" ? hook.blockW - lineW : Math.floor((hook.blockW - lineW) / 2);
              return (
                <div key={i} className="absolute" style={{ left: x0, top: i * hook.step, width: lineW, height: hook.boxH }}>
                  {hook.bg && h.background === "plate" ? (
                    <div
                      className="absolute inset-0"
                      style={{ borderRadius: Math.min(h.radius, Math.floor(hook.boxH / 2)), background: hexToRgba(h.background_color, h.background_opacity) }}
                    />
                  ) : null}
                  <span
                    className="absolute whitespace-pre"
                    style={{
                      left: h.padding_x,
                      top: h.padding_y,
                      height: hook.asc + hook.desc,
                      lineHeight: `${hook.asc + hook.desc}px`,
                      fontFamily: hook.fontCss,
                      fontSize: h.size,
                      fontWeight: hook.weight,
                      color: h.text_color,
                      WebkitTextStroke: hook.stroke ? `${hook.stroke * 2}px ${h.outline_color}` : undefined,
                      paintOrder: "stroke fill",
                    }}
                  >
                    {line}
                  </span>
                </div>
              );
            })}
          </div>
        ) : null}

        {guides.v ? <div className="pointer-events-none absolute top-0 h-full bg-sky-400" style={{ left: FRAME_W / 2 - 2, width: 4 }} /> : null}
        {guides.h ? <div className="pointer-events-none absolute left-0 w-full bg-sky-400" style={{ top: FRAME_H / 2 - 2, height: 4 }} /> : null}
      </div>
      {drag ? (
        <div className="pointer-events-none absolute top-2 left-2 rounded bg-black/70 px-2 py-0.5 font-mono text-[11px] text-white">
          {LAYER_LABELS[drag.layer]} · x {template[drag.layer].x} · y {template[drag.layer].y}
        </div>
      ) : null}
    </div>
  );
}
