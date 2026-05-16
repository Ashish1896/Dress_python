---
title: VisionarySynth API
emoji: 🎨
colorFrom: yellow
colorTo: purple
sdk: docker
app_port: 7860
---

# VisionarySynth — Backend API

Converts hand-drawn fashion sketches into realistic fashion images using
Stable Diffusion 1.5 + ControlNet (scribble).

## Endpoints

- `GET /` — Health check
- `POST /generate` — Generate fashion images from sketch
