import subprocess
import os
import io


def render_latex_jpg(latex_content, output_name) -> io.BytesIO | None:
    # ensure working directory exists for temporary tex/pdf/jpg files
    tex_dir = "_tex"
    os.makedirs(tex_dir, exist_ok=True)

    # wrap the content in a valid document class
    full_latex = (
        r"\documentclass[preview,border=2pt]{standalone}"
        r"\usepackage[utf8]{inputenc}"
        r"\usepackage{amsmath, amssymb, enumerate}"
        r"\begin{document}" + latex_content + r"\end{document}"
    )

    tex_file = os.path.join(tex_dir, f"{output_name}.tex")
    jpg_file = os.path.join(tex_dir, f"{output_name}.jpg")

    with open(tex_file, "w", encoding="utf-8") as f:
        f.write(full_latex)

    # pdflatex
    # '--interaction=nonstopmode' prevents hanging on errors
    try:
        process = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", tex_file],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        if process.returncode != 0:
            print("LaTeX Error:", process.stdout)
            return None

        # PDF --> PNG, ImageMagick
        # density 600 for high quality
        pdf_path = os.path.join(tex_dir, f"{output_name}.pdf")
        magick_cmd = ["magick", "-density", "600", pdf_path, "-alpha", "remove", jpg_file]
        subprocess.run(magick_cmd, check=True)

        buf = io.BytesIO()
        with open(jpg_file, "rb") as f:
            buf.write(f.read())

        buf.seek(0)
        return buf

    finally:
        # clear intermediate files
        for ext in ["aux", "log", "pdf", "tex", "jpg"]:
            file_to_del = os.path.join(tex_dir, f"{output_name}.{ext}")
            if os.path.exists(file_to_del):
                os.remove(file_to_del)
