import io
import os
import re
import base64
import logging
from typing import Optional, List, Tuple, Dict, Union
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

class MeeBhoomiCaptchaSolver:
    """
    High-precision self-contained OCR engine for Andhra Pradesh government portal captchas.
    Specialized for MeeBhoomi / Webland 4 to 6 digit numeric and alphanumeric captchas.
    Uses adaptive morphology, vertical projection segmentation, and topological template correlation.
    Zero external binary dependencies (runs 100% via OpenCV and Pillow).
    """

    CHAR_WIDTH = 20
    CHAR_HEIGHT = 26
    DIGITS = "0123456789"
    ALPHANUMERIC = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

    def __init__(self, mode: str = "numeric"):
        """
        :param mode: 'numeric' for standard MeeBhoomi 5-digit PINs, 'alphanumeric' for mixed characters.
        """
        self.mode = mode
        self.charset = self.DIGITS if mode == "numeric" else self.ALPHANUMERIC
        self.templates = self._build_template_bank()

    def _build_template_bank(self) -> Dict[str, List[np.ndarray]]:
        """
        Generates multi-font normalized character templates (20x26) at initialization.
        Uses available system fonts (Arial, Tahoma, Calibri, Times) and PIL default.
        """
        templates: Dict[str, List[np.ndarray]] = {ch: [] for ch in self.charset}
        
        font_paths = [
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/tahoma.ttf",
            "C:/Windows/Fonts/calibri.ttf",
            "C:/Windows/Fonts/cour.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
        ]
        
        usable_fonts = []
        for fp in font_paths:
            if os.path.exists(fp):
                try:
                    for sz in [22, 24, 26]:
                        usable_fonts.append(ImageFont.truetype(fp, sz))
                except Exception:
                    continue

        if not usable_fonts:
            usable_fonts.append(ImageFont.load_default())

        for font in usable_fonts:
            for ch in self.charset:
                im = Image.new("L", (36, 42), 0)
                dr = ImageDraw.Draw(im)
                dr.text((6, 4), ch, fill=255, font=font)
                arr = np.array(im)
                
                y_idxs, x_idxs = np.where(arr > 30)
                if len(y_idxs) > 0:
                    arr_crop = arr[np.min(y_idxs):np.max(y_idxs)+1, np.min(x_idxs):np.max(x_idxs)+1]
                    norm = cv2.resize(arr_crop, (self.CHAR_WIDTH, self.CHAR_HEIGHT), interpolation=cv2.INTER_AREA)
                    _, norm_bin = cv2.threshold(norm, 100, 255, cv2.THRESH_BINARY)
                    templates[ch].append(norm_bin)

        return templates

    def _analyze_holes(self, binary_glyph: np.ndarray) -> List[Tuple[float, float, float]]:
        """
        Analyzes closed interior holes in a 20x26 binary character glyph using floodfill.
        Returns a list of (hole_area, relative_center_y, relative_height) for each genuine hole.
        """
        h, w = binary_glyph.shape
        # Pad border so floodfill can reach all exterior background pixels
        padded = cv2.copyMakeBorder(binary_glyph, 2, 2, 2, 2, cv2.BORDER_CONSTANT, value=0)
        ph, pw = padded.shape
        flood = padded.copy()
        mask = np.zeros((ph + 2, pw + 2), np.uint8)
        cv2.floodFill(flood, mask, (0, 0), 255)

        # Inverted flood leaves ONLY interior holes as 255
        holes_img = cv2.bitwise_not(flood)
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(holes_img)

        holes = []
        for lbl in range(1, num_labels):
            area = stats[lbl, cv2.CC_STAT_AREA]
            hole_h = stats[lbl, cv2.CC_STAT_HEIGHT]
            cy = centroids[lbl][1] - 2  # Subtract padding offset
            if area >= 4:  # Filter out single-pixel artifacts
                holes.append((float(area), float(cy / h), float(hole_h / h)))
        return holes

    def preprocess_image(self, img_np: np.ndarray) -> np.ndarray:
        """
        Preprocesses raw captcha image to high-contrast binary:
        1. Grayscale conversion.
        2. Bilateral filtering for edge-preserving noise suppression.
        3. Otsu thresholding with inversion.
        4. Light noise suppression preserving character topology.
        """
        if len(img_np.shape) == 3:
            gray = cv2.cvtColor(img_np, cv2.COLOR_BGR2GRAY)
        else:
            gray = img_np.copy()

        # Edge-preserving filter
        denoised = cv2.bilateralFilter(gray, 5, 40, 40)

        # Otsu binarization
        _, thresh = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        # Median filter to clean isolated speckles without eroding character strokes
        cleaned = cv2.medianBlur(thresh, 3)

        return cleaned

    def segment_characters(self, binary_img: np.ndarray) -> List[np.ndarray]:
        """
        Segments character glyphs from the preprocessed binary image using
        vertical projection profile with adaptive splitting for touching characters.
        """
        proj = np.sum(binary_img, axis=0) // 255
        h, w = binary_img.shape

        # Identify contiguous horizontal regions containing foreground pixels
        segments: List[Tuple[int, int]] = []
        in_segment = False
        start_col = 0
        min_density_threshold = max(1, int(h * 0.03))

        for col, val in enumerate(proj):
            if val >= min_density_threshold and not in_segment:
                in_segment = True
                start_col = col
            elif val < min_density_threshold and in_segment:
                in_segment = False
                if (col - start_col) >= 2:  # Retain narrow digits like '1'
                    segments.append((start_col, col))
        if in_segment and (w - start_col) >= 2:
            segments.append((start_col, w))

        # Split segments that are too wide (merged characters)
        widths = [end - start for start, end in segments]
        median_width = float(np.median(widths)) if widths else 16.0
        refined_segments: List[Tuple[int, int]] = []

        for start, end in segments:
            seg_width = end - start
            if seg_width > 1.7 * median_width:
                # Two or more characters merged, find valley in middle 50%
                mid = (start + end) // 2
                search_start = start + int(seg_width * 0.3)
                search_end = end - int(seg_width * 0.3)
                if search_end > search_start:
                    sub_proj = proj[search_start:search_end]
                    split_offset = int(np.argmin(sub_proj))
                    split_col = search_start + split_offset
                    refined_segments.append((start, split_col))
                    refined_segments.append((split_col, end))
                else:
                    refined_segments.append((start, mid))
                    refined_segments.append((mid, end))
            else:
                refined_segments.append((start, end))

        # Extract, vertically crop and normalize each character glyph
        glyphs: List[np.ndarray] = []
        for start, end in refined_segments:
            glyph_crop = binary_img[:, start:end]
            y_idxs, x_idxs = np.where(glyph_crop > 0)
            if len(y_idxs) < 10:  # Ignore tiny noise fragments
                continue
            y_min, y_max = np.min(y_idxs), np.max(y_idxs)
            x_min, x_max = np.min(x_idxs), np.max(x_idxs)
            cropped = glyph_crop[y_min:y_max+1, x_min:x_max+1]
            resized = cv2.resize(cropped, (self.CHAR_WIDTH, self.CHAR_HEIGHT), interpolation=cv2.INTER_AREA)
            _, glyph_bin = cv2.threshold(resized, 100, 255, cv2.THRESH_BINARY)
            glyphs.append(glyph_bin)

        return glyphs

    def classify_glyph(self, glyph: np.ndarray) -> str:
        """
        Classifies an isolated 20x26 binary glyph against template bank with topological scoring.
        Disambiguates 0, 6, 8, 9 using hole counts and hole centroid coordinates.
        """
        best_char = "?"
        best_score = -100.0
        glyph_holes = self._analyze_holes(glyph)
        num_holes = len(glyph_holes)

        for ch, tmpl_list in self.templates.items():
            for tmpl in tmpl_list:
                # Normalized cross-correlation
                res = cv2.matchTemplate(glyph, tmpl, cv2.TM_CCOEFF_NORMED)
                corr = float(res[0][0])
                
                # Topological hole characteristics
                tmpl_holes = self._analyze_holes(tmpl)
                tmpl_num_holes = len(tmpl_holes)

                # Hole count match bonus / penalty
                if num_holes == tmpl_num_holes:
                    corr += 0.15
                    # If single hole, check centroid position
                    if num_holes == 1 and tmpl_num_holes == 1:
                        _, g_cy, g_hh = glyph_holes[0]
                        _, t_cy, t_hh = tmpl_holes[0]
                        pos_diff = abs(g_cy - t_cy)
                        corr -= pos_diff * 0.25
                else:
                    corr -= abs(num_holes - tmpl_num_holes) * 0.20

                if corr > best_score:
                    best_score = corr
                    best_char = ch

        return best_char

    def solve(self, image_data: Union[bytes, np.ndarray, Image.Image, str]) -> str:
        """
        Main entry point to solve captcha from multiple input formats:
        - raw bytes (PNG/JPEG)
        - PIL Image
        - numpy ndarray
        - Base64 data URI string or raw base64 string
        """
        try:
            # 1. Parse input to OpenCV BGR array
            if isinstance(image_data, str):
                if image_data.startswith("data:image"):
                    image_data = re.sub(r"^data:image/.+;base64,", "", image_data)
                raw_bytes = base64.b64decode(image_data)
                nparr = np.frombuffer(raw_bytes, np.uint8)
                img_np = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            elif isinstance(image_data, bytes):
                nparr = np.frombuffer(image_data, np.uint8)
                img_np = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            elif isinstance(image_data, Image.Image):
                img_np = cv2.cvtColor(np.array(image_data), cv2.COLOR_RGB2BGR)
            elif isinstance(image_data, np.ndarray):
                img_np = image_data
            else:
                logger.error("Unsupported captcha image input format")
                return ""

            if img_np is None or img_np.size == 0:
                logger.error("Empty image provided to Captcha Solver")
                return ""

            # 2. Preprocess & binarize
            binary = self.preprocess_image(img_np)

            # 3. Segment character glyphs
            glyphs = self.segment_characters(binary)

            if not glyphs:
                logger.warning("No characters segmented from captcha image")
                return ""

            # 4. Classify each glyph
            solved_text = "".join(self.classify_glyph(g) for g in glyphs)
            logger.info(f"MeeBhoomi Captcha Solved: '{solved_text}' ({len(glyphs)} glyphs)")
            return solved_text

        except Exception as e:
            logger.error(f"Error in MeeBhoomi Captcha Solver: {e}")
            return ""

    @staticmethod
    def generate_synthetic_captcha(
        text: str = "74925",
        width: int = 165,
        height: int = 45,
        noise_lines: int = 1,
        noise_dots: int = 15
    ) -> Tuple[bytes, str]:
        """
        Utility generator producing an authentic synthetic AP MeeBhoomi captcha
        for offline testing and validation benchmarks.
        Returns (png_bytes, ground_truth_text).
        """
        im = Image.new("RGB", (width, height), color=(250, 252, 255))
        draw = ImageDraw.Draw(im)

        # Choose system font or fallback
        font = None
        for fp in ["C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/tahoma.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
            if os.path.exists(fp):
                try:
                    font = ImageFont.truetype(fp, 26)
                    break
                except Exception:
                    pass
        if font is None:
            font = ImageFont.load_default()

        # Add background noise lines and speckles first (like ASP.NET CaptchaImage)
        for _ in range(noise_lines):
            y1 = np.random.randint(5, height - 5)
            y2 = np.random.randint(5, height - 5)
            draw.line([(0, y1), (width, y2)], fill=(200, 205, 215), width=1)

        for _ in range(noise_dots):
            dx = np.random.randint(0, width)
            dy = np.random.randint(0, height)
            draw.point((dx, dy), fill=(180, 185, 195))

        # Draw text foreground with character spacing
        x_cursor = 12
        for ch in text:
            y_offset = 7
            color = (20, 25, 45)
            draw.text((x_cursor, y_offset), ch, fill=color, font=font)
            x_cursor += 24

        buf = io.BytesIO()
        im.save(buf, format="PNG")
        return buf.getvalue(), text
