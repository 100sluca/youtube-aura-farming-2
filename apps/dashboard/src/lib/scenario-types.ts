/**
 * Mes scénarios (docs/59) : types et choix de la carte « Mon scénario » de Création, partagés par le serveur
 * (lib/scenarios.ts) et le composant client.
 */
export type ScenarioStyle = "auto" | "pixar_human" | "cinematic_real" | "dreamworks_animal" | "pixar_fruit";
export type ScenarioSpeech = "auto" | "muet" | "repliques" | "dialogues";

export const SCENARIO_STYLES: { value: ScenarioStyle; label: string }[] = [
  { value: "auto", label: "L’équipe choisit (réaliste d’habitude)" },
  { value: "cinematic_real", label: "Réaliste (prise de vue réelle)" },
  { value: "pixar_human", label: "Film d’animation (Pixar)" },
  { value: "dreamworks_animal", label: "Animaux qui parlent (DreamWorks)" },
  { value: "pixar_fruit", label: "Fruits (Pixar)" },
];

export const SCENARIO_SPEECH: { value: ScenarioSpeech; label: string }[] = [
  { value: "auto", label: "L’équipe choisit" },
  { value: "muet", label: "Sans paroles (jeu, regards, sons)" },
  { value: "repliques", label: "Quelques répliques" },
  { value: "dialogues", label: "Dialogues" },
];

export const SCENARIO_DURATIONS = [0, 30, 45, 60, 75] as const; // 0 = l'équipe choisit

export type ScenarioBeat = { what: string; shown?: string; why?: string; from_text?: string };

export type ScenarioPlan = {
  title: string;
  logline?: string;
  genre?: string;
  style?: string;
  style_why?: string;
  speech?: string;
  duration_s?: number;
  cast?: { key: string; name: string; role?: string; look?: string }[];
  beats?: ScenarioBeat[];
  hook_title?: string;
  choices?: string[];
  risks?: string[];
};

export type ScenarioItem = {
  conceptId: string;
  title: string;
  text: string;
  createdAt: string;
  style: string;
  speech: string;
  durationS: number | null;
  plan: ScenarioPlan | null;
  productionId: string | null;
  status: string | null;
  error: string | null;
  videoId: string | null;
  videoStatus: string | null;
};
