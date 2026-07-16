# Product

## Register

product

## Platform

web

## Users

Swedish gymnasium (high-school) teachers, working alone on their own Windows 11
desktop (RTX 4090 / 24 GB class). They record lessons — local audio and video
files, or pasted YouTube links — and need them turned into accurate transcripts
(SRT / TXT / VTT) and organized by **date, class, and course**. They are
subject-matter experts, not AI or ML experts. The typical moment of use is a busy
workday, often between or right after lessons, while handling **sensitive student
data** — which is why everything runs locally and offline, with no cloud and no
account.

The job runs past transcription: proofread, summarize, and chat with a transcript
through a local LLM (Qwen3 over an app-managed llama.cpp); extract action items and
calendar events; and search what was said across the whole archive. All of it stays
private and on-device.

## Product Purpose

Transkribera turns recorded lessons into trustworthy, well-organized transcripts and
lets a teacher work with them — proofreading, summarizing, questioning, extracting,
searching — entirely on their own machine. It exists because lesson audio carries
sensitive student data that must never leave the teacher's computer, and because the
tools that otherwise do this well are cloud services. Success is a teacher who can go
from a recording to an accurate, filed, searchable transcript in one unhurried
sitting, confident that nothing was uploaded anywhere.

## Positioning

Everything a teacher needs to turn a lesson recording into an accurate, searchable,
well-filed transcript — proofread, summarized, and questioned with a local model —
running entirely on their own machine, never the cloud.

## Brand Personality

Calm, editorial, and quietly confident — in three words, **calm, editorial,
unobtrusive**. The voice is Swedish, plain, and respectful of the teacher's time and
expertise; never chirpy, salesy, or hyped. The emotional goal is that the teacher
feels **in control and unhurried**, with the software receding into the background
like good paper so that the *lesson content* — not the interface — is the subject.

## Anti-references

Three looks the owner has explicitly ruled out:

- **Generic AI / SaaS dashboard** — card grids, hero-metric tiles, gradient text,
  glassmorphism, cyan-on-dark neon. The "AI slop" look.
- **Dense corporate / enterprise admin UI** — cramped, cold, bureaucratic,
  Bootstrap-gray.
- **Anything that reads as a cloud or online service** — no account or online
  affordances of any kind; the app is strictly local and offline.

## Design Principles

1. **Recede, don't perform.** The UI is quiet scaffolding; the lesson content —
   transcript, sources, answers — is the subject. Prefer whitespace and hairlines over
   boxes and chrome.
2. **Editorial, not dashboard.** Compose like print: a mono eyebrow, a serif-italic
   display title, a lede, asymmetric grids, hairline rules. Never card-grid or
   hero-metric slop; never dense admin tables.
3. **Local and private is the point.** Never imply the cloud. No account or online
   language or iconography; everything stays on-device.
4. **Swedish, plain, unhurried.** All user-facing text is natural Swedish, calm and
   respectful of the teacher's time — no hype, no chirp.
5. **Restrained motion; accessibility as a floor.** Purposeful mask-reveal and
   fade-up with expo-out easing, and reduced motion always honored.

## Accessibility & Inclusion

Accessibility is **best-effort with no formal WCAG target**, but real and
load-bearing: keyboard-operable controls, visible focus, honest labels, and live
regions for asynchronous status. Reduced motion is fully honored throughout. A
hardening pass in July 2026 brought the interface close to AA in practice.
