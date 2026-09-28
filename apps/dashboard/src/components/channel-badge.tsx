import { Badge } from "@/components/ui/badge";
import { channelColor, channelInitials } from "@/lib/channel";
import { cn } from "@/lib/utils";

type ChannelLike = { slug: string; name: string; youtube_thumbnail_url?: string | null };

/** Pastille d'une chaîne : son nom, avec la couleur qui la suit partout (graphiques, calendrier). */
export function ChannelBadge({ channel, className }: { channel: { slug: string; name: string }; className?: string }) {
  const color = channelColor(channel.slug);
  return (
    <Badge
      variant="outline"
      className={cn("max-w-44 gap-1.5 font-medium", className)}
      style={{ borderColor: `color-mix(in oklab, ${color} 50%, transparent)` }}
    >
      <span className="size-2 shrink-0 rounded-full" style={{ background: color }} aria-hidden />
      <span className="truncate">{channel.name}</span>
    </Badge>
  );
}

/** Avatar d'une chaîne : l'image YouTube une fois connectée, sinon ses initiales sur sa couleur. */
export function ChannelAvatar({ channel, className }: { channel: ChannelLike; className?: string }) {
  if (channel.youtube_thumbnail_url) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img src={channel.youtube_thumbnail_url} alt="" className={cn("size-6 shrink-0 rounded-full object-cover", className)} />
    );
  }
  return (
    <span
      aria-hidden
      className={cn("flex size-6 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold text-white", className)}
      style={{ background: channelColor(channel.slug) }}
    >
      {channelInitials(channel.name)}
    </span>
  );
}
