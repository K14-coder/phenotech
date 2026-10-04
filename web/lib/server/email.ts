// Email for Tasukeru: SMTP (the mehro.ch mailbox) or Resend's HTTP API, with a dry-run sender for local tests.
//  - EMAIL_DRY_RUN=1: write each email to web/.data/outbox/ (gitignored) instead of sending.
//  - SMTP_HOST + SMTP_PORT + SMTP_USER + SMTP_PASS: send through that server with nodemailer
//    (port 465: TLS from the start; 587: STARTTLS required; other ports: STARTTLS if offered).
//  - RESEND_API_KEY: send through https://api.resend.com/emails.
//  - EMAIL_FROM: the sender, e.g. "Tasukeru <no-reply@mehro.ch>".
//  - neither: log "email disabled" (never the address); notices stay in the inbox only.
// Until a sending domain is verified, Resend delivers only to the account owner's own address:
// EMAIL_DOMAIN_VERIFIED=1 tells the admin page the domain is verified.
import { mkdir, writeFile } from "node:fs/promises";
import nodemailer, { type Transporter } from "nodemailer";
import path from "node:path";

export type EmailMode = "dry-run" | "smtp" | "resend" | "disabled";

const smtpReady = () => !!(process.env.SMTP_HOST && process.env.SMTP_PORT && process.env.SMTP_USER && process.env.SMTP_PASS);

/** dry run first (local tests), then the mailbox's own SMTP server, then Resend, else disabled. */
export function emailMode(): EmailMode {
  if (process.env.EMAIL_DRY_RUN === "1") return "dry-run";
  if (smtpReady()) return "smtp";
  if (process.env.RESEND_API_KEY) return "resend";
  return "disabled";
}

export function emailStatus() {
  return { mode: emailMode(), domainVerified: process.env.EMAIL_DOMAIN_VERIFIED === "1" };
}

/** Sender: EMAIL_FROM (e.g. "Tasukeru <no-reply@mehro.ch>"); a bare address gets the Tasukeru display name. */
export function fromAddress(): string {
  const raw = (process.env.EMAIL_FROM ?? "").trim() || (emailMode() === "smtp" ? (process.env.SMTP_USER ?? "") : "onboarding@resend.dev");
  return raw.includes("<") ? raw : `Tasukeru <${raw}>`;
}

/** Absolute base URL for links in emails: APP_URL, else the production URL Vercel provides, else the request. */
export function baseUrl(req?: Request): string {
  const env = process.env.APP_URL ?? (process.env.VERCEL_PROJECT_PRODUCTION_URL ? `https://${process.env.VERCEL_PROJECT_PRODUCTION_URL}` : null);
  if (env) return env.replace(/\/$/, "");
  if (req) return new URL(req.url).origin;
  return "http://127.0.0.1:3000";
}

export interface Unsub {
  page: string;
  post: string;
}

export interface Email {
  to: string;
  subject: string;
  html: string;
  text: string;
  /** unsubscribe links: `page` for people (a confirmation page that unsubscribes on open), `post` for the List-Unsubscribe header (RFC 8058 one-click POST) */
  unsubscribe?: Unsub;
  /** short tag for the outbox file name and logs, e.g. "verify" */
  tag: string;
}

let smtp: Transporter | null = null;
let smtpKey = "";
function smtpTransport(): Transporter {
  const port = Number(process.env.SMTP_PORT);
  const key = `${process.env.SMTP_HOST}:${port}:${process.env.SMTP_USER}`;
  if (!smtp || key !== smtpKey) {
    smtp = nodemailer.createTransport({
      host: process.env.SMTP_HOST,
      port,
      secure: port === 465,
      requireTLS: port === 587,
      auth: { user: process.env.SMTP_USER, pass: process.env.SMTP_PASS },
      connectionTimeout: 10_000,
      greetingTimeout: 10_000,
      socketTimeout: 20_000,
      // never let nodemailer log message contents or credentials
      logger: false,
      debug: false,
    });
    smtpKey = key;
  }
  return smtp;
}

