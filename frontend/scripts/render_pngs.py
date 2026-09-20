import os
import glob
from playwright.sync_api import sync_playwright

def render_svgs_to_png():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    logos_dir = os.path.join(script_dir, "..", "public", "logos")
    svg_files = glob.glob(os.path.join(logos_dir, "*.svg"))

    if not svg_files:
        print("No SVG files found in", logos_dir)
        return

    print(f"Found {len(svg_files)} SVG files. Rendering high-quality PNGs via Playwright Chromium...")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        # 512x512 with scale factor 2 gives high-res 1024x1024 PNGs
        page = browser.new_page(viewport={"width": 512, "height": 512}, device_scale_factor=2)

        for svg_path in svg_files:
            file_name = os.path.basename(svg_path)
            png_name = file_name.replace(".svg", ".png")
            png_path = os.path.join(logos_dir, png_name)

            with open(svg_path, "r", encoding="utf-8") as f:
                svg_content = f.read()

            html_wrapper = f"""<!DOCTYPE html>
<html>
<head>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ background: transparent; overflow: hidden; }}
    svg {{ display: block; width: 512px; height: 512px; }}
  </style>
</head>
<body>
  {svg_content}
</body>
</html>"""

            page.set_content(html_wrapper)
            svg_locator = page.locator("svg")
            svg_locator.screenshot(path=png_path, omit_background=True)
            size_kb = os.path.getsize(png_path) / 1024
            print(f"Rendered: {png_name} ({size_kb:.1f} KB)")

        browser.close()

    print("All PNG logos rendered successfully.")

if __name__ == "__main__":
    render_svgs_to_png()
