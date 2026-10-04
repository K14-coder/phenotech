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

/** Dry-run writer: web/.data/outbox/<time>-<tag>.json (from, to, subject, headers, text) and .html. Returns the base path. */
export async function writeOutbox(e: Email, name?: string): Promise<string> {
  const subject = e.subject.replace(/[\r\n]+/g, " ").slice(0, 200);
  const headers: Record<string, string> = e.unsubscribe ? { "List-Unsubscribe": `<${e.unsubscribe.post}>`, "List-Unsubscribe-Post": "List-Unsubscribe=One-Click" } : {};
  const dir = path.join(process.cwd(), ".data", "outbox");
  await mkdir(dir, { recursive: true });
  const base = name ?? `${new Date().toISOString().replace(/[:.]/g, "-")}-${e.tag}`;
  await writeFile(path.join(dir, `${base}.json`), JSON.stringify({ from: fromAddress(), to: e.to, subject, headers, text: e.text }, null, 2));
  await writeFile(path.join(dir, `${base}.html`), e.html);
  return path.join(".data", "outbox", base);
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
      await writeOutbox(e);
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
      paragraphs: ["Good news: email from Tasukeru reaches you.", `This test went out through the ${emailMode()} transport on ${new Date().toISOString().slice(0, 16).replace("T", " ")} UTC. Nothing else to do.`],
      why: "you asked for a test email on the Tasukeru admin page.",
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
  /** "Hi there," unless a name is known */
  name?: string | null;
}

/** Site origin for the logo and privacy links: from a link in the email, else APP_URL / the production URL. */
function originOf(b: Block): string {
  const u = b.button?.url ?? b.unsubscribe?.page ?? b.items?.[0]?.url;
  try {
    if (u && !/clinicaltrials\.gov|reporter\.nih\.gov/.test(u)) return new URL(u).origin;
  } catch {
    /* fall through */
  }
  return baseUrl();
}

// Palette: warm paper background, white card, the site's accent blue. The <style> block only adds dark-mode
// and phone tweaks; everything that matters is inline, so clients that drop <style> still render it well.
const C = { bg: "#f6f1ea", card: "#ffffff", line: "#ece4d8", ink: "#1d2027", ink2: "#3f4550", muted: "#857b6e", accent: "#1f5a96", quote: "#f8f5f0" };
const FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif";

