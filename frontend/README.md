## VisionarySynth — Frontend

### What This Does
VisionarySynth is a simple, beautiful website that lets you turn basic hand-drawn sketches of clothing into photorealistic fashion images. You upload a sketch, pick a style (like "Casual" or "Streetwear") and a skin tone, and then click generate. The website sends your sketch to an AI brain (the backend server), waits a few minutes, and then shows you three different high-quality fashion designs based on your drawing. You can then download these images.

### How to Use
1. **Open the Website:** Open the `index.html` file in any web browser (like Chrome, Firefox, or Safari).
2. **Upload a Sketch:** Click the dashed box that says "Upload Your Sketch" and select an image file (PNG or JPG) of a clothing sketch from your computer. You can also drag and drop the file directly into the box.
3. **Choose Options:** 
   - Select the fashion style you want from the dropdown menu (e.g., Casual, Formal).
   - Click one of the three colored circles to pick the model's skin tone (Fair, Medium, or Dark).
4. **Generate:** Click the big gold "Generate Fashion" button. 
5. **Wait:** A loading spinner will appear. The AI needs a few minutes to create the images, so please be patient.
6. **Download:** Once the images appear at the bottom of the page, you can click the "Download Design" button under any image to save it to your computer.

### How to Deploy on GitHub Pages
1. **Create a GitHub Account:** If you don't have one, go to github.com and sign up.
2. **Create a New Repository:** Click the "+" icon in the top right corner and select "New repository". Give it a name like `visionary-synth-frontend`. Make it "Public". Click "Create repository".
3. **Upload the File:** On the next screen, click the "uploading an existing file" link. Drag and drop your `index.html` file into the box. Click "Commit changes" at the bottom.
4. **Enable GitHub Pages:**
   - Go to the "Settings" tab of your repository.
   - On the left sidebar, click on "Pages" (under the "Code and automation" section).
   - Under "Build and deployment", look for the "Source" dropdown. It should say "Deploy from a branch".
   - Under "Branch", change "None" to "main" (or "master"). Click "Save".
5. **Get the Link:** At the top of the Pages settings, it will eventually say "Your site is live at [your-link]". It might take a minute or two to build. Click the link to view your live website!

### How to Connect to Backend
Right now, the website doesn't know where the AI brain (backend) is located. You need to tell it.

1. Open `index.html` in any text editor (like Notepad, VS Code, etc.).
2. Scroll down near the bottom to find the `<script>` section.
3. Look for the very first line of JavaScript code:
   ```javascript
   const API_URL = "YOUR_RENDER_URL_HERE"; 
   ```
4. Replace `"YOUR_RENDER_URL_HERE"` with the actual URL of your deployed backend on Render. For example:
   ```javascript
   const API_URL = "https://visionarysynth-backend.onrender.com"; 
   ```
   **Important:** Make sure you keep the quotation marks around the URL and do *not* put a slash (`/`) at the very end of the URL.
5. Save the file and refresh your browser (or upload the updated file to GitHub if you've deployed it).

### File Structure
The `index.html` is a single, self-contained file containing everything needed for the frontend. It is divided into three main sections:
1. **HTML (Structure):** The skeleton of the page inside the `<body>` tags. It defines the header, the upload box, the dropdowns, the buttons, and the empty space where the results will go.
2. **CSS (Style):** Located inside the `<style>` tags in the `<head>`. This handles all the visuals: the dark background (`#0a0a0a`), the gold accents (`#c9a84c`), the fonts (Playfair Display and Inter), and the responsive layout.
3. **JavaScript (Logic):** Located inside the `<script>` tags at the bottom. This makes the page interactive. It handles drag-and-drop, reads the uploaded image, sends it to the backend when you click generate, waits for the response, and then creates the image cards to display the results.

### Customization Guide
If you want to change how the website looks, open `index.html` and look for the CSS section near the top.

*   **Change Colors:** Find the `:root` block at the very top of the `<style>` section. You can change the hex codes for `--bg-color`, `--gold`, etc., to quickly change the entire theme.
*   **Change Fonts:** The fonts are imported from Google Fonts at the top (`<link href="...">`). If you want different fonts, import them from Google Fonts, and then change the `--font-heading` and `--font-body` variables in the `:root` CSS block.
*   **Add More Style Options:** Find the `<select class="style-select" id="styleSelect">` block in the HTML. Add new `<option>` tags inside it. For example: `<option value="vintage">Vintage</option>`. The backend will automatically receive this new value.

### For AI Agents reading this file
The `index.html` is designed to be easily readable and modifiable by an AI agent.

*   **No Build Step:** It's pure HTML/CSS/JS without React, Vue, or npm. You can modify it and test it immediately by opening it in a browser.
*   **Base64 Image Flow:** The frontend expects the user to upload an image. The JS `FileReader` reads this file as a DataURL (Base64). When the user clicks "Generate", this Base64 string is included in the JSON payload sent via `POST` to the `/generate` endpoint.
*   **API Communication:** The fetch logic is contained within the `generateBtn.addEventListener('click', async () => {...})` block. It handles payload construction, UI state management (loading spinners, disabling buttons), the actual `fetch` call, error catching, and passing the successful data to the renderer.
*   **Result Rendering:** The backend is expected to return a JSON object containing an `images` array (array of base64 strings). The `renderResults(imagesArray)` function iterates over this array, dynamically creates HTML cards for each image, attaches the base64 string to the `img src` (prepending the data URI prefix if necessary), creates a dynamic download link, and appends the cards to the `#resultsGrid` container.
*   **Modifying UI:** All CSS is scoped using descriptive class names (e.g., `.upload-container`, `.result-card`) and utilizes CSS variables in the `:root` selector for easy theming. State changes (like selecting a skin tone) are handled by adding/removing specific CSS classes (e.g., `.selected`).
