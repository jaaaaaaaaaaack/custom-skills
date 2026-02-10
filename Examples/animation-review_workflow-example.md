# Animation Review — Example Workflow

This example shows a real flow I used this skill to help with: I briefly describe the animation issue, the agent uses the animation-review skill to record and analyse it, and Gemini returns structured, actionable, frame-level feedback. The feedback allowed Claude to solve the issue in one go, where previously it had been running in circles. 

---

## 1. Original prompt I wrote to Claude

> When a user clicks on a card that's not already in the central slot of the carousel, the card animates to the centre before pushing out into the detail view. The overall animation for this is working really well, but there's just something about the easing or timing that's not feeling natural. It feels like two separate events, but I want it to feel like two stages of the same interaction. Use the animation review skill to analyse it and work out what might improve the feel.

---

## 2. What the agent did

- **Recorded the interaction** using Playwright (the carousel click and resulting animation).
- **Chose diagnose mode** and set up the API call (model, FPS for analysis, and timestamp of the interaction).
- **Sent the video + the prompt below to Gemini.**

The clip that was recorded and sent for analysis is in this repo — on GitHub you can watch it in the file view:

**[Watch the recorded clip](./2026-02-10_snap-detail-open_diagnose.mp4)** < Interaction from 13-18s

---

## 3. Prompt sent to Gemini

Claude then used the skill instructions + codebase context to build this prompt for Gemini:

> Circular carousel of image/video cards. When a non-central card is clicked, two things happen sequentially: (1) the carousel rotates to snap the clicked card to center (0.37s, power3.in easing — accelerating), then (2) the card clones to a fixed overlay and animates to viewport center as a detail view (0.5s, power2.inOut). These are two separate GSAP animations that run back-to-back with an onComplete callback connecting them. The user reports it feels like two separate movements instead of one continuous gesture.
>
> I need frame-by-frame analysis of:
> - the velocity profile through the snap phase  
> - the exact moment of handoff  
> - whether there's a visible pause/stutter at the transition point  
> - the velocity profile through the open phase  
>
> Pay special attention to any frame where motion appears to stop or reverse direction. Also note the easing character of each phase independently.

---

## 4. What Gemini returned

Gemini produced a **diagnose**-style report: animation overview, frame-by-frame tables with timestamps and velocity notes, a clear “handoff / stutter” section, and hypotheses with concrete debugging steps.

**Full example response:** [animation-review_gemini-response-example.md](./animation-review_gemini-response-example.md)

In short: it identified a one-frame pause at the handoff, that the snap was effectively ease-in-out (not pure power3.in), and suggested checking the GSAP tween’s ease and the `onComplete` callback for latency. This allowed Claude to improve the animation in one go, where previously it had tried several approaches that didn't move us closer to the intended result.
