import type { Metadata } from "next";
import { ReportContact } from "@/components/community/ReportContact";

export const metadata: Metadata = { title: "Privacy · Tasukeru" };

const H2 = "mt-8 text-[19px] font-semibold text-ink";
const P = "mt-2 text-[16px] leading-relaxed text-ink-2";

export default function Page() {
  return (
    <div className="mx-auto w-full max-w-[680px] px-4 pb-24 pt-10">
      <h1 className="text-[28px] font-semibold text-ink">Privacy at Tasukeru</h1>
      <p className={P}>You can use all of Tasukeru without an account. Searches, pages and DNA checks are not tied to you, and the DNA sequence and VCF check runs entirely in your browser.</p>

      <h2 className={H2}>If you create an account, we keep</h2>
      <ul className="mt-2 list-disc space-y-1 pl-5 text-[16px] text-ink-2">
        <li>your email and a scrambled form of your password (scrypt with a random salt; we cannot read it);</li>
        <li>who you are (family, patient, group leader, researcher or industry), the diseases you follow, and a country if you give one;</li>
        <li>your choices about notifications and researcher contact, your saved items, and messages in your inbox.</li>
      </ul>

      <h2 className={H2}>What others can see</h2>
      <p className={P}>
        Nobody sees your email. Researchers see only anonymous counts of members per disease and country, and only when a group has at least 5
        members. A researcher can send a message through the atlas only to members who ticked “researchers may contact me”; they never learn who
        received it unless you reply.
      </p>
      <p className={P}>We never sell or share your contact details. Study announcements are reviewed by a person before they reach anyone.</p>

      <h2 className={H2}>Emails</h2>
      <p className={P}>
        We email you only after you confirm your address, and only what you asked for: new studies for diseases you follow (one at a time or as a
        weekly summary), approved study announcements, and messages researchers send through the atlas. Each email says why you are getting it and
        has a one-click unsubscribe link. Password-reset and confirmation emails are sent only when you ask for them. Emails are sent from no-reply@mehro.ch, through
        Resend or our own mail server, which receive your address and the message for that purpose only.
      </p>

      <h2 id="report" className={`${H2} scroll-mt-20`}>
        Contact details we show for groups and studies
      </h2>
      <p className={P}>
        On group and study cards we show only contact details that an organisation publishes so that people can reach it: its general phone
        number and email from its own website, a contact person it names on its own site (with the role, phone and email exactly as published,
        and a link to that page), and a recruiting study’s central contact from ClinicalTrials.gov. We never show researchers’ personal
        contact details; researchers are reached only through “Request contact” or their institution’s page. If a detail is wrong, or it is
        about you and you want it removed, tell the organisation or use this form. A person on our team reviews every request.
      </p>
      <h3 className="mt-5 text-[16px] font-semibold text-ink">Report or remove a contact</h3>
      <ReportContact />

      <h2 className={H2}>Your controls</h2>
      <p className={P}>
        In “My atlas” you can change every choice, export everything we hold about you as a file, and delete your account. Deleting removes your
        account, what you follow, your inbox and saved items straight away.
      </p>

      <h2 className={H2}>Technical notes</h2>
      <p className={P}>
        We use one cookie, to keep you signed in (httpOnly, signed, 30 days). There is no advertising or tracking. Data is stored in a managed Redis
        database. Every notice also appears in your inbox on the site. This is a hackathon prototype: please do not store anything
        sensitive in free-text fields.
      </p>
    </div>
  );
}
