"use client";

import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectSeparator, SelectTrigger, SelectValue } from "@/components/ui/select";
import { MODIFIER_VOICES } from "@/lib/long-types";
import { VOICE_MOD_PREFIX, type VoiceProfile } from "@/lib/voice-mods";

/** Nom d'une voix du modificateur : un réglage du Studio (docs/67) ou une voix d'arrivée de Chatterbox (docs/63 §4). */
export function modifierVoiceLabel(id: string, profiles: VoiceProfile[]): string {
  if (id.startsWith(VOICE_MOD_PREFIX)) return profiles.find((p) => VOICE_MOD_PREFIX + p.id === id)?.name ?? "réglage supprimé";
  return MODIFIER_VOICES.find((m) => m.id === id)?.label ?? id;
}

/** Choix de la voix du modificateur : d'abord les réglages de Luca, puis les voix d'IA de Chatterbox. */
export function ModifierVoiceSelect({
  value,
  onChange,
  profiles,
  className = "w-64",
}: {
  value: string;
  onChange: (v: string) => void;
  profiles: VoiceProfile[];
  className?: string;
}) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className={className}>
        <SelectValue>{modifierVoiceLabel(value, profiles)}</SelectValue>
      </SelectTrigger>
      <SelectContent>
        <SelectGroup>
          <SelectLabel>Mes réglages (Studio du modificateur)</SelectLabel>
          {profiles.length ? (
            profiles.map((p) => (
              <SelectItem key={p.id} value={VOICE_MOD_PREFIX + p.id}>
                {p.name}
              </SelectItem>
            ))
          ) : (
            <SelectItem value="__aucun" disabled>
              Aucun réglage pour l’instant
            </SelectItem>
          )}
        </SelectGroup>
        <SelectSeparator />
        <SelectGroup>
          <SelectLabel>Voix d’IA (Chatterbox)</SelectLabel>
          {MODIFIER_VOICES.map((m) => (
            <SelectItem key={m.id} value={m.id}>
              {m.label}
            </SelectItem>
          ))}
        </SelectGroup>
      </SelectContent>
    </Select>
  );
}