export interface SendResult {
  sent: boolean;
  mode: EmailMode;
  /** a short error code only (EAUTH, ECONNECTION, HTTP 403 ...), never addresses or credentials */
  error?: string;
}

export async function sendEmail(e: Email): Promise<SendResult> {
  const mode = emailMode();
  const subject = e.subject.replace(/[\r\n]+/g, " ").slice(0, 200);
  const headers: Record<string, string> = e.unsubscribe ? { "List-Unsubscribe": `<${e.unsubscribe.post}>`, "List-Unsubscribe-Post": "List-Unsubscribe=One-Click" } : {};
  if (mode === "disabled") {
    console.info(`email disabled (${e.tag})`);
    return { sent: false, mode, error: "disabled" };
  }
  if (mode === "dry-run") {
    try {
      const dir = path.join(process.cwd(), ".data", "outbox");
      await mkdir(dir, { recursive: true });
      const base = `${new Date().toISOString().replace(/[:.]/g, "-")}-${e.tag}`;
      await writeFile(path.join(dir, `${base}.json`), JSON.stringify({ from: fromAddress(), to: e.to, subject, headers, text: e.text }, null, 2));
      await writeFile(path.join(dir, `${base}.html`), e.html);
      return { sent: true, mode };
    } catch {
      console.error(`email dry run could not write the outbox (${e.tag})`);
      return { sent: false, mode, error: "outbox" };
    }
  }
  if (mode === "smtp") {
    try {
      await smtpTransport().sendMail({ from: fromAddress(), to: e.to, subject, html: e.html, text: e.text, headers });
      return { sent: true, mode };
    } catch (err) {
      const code = String((err as { code?: string; responseCode?: number })?.code ?? (err as { responseCode?: number })?.responseCode ?? "error").slice(0, 24);
      console.error(`email send failed (${e.tag}): smtp ${code}`);
      return { sent: false, mode, error: `smtp ${code}` };
    }
  }
  try {
    const r = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: { Authorization: `Bearer ${process.env.RESEND_API_KEY}`, "Content-Type": "application/json" },
      body: JSON.stringify({ from: fromAddress(), to: [e.to], subject, html: e.html, text: e.text, headers }),
    });
    if (!r.ok) console.error(`email send failed (${e.tag}): HTTP ${r.status}`);
    return r.ok ? { sent: true, mode } : { sent: false, mode, error: `HTTP ${r.status}` };
  } catch {
    console.error(`email send failed (${e.tag}): network error`);
    return { sent: false, mode, error: "network" };
  }
}

/** Admin "send a test email to myself". */
export function testEmail(to: string): Email {
  const subject = "Tasukeru: test email";
  return {
    to,
    subject,
    tag: "test",
    ...render(subject, {
      paragraphs: ["This is a test email from Tasukeru.", `It was sent with the ${emailMode()} transport on ${new Date().toISOString().slice(0, 16).replace("T", " ")} UTC.`],
      why: "You are receiving this because you asked for a test email on the Tasukeru admin page.",
    }),
  };
}

// ---------- templates: plain, kind, short; every email says why you get it ----------

const esc = (s: string) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);

interface Block {
  /** paragraphs of plain text */
  paragraphs: string[];
  button?: { label: string; url: string };
  /** a quoted block (announcement summary, researcher message) */
  quote?: { title?: string; lines: string[] };
  /** a list of linked items (studies) */
  items?: { label: string; title: string; url: string; meta?: string }[];
  why: string;
  unsubscribe?: Unsub;
}

