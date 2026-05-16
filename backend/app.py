"""
VisionarySynth — Backend API
============================
Converts hand-drawn fashion sketches into realistic fashion images using
Stable Diffusion 1.5 + ControlNet (scribble) + LoRA.

Author  : VisionarySynth Team
Version : 1.0.0
"""

import io
import base64
import logging
from contextlib import asynccontextmanager

import cv2
import numpy as np
import torch
from PIL import Image
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from diffusers import StableDiffusionControlNetPipeline, ControlNetModel
from diffusers import UniPCMultistepScheduler

# ---------------------------------------------------------------------------
# Logging setup — prints timestamped messages to stdout (visible on Render)
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Global pipeline variable — loaded once at startup and reused across requests
# ---------------------------------------------------------------------------
pipeline = None


# ---------------------------------------------------------------------------
# Pydantic request schema
# ---------------------------------------------------------------------------
class GenerateRequest(BaseModel):
    """
    Schema for the POST /generate request body.

    Fields
    ------
    sketch_base64 : str
        The hand-drawn sketch encoded as a base64 string (PNG or JPEG).
    style : str
        Fashion style descriptor, e.g. "streetwear", "formal", "bohemian".
    skin_tone : str
        Skin tone descriptor, e.g. "fair", "medium", "dark".
    """

    sketch_base64: str
    style: str
    skin_tone: str


