/** Réglages → Notifications (docs/32-notifications-mail.md) : types partagés serveur / navigateur. */

export interface NotificationSettings {
  email_to: string; // adresse qui reçoit
  on_video_ready: boolean; // un mail dès qu'une vidéo est terminée
  sender: string; // compte Gmail qui envoie ; vide = l'adresse qui reçoit
}

export interface NotifyDelivery {
  kind: "video_ready" | "test";
  title: string;
  ok: boolean;
  at: string;
  error: string | null;
}

export interface NotifyStatus {
  passwordHint: string | null; // 4 derniers caractères du mot de passe d'application enregistré
  last: NotifyDelivery | null; // dernier mail parti ou refusé
  pending: number; // mails « vidéo terminée » en attente d'envoi
}

export interface TestMailState {
  state: "pending" | "sent" | "failed" | "unknown";
  message: string;
}

export const DEFAULT_ALERT_EMAIL = "adresse@example.com";
export const APP_PASSWORD_URL = "https://myaccount.google.com/apppasswords";
export const OUTBOX_HOURS = 6; // worker/notify.py : une alerte plus vieille ne part plus