function render(subject: string, b: Block): { html: string; text: string } {
  const p = (t: string) => `<p style="margin:0 0 14px;font-size:16px;line-height:1.5;color:#16181d">${esc(t)}</p>`;
  const html = `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>${esc(subject)}</title></head>
<body style="margin:0;padding:0;background:#f7f8f9;font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f7f8f9;padding:24px 12px"><tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:#ffffff;border:1px solid #e5e7eb;border-radius:12px;padding:28px">
<tr><td>
<p style="margin:0 0 18px;font-size:15px;font-weight:600;color:#1f5a96">Tasukeru <span style="font-weight:400;color:#5f6672">· a rare-disease atlas</span></p>
${b.paragraphs.map(p).join("\n")}
${b.quote ? `<div style="margin:6px 0 18px;padding:14px 16px;background:#f7f8f9;border-radius:8px">${b.quote.title ? `<p style="margin:0 0 8px;font-size:16px;font-weight:600;color:#16181d">${esc(b.quote.title)}</p>` : ""}${b.quote.lines.map((l) => `<p style="margin:0 0 6px;font-size:15px;line-height:1.5;color:#3f4550">${esc(l)}</p>`).join("")}</div>` : ""}
${b.items?.length ? `<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:6px 0 18px">${b.items.map((i) => `<tr><td style="padding:10px 0;border-top:1px solid #eff1f3"><p style="margin:0 0 2px;font-size:12px;letter-spacing:.04em;text-transform:uppercase;color:#5f6672">${esc(i.label)}</p><p style="margin:0;font-size:16px;line-height:1.4"><a href="${esc(i.url)}" style="color:#1f5a96;font-weight:600;text-decoration:none">${esc(i.title)}</a></p>${i.meta ? `<p style="margin:2px 0 0;font-size:14px;color:#5f6672">${esc(i.meta)}</p>` : ""}</td></tr>`).join("")}</table>` : ""}
${b.button ? `<p style="margin:8px 0 22px"><a href="${esc(b.button.url)}" style="display:inline-block;background:#1f5a96;color:#ffffff;text-decoration:none;font-size:16px;font-weight:600;padding:12px 18px;border-radius:8px">${esc(b.button.label)}</a></p><p style="margin:0 0 18px;font-size:13px;color:#5f6672;word-break:break-all">Or open this link: ${esc(b.button.url)}</p>` : ""}
<p style="margin:18px 0 0;padding-top:14px;border-top:1px solid #eff1f3;font-size:13px;line-height:1.5;color:#5f6672">${esc(b.why)}${b.unsubscribe ? ` <a href="${esc(b.unsubscribe.page)}" style="color:#5f6672">Unsubscribe in one click</a>.` : ""}<br>Tasukeru (助ける, “to help”) · a rare-disease atlas</p>
</td></tr></table></td></tr></table></body></html>`;
  const text = [
    "Tasukeru · a rare-disease atlas",
    "",
    ...b.paragraphs.flatMap((t) => [t, ""]),
    ...(b.quote ? [...(b.quote.title ? [b.quote.title] : []), ...b.quote.lines, ""] : []),
    ...(b.items ?? []).flatMap((i) => [`${i.label}: ${i.title}`, ...(i.meta ? [i.meta] : []), i.url, ""]),
    ...(b.button ? [`${b.button.label}: ${b.button.url}`, ""] : []),
    "--",
    b.why,
    "Tasukeru (助ける, \"to help\") · a rare-disease atlas",
    ...(b.unsubscribe ? [`Unsubscribe in one click: ${b.unsubscribe.page}`] : []),
  ].join("\n");
  return { html, text };
}

export function verificationEmail(to: string, url: string): Email {
  const subject = "Tasukeru: please confirm your email";
  return {
    to,
    subject,
    tag: "verify",
    ...render(subject, {
      paragraphs: ["Thank you for joining Tasukeru, the rare-disease atlas.", "Please confirm this is your email address. The link works for 7 days."],
      button: { label: "Confirm my email", url },
      why: "You are receiving this because someone used this address to create an account. If it wasn't you, ignore this email and nothing will happen.",
    }),
  };
}

export function resetEmail(to: string, url: string): Email {
  const subject = "Tasukeru: reset your password";
  return {
    to,
    subject,
    tag: "reset",
    ...render(subject, {
      paragraphs: ["Someone asked to reset the password for your Tasukeru account.", "The link works once, for one hour."],
      button: { label: "Choose a new password", url },
      why: "You are receiving this because a password reset was requested for this address. If it wasn't you, ignore this email; your password stays the same.",
    }),
  };
}

export function announcementEmail(
  to: string,
  a: { title: string; summary: string; eligibility: string; contact: string; organisation: string; ethics: string },
  diseases: string,
  meUrl: string,
  unsubscribe: Unsub,
): Email {
  const subject = `Tasukeru: a new study for ${diseases}`;
  return {
    to,
    subject,
    tag: "announcement",
    unsubscribe,
    ...render(subject, {
      paragraphs: [`${a.organisation} has announced a study for ${diseases}. Our team checked the announcement before sending it.`],
      quote: { title: a.title, lines: [a.summary, `Who can take part: ${a.eligibility}`, `How to get in touch: ${a.contact}`, `Ethics approval: ${a.ethics}`] },
      button: { label: "See it in my atlas", url: meUrl },
      why: `You are receiving this because you follow ${diseases} and asked to hear about studies. Taking part is always your choice.`,
      unsubscribe,
    }),
  };
}

export function contactEmail(to: string, organisation: string, message: string, diseases: string, verified: boolean, meUrl: string, unsubscribe: Unsub): Email {
  const subject = `Tasukeru: a researcher would like to hear from families (${diseases})`;
  return {
    to,
    subject,
    tag: "contact",
    unsubscribe,
    ...render(subject, {
      paragraphs: [
        `A researcher at ${organisation} sent this message to families who follow ${diseases}. They do not know your email address, and they will only hear from you if you choose to get in touch.`,
        verified ? "Their account uses an institutional email address." : "Their account is not verified yet, so please be careful.",
      ],
      quote: { lines: [message] },
      button: { label: "Read it in my atlas", url: meUrl },
      why: "You are receiving this because you said researchers may contact you through the atlas. You can turn this off in My atlas.",
      unsubscribe,
    }),
  };
}

export function trialsEmail(to: string, items: { disease: string; title: string; url: string; meta?: string }[], weekly: boolean, meUrl: string, unsubscribe: Unsub): Email {
  const grantsOnly = items.every((i) => i.disease.startsWith("New research"));
  const subject = weekly
    ? "Your Tasukeru weekly summary"
    : grantsOnly
      ? `Tasukeru: new researchers working on ${items[0].disease.replace(/^New research · /, "")}`
      : items.length === 1
        ? `Tasukeru: a study is recruiting for ${items[0].disease}`
        : "Tasukeru: news for diseases you follow";
  return {
    to,
    subject,
    tag: weekly ? "digest" : "trials",
    unsubscribe,
    ...render(subject, {
      paragraphs: [
        weekly
          ? "Here is what is new this week for the diseases you follow."
          : grantsOnly
            ? "Newly funded research projects name a gene behind a disease you follow. It means more researchers are working on it."
            : "We found new recruiting studies, or newly funded research, for diseases you follow.",
        grantsOnly
          ? "Each link opens the public project page at NIH RePORTER, with the institution doing the work."
          : "Ages, places and how to join are on each study page. A doctor can help you decide whether a study fits.",
      ],
      items: items.map((i) => ({ label: i.disease, title: i.title, url: i.url, meta: i.meta })),
      button: { label: "Open my atlas", url: meUrl },
      why: weekly
        ? "You are receiving this weekly summary because you follow these diseases and chose a weekly summary."
        : "You are receiving this because you follow these diseases and asked to hear about new studies and research.",
      unsubscribe,
    }),
  };
}
