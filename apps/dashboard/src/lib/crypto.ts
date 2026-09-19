/**
 * Chiffrement des refresh tokens (AES-GCM, Web Crypto).
 * Format : base64(nonce[12] + ciphertext). Le worker Python déchiffre avec la même clé
 * (`CREDENTIALS_KEY`, 32 octets en base64) — voir services/worker/worker/youtube/auth.py.
 */

function keyBytes(): Uint8Array<ArrayBuffer> {
  const b64 = process.env.CREDENTIALS_KEY;
  if (!b64) throw new Error("CREDENTIALS_KEY manquante");
  const raw = Buffer.from(b64, "base64");
  if (raw.length !== 32) throw new Error("CREDENTIALS_KEY doit faire 32 octets (base64)");
  return new Uint8Array(raw);
}

async function importKey(): Promise<CryptoKey> {
  return crypto.subtle.importKey("raw", keyBytes(), { name: "AES-GCM" }, false, ["encrypt", "decrypt"]);
}

export async function encryptSecret(plain: string): Promise<string> {
  const key = await importKey();
  const nonce = crypto.getRandomValues(new Uint8Array(12));
  const cipher = new Uint8Array(
    await crypto.subtle.encrypt({ name: "AES-GCM", iv: nonce }, key, new TextEncoder().encode(plain)),
  );
  const out = new Uint8Array(nonce.length + cipher.length);
  out.set(nonce);
  out.set(cipher, nonce.length);
  return Buffer.from(out).toString("base64");
}

export async function decryptSecret(payload: string): Promise<string> {
  const key = await importKey();
  const raw = new Uint8Array(Buffer.from(payload, "base64"));
  const plain = await crypto.subtle.decrypt({ name: "AES-GCM", iv: raw.slice(0, 12) }, key, raw.slice(12));
  return new TextDecoder().decode(plain);
}

/** HMAC-SHA256 en base64url : signe le paramètre `state` du flux OAuth. */
export async function sign(data: string, secret: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"],
  );
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(data));
  return Buffer.from(sig).toString("base64url");
}
