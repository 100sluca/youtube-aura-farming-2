/** Différences ligne à ligne entre deux textes (plus longue sous-suite commune), pour comparer deux versions d'un
 * prompt dans l'onglet Agents. Les prompts font quelques dizaines de lignes : le calcul complet suffit. */

export type DiffLine = { type: "same" | "add" | "del"; text: string };

export function diffLines(before: string, after: string): DiffLine[] {
  const a = before.split("\n");
  const b = after.split("\n");
  const n = a.length;
  const m = b.length;
  // lcs[i][j] = longueur de la plus longue sous-suite commune de a[i:] et b[j:]
  const lcs = Array.from({ length: n + 1 }, () => new Uint32Array(m + 1));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      lcs[i][j] = a[i] === b[j] ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1]);
    }
  }
  const out: DiffLine[] = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) {
      out.push({ type: "same", text: a[i] });
      i += 1;
      j += 1;
    } else if (lcs[i + 1][j] >= lcs[i][j + 1]) {
      out.push({ type: "del", text: a[i] });
      i += 1;
    } else {
      out.push({ type: "add", text: b[j] });
      j += 1;
    }
  }
  for (; i < n; i += 1) out.push({ type: "del", text: a[i] });
  for (; j < m; j += 1) out.push({ type: "add", text: b[j] });
  return out;
}

export type DiffBlock = { type: "lines"; lines: DiffLine[] } | { type: "skip"; count: number };

/** Garde `context` lignes identiques autour de chaque changement et replie le reste. */
export function foldDiff(lines: DiffLine[], context = 2): DiffBlock[] {
  const keep = lines.map((l) => l.type !== "same");
  const near = lines.map((_, k) => {
    for (let d = -context; d <= context; d += 1) if (keep[k + d]) return true;
    return false;
  });
  const blocks: DiffBlock[] = [];
  for (let k = 0; k < lines.length; ) {
    if (near[k]) {
      const run: DiffLine[] = [];
      while (k < lines.length && near[k]) run.push(lines[k++]);
      blocks.push({ type: "lines", lines: run });
    } else {
      let count = 0;
      while (k < lines.length && !near[k]) {
        count += 1;
        k += 1;
      }
      blocks.push({ type: "skip", count });
    }
  }
  return blocks;
}