# ---------------------------------------------------------------------------
# Lifespan context manager — loads the AI model once when the server starts
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan handler.

    Loads the ControlNet + Stable Diffusion pipeline into memory on startup
    so every request can reuse the same model without reload overhead.
    On Render free tier this runs once when the dyno wakes up.
    """
    global pipeline

    logger.info("=== VisionarySynth API starting up ===")

    # ------------------------------------------------------------------
    # Decide compute device and dtype
    # CUDA (GPU) → float16  (faster, less VRAM)
    # CPU        → float32  (slower but universally compatible)
    # Render free tier is CPU-only, so this will use float32.
    # ------------------------------------------------------------------
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32
    logger.info(f"Using device: {device}  |  dtype: {dtype}")

    try:
        # --------------------------------------------------------------
        # 1. Load ControlNet scribble model
        #    This model understands rough edge/scribble images as guidance.
        # --------------------------------------------------------------
        logger.info("Loading ControlNet scribble model…")
        controlnet = ControlNetModel.from_pretrained(
            "lllyasviel/sd-controlnet-scribble",
            torch_dtype=dtype,
        )

        # --------------------------------------------------------------
        # 2. Load Stable Diffusion 1.5 pipeline with the ControlNet attached
        # --------------------------------------------------------------
        logger.info("Loading Stable Diffusion 1.5 pipeline…")
        pipe = StableDiffusionControlNetPipeline.from_pretrained(
            "runwayml/stable-diffusion-v1-5",
            controlnet=controlnet,
            torch_dtype=dtype,
            safety_checker=None,          # disabled to speed up CPU inference
            requires_safety_checker=False,
        )

        # --------------------------------------------------------------
        # 3. Attach a fast scheduler (UniPC is faster than PNDM/DDIM)
        # --------------------------------------------------------------
        pipe.scheduler = UniPCMultistepScheduler.from_config(
            pipe.scheduler.config
        )

        # --------------------------------------------------------------
        # 4. Move the full pipeline to the target device
        # --------------------------------------------------------------
        pipe = pipe.to(device)

        # --------------------------------------------------------------
        # 5. Enable memory optimisations on CPU to avoid OOM on Render
        # --------------------------------------------------------------
        if device == "cpu":
            pipe.enable_attention_slicing()   # process attention in chunks
            logger.info("Attention slicing enabled for CPU inference.")

        pipeline = pipe
        logger.info("✅ Pipeline loaded successfully. API is ready.")

    except Exception as exc:
        # Log the full error but do NOT crash — let the health endpoint still
        # respond so Render doesn't immediately restart the dyno.
        logger.error(f"❌ Failed to load pipeline: {exc}", exc_info=True)
        pipeline = None

    yield  # ← server is now live and handling requests

    # Cleanup on shutdown (optional, but good practice)
    logger.info("=== VisionarySynth API shutting down ===")
    pipeline = None


# ---------------------------------------------------------------------------
# FastAPI application instance
# ---------------------------------------------------------------------------
app = FastAPI(
    title="VisionarySynth API",
    description="Converts hand-drawn fashion sketches into realistic images.",
    version="1.0.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS middleware — allows the GitHub Pages frontend (any origin) to call this
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # open to all origins; tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Helper: decode a base64 string → PIL Image
# ---------------------------------------------------------------------------
def decode_base64_image(b64_string: str) -> Image.Image:
    """
    Decode a base64-encoded image string into a PIL Image object.

    Parameters
    ----------
    b64_string : str
        Raw base64 string (with or without data-URI prefix like
        'data:image/png;base64,...').

    Returns
    -------
    PIL.Image.Image
        The decoded image in RGB mode.

    Raises
    ------
    ValueError
        If the string is not valid base64 or cannot be opened as an image.
    """
    try:
        # Strip data-URI prefix if present (e.g. from a browser canvas export)
        if "," in b64_string:
            b64_string = b64_string.split(",", 1)[1]

        # Decode bytes and wrap in a file-like buffer
        image_bytes = base64.b64decode(b64_string)
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        return image

    except Exception as exc:
        raise ValueError(f"Invalid base64 image data: {exc}") from exc


# ---------------------------------------------------------------------------
# Helper: preprocess sketch with OpenCV (grayscale → threshold → invert)
# ---------------------------------------------------------------------------
def preprocess_sketch(pil_image: Image.Image) -> Image.Image:
    """
    Preprocess a hand-drawn sketch so it matches the expected ControlNet
    scribble format: white lines on a black background.

    Steps
    -----
    1. Convert PIL image → NumPy array (BGR for OpenCV).
    2. Convert to grayscale.
    3. Apply binary threshold (Otsu's method) to make edges crisp.
    4. Invert colours so strokes become white on black.
    5. Convert back to a 3-channel PIL Image (ControlNet expects RGB).

    Parameters
    ----------
    pil_image : PIL.Image.Image
        The raw sketch image received from the frontend.

    Returns
    -------
    PIL.Image.Image
        Preprocessed scribble image suitable for ControlNet input.
    """
    # Step 1 — PIL → NumPy (RGB → BGR because OpenCV expects BGR)
    np_image = np.array(pil_image)
    bgr_image = cv2.cvtColor(np_image, cv2.COLOR_RGB2BGR)

    # Step 2 — Grayscale conversion
    gray = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2GRAY)

    # Step 3 — Otsu's binary threshold: automatically finds the best cutoff
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Step 4 — Invert: sketches are usually dark lines on white paper;
    #           ControlNet scribble expects white lines on black background.
    inverted = cv2.bitwise_not(binary)

    # Step 5 — Convert single-channel back to 3-channel RGB PIL image
    rgb = cv2.cvtColor(inverted, cv2.COLOR_GRAY2RGB)
    return Image.fromarray(rgb)


# ---------------------------------------------------------------------------
# Helper: encode a PIL Image → base64 string
# ---------------------------------------------------------------------------
def encode_image_to_base64(pil_image: Image.Image) -> str:
    """
    Encode a PIL Image into a base64 PNG string for JSON transport.

    Parameters
    ----------
    pil_image : PIL.Image.Image
        Any PIL image to encode.

    Returns
    -------
    str
        Base64-encoded PNG string (no data-URI prefix).
    """
    buffer = io.BytesIO()
    pil_image.save(buffer, format="PNG")
    buffer.seek(0)
    return base64.b64encode(buffer.read()).decode("utf-8")


# ---------------------------------------------------------------------------
# Helper: build the text prompt from user inputs
# ---------------------------------------------------------------------------
def build_prompt(style: str, skin_tone: str) -> str:
    """
    Construct a detailed positive prompt for Stable Diffusion.

    The prompt is engineered to produce high-quality, photorealistic
    fashion imagery consistent with a professional editorial shoot.

    Parameters
    ----------
    style     : str  e.g. "streetwear", "formal evening wear"
    skin_tone : str  e.g. "fair", "medium brown", "dark"

    Returns
    -------
    str
        Complete positive prompt string.
    """
    return (
        f"realistic {style} fashion clothing, {skin_tone} skin tone, "
        "high quality, photorealistic, fashion magazine editorial, "
        "studio lighting, professional photograph, sharp focus, "
        "8k resolution, detailed fabric texture, elegant pose"
    )


# ---------------------------------------------------------------------------
# GET /  — Health check endpoint
# ---------------------------------------------------------------------------
@app.get("/", tags=["Health"])
async def root():
    """
    Health check endpoint.

    Returns a simple JSON confirming the API is alive.
    Useful for Render uptime checks and frontend connectivity tests.

    Returns
    -------
    dict
        {"status": "VisionarySynth API is running"}
    """
    return {"status": "VisionarySynth API is running"}


# ---------------------------------------------------------------------------
# POST /generate  — Main image generation endpoint
# ---------------------------------------------------------------------------
@app.post("/generate", tags=["Generation"])
async def generate_images(request: GenerateRequest):
    """
    Convert a hand-drawn sketch into 3 realistic fashion image variants.

    Workflow
    --------
    1. Validate that the AI pipeline loaded successfully.
    2. Decode the incoming base64 sketch.
    3. Preprocess the sketch (grayscale → threshold → invert).
    4. Resize to 512×512 (SD 1.5 native resolution).
    5. Build the text prompt from style + skin_tone.
    6. Run the ControlNet pipeline to generate 3 image variants.
    7. Encode each output image to base64.
    8. Return all 3 images in the JSON response.

    Parameters
    ----------
    request : GenerateRequest
        JSON body with sketch_base64, style, skin_tone.

    Returns
    -------
    dict
        {
          "images": ["<base64_png>", "<base64_png>", "<base64_png>"],
          "prompt": "<the prompt that was used>"
        }

    Raises
    ------
    HTTPException 503
        If the AI pipeline is not loaded (model failed to initialise).
    HTTPException 400
        If the base64 sketch data is invalid.
    HTTPException 500
        If anything else goes wrong during generation.
    """
    global pipeline

    # ------------------------------------------------------------------
    # Guard: ensure the model loaded correctly at startup
    # ------------------------------------------------------------------
    if pipeline is None:
        logger.error("Generation requested but pipeline is not loaded.")
        raise HTTPException(
            status_code=503,
            detail="AI model is not available. Check server logs for startup errors.",
        )

    try:
        # --------------------------------------------------------------
        # Step 1 — Decode the base64 sketch sent from the frontend canvas
        # --------------------------------------------------------------
        logger.info("Decoding incoming sketch…")
        try:
            raw_sketch = decode_base64_image(request.sketch_base64)
        except ValueError as ve:
            raise HTTPException(status_code=400, detail=str(ve))

        # --------------------------------------------------------------
        # Step 2 — Preprocess: grayscale + threshold + invert
        #          This transforms the freehand drawing into a clean
        #          scribble-style control image for ControlNet.
        # --------------------------------------------------------------
        logger.info("Preprocessing sketch with OpenCV…")
        control_image = preprocess_sketch(raw_sketch)

        # --------------------------------------------------------------
        # Step 3 — Resize to 512×512 (Stable Diffusion 1.5 native size)
        #          Using LANCZOS for best quality downsampling.
        # --------------------------------------------------------------
        control_image = control_image.resize((512, 512), Image.LANCZOS)

        # --------------------------------------------------------------
        # Step 4 — Build positive and negative prompts
        # --------------------------------------------------------------
        positive_prompt = build_prompt(request.style, request.skin_tone)
        negative_prompt = (
            "blurry, low quality, cartoon, anime, sketch, drawing, "
            "deformed, ugly, bad anatomy, watermark, text, logo"
        )
        logger.info(f"Prompt: {positive_prompt}")

        # --------------------------------------------------------------
        # Step 5 — Run the diffusion pipeline
        #          num_images_per_prompt=3 → 3 variants in one forward pass
        #          num_inference_steps=20  → balance speed vs quality on CPU
        #          guidance_scale=7.5      → standard classifier-free guidance
        #          controlnet_conditioning_scale=1.0 → full sketch adherence
        # --------------------------------------------------------------
        logger.info("Running Stable Diffusion ControlNet pipeline…")
        result = pipeline(
            prompt=positive_prompt,
            negative_prompt=negative_prompt,
            image=control_image,
            num_images_per_prompt=3,
            num_inference_steps=20,
            guidance_scale=7.5,
            controlnet_conditioning_scale=1.0,
        )

        # --------------------------------------------------------------
        # Step 6 — Encode each generated PIL image to base64 PNG
        # --------------------------------------------------------------
        logger.info(f"Encoding {len(result.images)} output images…")
        encoded_images = [
            encode_image_to_base64(img) for img in result.images
        ]

        logger.info("✅ Generation complete. Returning response.")
        return {
            "images": encoded_images,
            "prompt": positive_prompt,
        }

    except HTTPException:
        # Re-raise HTTP exceptions as-is (don't wrap them again)
        raise

    except torch.cuda.OutOfMemoryError:
        # Special handling for GPU OOM — unlikely on Render but good practice
        logger.error("CUDA out of memory during generation.")
        raise HTTPException(
            status_code=500,
            detail="GPU out of memory. Try reducing image size or restart the server.",
        )

    except Exception as exc:
        # Catch-all for any unexpected errors during generation
        logger.error(f"Generation failed: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Image generation failed: {str(exc)}",
        )


# ---------------------------------------------------------------------------
# Entry point — only used when running locally with `python app.py`
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=7860,
        reload=False,   # set reload=True during local development
    )