function render(subject: string, b: Block): { html: string; text: string } {
  const origin = originOf(b);
  const greet = b.name ? `Hi ${b.name},` : "Hi there,";
  const p = (t: string) => `<p class="ink2" style="margin:0 0 16px;font-family:${FONT};font-size:16px;line-height:1.6;color:${C.ink2}">${esc(t)}</p>`;
  const quote = b.quote
    ? `<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:4px 0 22px"><tr><td class="quote" style="background:${C.quote};border-left:3px solid ${C.accent};border-radius:10px;padding:16px 18px">${
        b.quote.title ? `<p class="ink" style="margin:0 0 8px;font-family:${FONT};font-size:16px;font-weight:600;line-height:1.4;color:${C.ink}">${esc(b.quote.title)}</p>` : ""
      }${b.quote.lines.map((l) => `<p class="ink2" style="margin:0 0 6px;font-family:${FONT};font-size:15px;line-height:1.55;color:${C.ink2}">${esc(l)}</p>`).join("")}</td></tr></table>`
    : "";
  const items = b.items?.length
    ? `<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:4px 0 22px">${b.items
        .map(
          (i) =>
            `<tr><td class="quote" style="background:${C.quote};border-radius:10px;padding:14px 16px"><p class="muted" style="margin:0 0 4px;font-family:${FONT};font-size:12px;letter-spacing:.04em;text-transform:uppercase;color:${C.muted}">${esc(i.label)}</p><p style="margin:0;font-family:${FONT};font-size:16px;line-height:1.4"><a class="link" href="${esc(i.url)}" style="color:${C.accent};font-weight:600;text-decoration:none">${esc(i.title)}</a></p>${
              i.meta ? `<p class="muted" style="margin:4px 0 0;font-family:${FONT};font-size:14px;color:${C.muted}">${esc(i.meta)}</p>` : ""
            }</td></tr><tr><td style="height:10px;line-height:10px;font-size:10px">&nbsp;</td></tr>`,
        )
        .join("")}</table>`
    : "";
  const button = b.button
    ? `<table role="presentation" cellpadding="0" cellspacing="0" style="margin:8px 0 14px"><tr><td class="btn" bgcolor="${C.accent}" style="background:${C.accent};border-radius:12px"><a href="${esc(b.button.url)}" style="display:inline-block;padding:15px 28px;font-family:${FONT};font-size:17px;font-weight:600;color:#ffffff;text-decoration:none;border-radius:12px">${esc(b.button.label)}</a></td></tr></table>
<p class="muted" style="margin:0 0 22px;font-family:${FONT};font-size:13px;line-height:1.5;color:${C.muted};word-break:break-all">Button not working? Copy this link into your browser:<br><a class="link" href="${esc(b.button.url)}" style="color:${C.accent}">${esc(b.button.url)}</a></p>`
    : "";
  const preheader = b.paragraphs[0] ?? subject;
  const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light dark"><meta name="supported-color-schemes" content="light dark"><title>${esc(subject)}</title>
<style>
@media (prefers-color-scheme: dark) {
  .bg { background:#17191d !important; }
  .card { background:#23262c !important; border-color:#33373e !important; }
  .ink { color:#eef0f3 !important; }
  .ink2 { color:#cfd3d9 !important; }
  .muted { color:#a3a9b3 !important; }
  .quote { background:#2c3037 !important; }
  .btn { background:#3d7fc4 !important; }
  a.link { color:#9cc3ec !important; }
  .rule { border-color:#3a3e46 !important; }
}
@media (max-width:600px) { .pad { padding:28px 22px !important; } }
</style></head>
<body class="bg" style="margin:0;padding:0;background:${C.bg};-webkit-text-size-adjust:100%">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent">${esc(preheader)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="bg" bgcolor="${C.bg}" style="background:${C.bg}"><tr><td align="center" style="padding:32px 12px 40px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%">
<tr><td align="center" style="padding:0 0 20px"><a href="${esc(origin)}" style="text-decoration:none"><img src="${esc(origin)}/email/logo.png" width="120" height="32" alt="Tasukeru" style="display:block;border:0;outline:none;width:120px;height:32px"></a></td></tr>
<tr><td class="card pad" bgcolor="${C.card}" style="background:${C.card};border:1px solid ${C.line};border-radius:18px;padding:40px 40px 32px">
<p class="ink" style="margin:0 0 18px;font-family:${FONT};font-size:18px;font-weight:600;color:${C.ink}">${esc(greet)}</p>
${b.paragraphs.map(p).join("\n")}
${quote}${items}${button}
<p class="muted rule" style="margin:18px 0 0;padding-top:16px;border-top:1px solid ${C.line};font-family:${FONT};font-size:13px;line-height:1.55;color:${C.muted}"><strong style="font-weight:600">Why you’re getting this:</strong> ${esc(b.why)}</p>
</td></tr>
<tr><td align="center" class="muted" style="padding:22px 16px 0;font-family:${FONT};font-size:12px;line-height:1.7;color:${C.muted}">
With care, the Tasukeru team<br>Tasukeru (助ける) means “to help” in Japanese.<br>
${b.unsubscribe ? `<a class="link" href="${esc(b.unsubscribe.page)}" style="color:${C.muted};text-decoration:underline">Unsubscribe in one click</a> &nbsp;·&nbsp; ` : ""}<a class="link" href="${esc(origin)}/privacy" style="color:${C.muted};text-decoration:underline">Privacy</a>
</td></tr>
</table></td></tr></table></body></html>`;
  const text = [
    "Tasukeru",
    "",
    greet,
    "",
    ...b.paragraphs.flatMap((t) => [t, ""]),
    ...(b.quote ? [...(b.quote.title ? [b.quote.title] : []), ...b.quote.lines, ""] : []),
    ...(b.items ?? []).flatMap((i) => [`${i.label}: ${i.title}`, ...(i.meta ? [i.meta] : []), i.url, ""]),
    ...(b.button ? [`${b.button.label}: ${b.button.url}`, ""] : []),
    `Why you're getting this: ${b.why}`,
    "",
    "--",
    "With care, the Tasukeru team",
    "Tasukeru (助ける) means \"to help\" in Japanese.",
    ...(b.unsubscribe ? [`Unsubscribe in one click: ${b.unsubscribe.page}`] : []),
    `Privacy: ${origin}/privacy`,
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
      paragraphs: ["Welcome to Tasukeru. We’re really glad you’re here.", "One small step left: please confirm this is your email address, so we can send you the updates you asked for. The button works for 7 days."],
      button: { label: "Confirm my email", url },
      why: "this address was used to create a Tasukeru account. If that wasn’t you, just ignore this email and nothing will happen.",
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
      paragraphs: ["We got a request to reset the password for your Tasukeru account.", "Choose a new one with the button below. It works once, for one hour."],
      button: { label: "Choose a new password", url },
      why: "someone asked to reset the password for this address. If that wasn’t you, you can ignore this email; your password stays the same.",
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
      paragraphs: [`There’s a new study for ${diseases}, from ${a.organisation}.`, "A person on our team read it before it reached you. Taking part is always your choice, and there is no rush."],
      quote: { title: a.title, lines: [a.summary, `Who can take part: ${a.eligibility}`, `How to get in touch: ${a.contact}`, `Ethics approval: ${a.ethics}`] },
      button: { label: "See it in my atlas", url: meUrl },
      why: `you follow ${diseases} and asked to hear about studies.`,
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
        `A researcher at ${organisation} wrote to families who follow ${diseases}. They don’t know your email address, and they only hear from you if you decide to reply.`,
        verified ? "Their account uses an institutional email address." : "Their account is not verified yet, so please be careful.",
      ],
      quote: { lines: [message] },
      button: { label: "Read it in my atlas", url: meUrl },
      why: "you said researchers may contact you through Tasukeru. You can turn this off anytime in My atlas.",
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
          ? "Here’s what’s new this week for the diseases you follow."
          : grantsOnly
            ? "Good news: new research has been funded on a gene behind a disease you follow. More people are working on it."
            : "We found something new for the diseases you follow: studies looking for participants, or newly funded research.",
        grantsOnly
          ? "Each link opens the public project page at NIH RePORTER, with the institution doing the work."
          : "Ages, places and how to join are on each study page. A doctor can help you decide whether a study fits.",
      ],
      items: items.map((i) => ({ label: i.disease, title: i.title, url: i.url, meta: i.meta })),
      button: { label: "Open my atlas", url: meUrl },
      why: weekly
        ? "you follow these diseases and chose a weekly summary."
        : "you follow these diseases and asked to hear about new studies and research.",
      unsubscribe,
    }),
  };
}

/** Every template with made-up sample data, for the admin preview (nothing is sent). */
export function sampleEmails(base: string): { name: string; email: Email }[] {
  const to = "family@example.org";
  const unsub: Unsub = { page: `${base}/unsubscribe?t=SAMPLE`, post: `${base}/api/account/unsubscribe?t=SAMPLE` };
  const items = [
    { disease: "STXBP1-related disorders", title: "A Multicentric European Study to Promote Clinical Trial Readiness for STXBP1-related Disorders", url: "https://clinicaltrials.gov/study/NCT06625112", meta: "recruiting · European STXBP1 Consortium" },
    { disease: "New research · SCN2A-related disorders", title: "Dual-AAV gene replacement for SCN2A disorders", url: "https://reporter.nih.gov/project-details/11594149", meta: "Purdue University · NIH, fiscal year 2026 · mentions SCN2A" },
  ];
  return [
    { name: "Confirm your email", email: verificationEmail(to, `${base}/verify?t=SAMPLE`) },
    { name: "Reset your password", email: resetEmail(to, `${base}/reset?t=SAMPLE`) },
    {
      name: "Study announcement",
      email: announcementEmail(
        to,
        {
          title: "Sleep and seizures in SCN2A: a home study",
          summary: "We are studying sleep in children with SCN2A changes, using a small wrist monitor at home for two weeks.",
          eligibility: "Children aged 2 to 12 with a confirmed SCN2A variant.",
          contact: "Study team via the hospital research office web form",
          ethics: "REC 24/LO/0001 (example)",
          organisation: "Example University Hospital",
        },
        "SCN2A-related disorders",
        `${base}/me`,
        unsub,
      ),
    },
    { name: "Researcher message", email: contactEmail(to, "Example University Hospital", "We would like to hear how sleep affects your family. If you are interested, reply through Tasukeru.", "SCN2A-related disorders", true, `${base}/me`, unsub) },
    { name: "Study notice", email: trialsEmail(to, items, false, `${base}/me`, unsub) },
    { name: "Weekly summary", email: trialsEmail(to, items, true, `${base}/me`, unsub) },
    { name: "Admin test", email: { ...testEmail(to), ...render("Tasukeru: test email", { paragraphs: ["Good news: email from Tasukeru reaches you.", "This test went out through the smtp transport. Nothing else to do."], button: { label: "Open Tasukeru", url: base }, why: "you asked for a test email on the Tasukeru admin page." }) } },
  ];
}
